-- ============================================================================
-- Migration 286 -- social_wiring: atendimento blocks + handoffs + Maya supervision (maya-blocks S1)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/maya-blocks/CONTRACT.md. The owner's model
-- (2026-10-19): the real-estate atendimento runs as a closed list of BLOCKS, each with one
-- accountable specialist (an agent or humans); a HANDOFF is the explicit, recorded moment a
-- lead/card leaves one block for the next; Maya supervises every block and reports to the owner.
-- Julia (studio agent `lead-imob`) is block `sdr`.
--
--   atendimento_blocos       per-org configuration of each block: which agent runs it (NULL =
--                            humans), on/off (DEFAULT false), and which pipeline stage slugs it
--                            owns. The current block of a card is DERIVED from its stage; `sdr`
--                            owns the pre-card phase (lais_contatos without lead_id) and no stage.
--                            Absent row = the code default (CONTRACT section 2), never an implied ON.
--   atendimento_handoffs     one row per block-to-block transfer. REFERENCES only (contato, lead,
--                            atendimento, atribuicao, entrega, the originating event id) -- no
--                            copied personal data. Status machine emitido -> assumido | expirado.
--                            unique (org_id, gatilho, origem_evento) makes a replayed event a no-op.
--   agente_scorecards        Maya's daily per-block per-agent metrics (jsonb, formulas in the
--                            contract), stamped with the rubric version that produced them.
--   supervisao_config        per-org supervision switch (supervisao_ativa DEFAULT false) + the
--                            "handoff not assumido within N hours" threshold.
--   lais_interacoes          + primeira_resposta_at: the first Julia/human reply of the episode,
--                            the only missing input of the first-response-time metric (no per-
--                            message store exists in SW; WAHA holds the messages).
--   status_pagina            'atendimento_blocos' + 'supervisao', seeded 'desenvolvimento'
--                            (owner/dev/admin only, per 036 -- DEV_ROLES parity unchanged).
--
-- SAFETY: nothing here sends anything, and nothing is seeded ON (no block row, no config row).
-- RLS: select_own_org + service_role on every new table (writes go through the backend with the
-- service-role client and an explicit org filter; config writes are owner/admin-gated in the
-- router), pattern 281/284. NO SECURITY DEFINER function in this file. FORWARD-ONLY, IDEMPOTENT.
-- PREREQUISITES: core 070 (public.current_org_id_for), 001 (status_pagina, leads), 060
-- (atendimentos), 267 (lais_contatos/lais_interacoes), 270 (lais_envio_entregas), 276
-- (lais_atribuicoes). Applied by the tech-lead with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.atendimentos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.atendimentos (migration 060) -- apply 060 first';
  END IF;
  IF to_regclass('social_wiring.lais_interacoes') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_interacoes (migration 267) -- apply 267 first';
  END IF;
  IF to_regclass('social_wiring.lais_envio_entregas') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_envio_entregas (migration 270) -- apply 270 first';
  END IF;
  IF to_regclass('social_wiring.lais_atribuicoes') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_atribuicoes (migration 276) -- apply 276 first';
  END IF;
  IF to_regclass('social_wiring.status_pagina') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.status_pagina (migration 001) -- apply 001 first';
  END IF;
END
$guard$;

-- ── 1. atendimento_blocos ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_blocos (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid        NOT NULL,
    bloco       text        NOT NULL,
    agent_key   text,
    ativo       boolean     NOT NULL DEFAULT false,
    pipeline    text,
    etapas      text[]      NOT NULL DEFAULT '{}',
    updated_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT atendimento_blocos_bloco_valido CHECK (bloco IN
        ('sdr', 'atendimento', 'negociacao', 'juridico', 'financeiro', 'contador')),
    CONSTRAINT atendimento_blocos_pipeline_do_bloco CHECK (
        (bloco = 'sdr' AND pipeline IS NULL AND cardinality(etapas) = 0)
        OR (bloco <> 'sdr' AND pipeline IN ('funil', 'processos_venda'))
    ),
    CONSTRAINT atendimento_blocos_agent_key_formato CHECK (agent_key IS NULL OR agent_key ~ '^[a-z][a-z0-9-]{1,39}$'),
    CONSTRAINT atendimento_blocos_um_por_bloco UNIQUE (org_id, bloco)
);

COMMENT ON TABLE social_wiring.atendimento_blocos IS
    'Per-org atendimento block config (migration 286, maya-blocks): agent_key NULL = humans; ativo DEFAULT false; '
    'etapas = the pipeline stage slugs the block owns (disjoint across blocks, trigger atendimento_blocos_etapas_disjuntas). '
    'Absent row = the code default; the closed block list lives in the CHECK and in the backend.';

-- Stage slugs must be well-formed, unique within the row, and owned by ONE block per (org, pipeline):
-- the current block is derived from a card's stage, so an overlap would make it ambiguous.
CREATE OR REPLACE FUNCTION social_wiring.atendimento_blocos_etapas_disjuntas()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $fn$
DECLARE
  v_slug text;
  v_dono text;
BEGIN
  IF EXISTS (SELECT 1 FROM unnest(NEW.etapas) AS e(s) WHERE s IS NULL OR s !~ '^[a-z0-9_]+$') THEN
    RAISE EXCEPTION 'etapa com slug invalido no bloco %', NEW.bloco
      USING ERRCODE = 'check_violation', CONSTRAINT = 'atendimento_blocos_etapas_validas';
  END IF;
  IF cardinality(NEW.etapas) <> (SELECT count(DISTINCT s) FROM unnest(NEW.etapas) AS e(s)) THEN
    RAISE EXCEPTION 'etapa repetida no bloco %', NEW.bloco
      USING ERRCODE = 'check_violation', CONSTRAINT = 'atendimento_blocos_etapas_validas';
  END IF;
  SELECT s, b.bloco INTO v_slug, v_dono
    FROM social_wiring.atendimento_blocos b, unnest(b.etapas) AS e(s)
   WHERE b.org_id = NEW.org_id AND b.pipeline = NEW.pipeline AND b.bloco <> NEW.bloco
     AND s = ANY (NEW.etapas)
   LIMIT 1;
  IF v_slug IS NOT NULL THEN
    RAISE EXCEPTION 'a etapa % ja pertence ao bloco %', v_slug, v_dono
      USING ERRCODE = 'check_violation', CONSTRAINT = 'atendimento_blocos_etapas_disjuntas';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS atendimento_blocos_etapas_disjuntas ON social_wiring.atendimento_blocos;
CREATE TRIGGER atendimento_blocos_etapas_disjuntas
    BEFORE INSERT OR UPDATE ON social_wiring.atendimento_blocos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.atendimento_blocos_etapas_disjuntas();

-- ── 2. atendimento_handoffs ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_handoffs (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid        NOT NULL,
    de_bloco        text        NOT NULL,
    para_bloco      text        NOT NULL,
    de_agent_key    text,
    para_agent_key  text,
    gatilho         text        NOT NULL,
    origem_evento   uuid        NOT NULL,
    contato_id      uuid        REFERENCES social_wiring.lais_contatos (id) ON DELETE SET NULL,
    lead_id         uuid        REFERENCES social_wiring.leads (id) ON DELETE SET NULL,
    atendimento_id  uuid        REFERENCES social_wiring.atendimentos (id) ON DELETE SET NULL,
    atribuicao_id   uuid        REFERENCES social_wiring.lais_atribuicoes (id) ON DELETE SET NULL,
    entrega_id      uuid        REFERENCES social_wiring.lais_envio_entregas (id) ON DELETE SET NULL,
    status          text        NOT NULL DEFAULT 'emitido',
    created_at      timestamptz NOT NULL DEFAULT now(),
    assumido_at     timestamptz,
    expirado_at     timestamptz,
    CONSTRAINT atendimento_handoffs_blocos_validos CHECK (
        de_bloco IN ('sdr', 'atendimento', 'negociacao', 'juridico', 'financeiro', 'contador')
        AND para_bloco IN ('sdr', 'atendimento', 'negociacao', 'juridico', 'financeiro', 'contador')
    ),
    CONSTRAINT atendimento_handoffs_blocos_distintos CHECK (de_bloco <> para_bloco),
    CONSTRAINT atendimento_handoffs_gatilho_valido CHECK (gatilho IN ('novo_lead', 'movimento_etapa')),
    CONSTRAINT atendimento_handoffs_status_valido CHECK (status IN ('emitido', 'assumido', 'expirado')),
    -- written as implications so an unknown status trips ONLY status_valido (CHECKs run in name order)
    CONSTRAINT atendimento_handoffs_status_coerente CHECK (
        (status <> 'emitido'  OR (assumido_at IS NULL AND expirado_at IS NULL))
        AND (status <> 'assumido' OR (assumido_at IS NOT NULL AND assumido_at >= created_at AND expirado_at IS NULL))
        AND (status <> 'expirado' OR (expirado_at IS NOT NULL AND expirado_at >= created_at AND assumido_at IS NULL))
    ),
    CONSTRAINT atendimento_handoffs_uma_por_origem UNIQUE (org_id, gatilho, origem_evento)
);

COMMENT ON TABLE social_wiring.atendimento_handoffs IS
    'Block-to-block handoffs (migration 286, maya-blocks): references only, no copied PII. origem_evento = '
    'lais_eventos.id (gatilho novo_lead) or pipeline_movimentos.id (gatilho movimento_etapa); the unique key '
    'makes a replayed event a no-op. Status emitido -> assumido | expirado (both terminal).';

CREATE INDEX IF NOT EXISTS idx_atendimento_handoffs_org_created
    ON social_wiring.atendimento_handoffs (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_atendimento_handoffs_abertos
    ON social_wiring.atendimento_handoffs (org_id, created_at) WHERE status = 'emitido';
CREATE INDEX IF NOT EXISTS idx_atendimento_handoffs_atendimento
    ON social_wiring.atendimento_handoffs (atendimento_id);
CREATE INDEX IF NOT EXISTS idx_atendimento_handoffs_contato
    ON social_wiring.atendimento_handoffs (contato_id);

-- ── 3. agente_scorecards ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.agente_scorecards (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid        NOT NULL,
    bloco           text        NOT NULL,
    agent_key       text,
    dia             date        NOT NULL,
    metricas        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    rubrica_versao  text        NOT NULL,
    calculado_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agente_scorecards_bloco_valido CHECK (bloco IN
        ('sdr', 'atendimento', 'negociacao', 'juridico', 'financeiro', 'contador')),
    CONSTRAINT agente_scorecards_metricas_objeto CHECK (jsonb_typeof(metricas) = 'object'),
    CONSTRAINT agente_scorecards_rubrica_formato CHECK (rubrica_versao ~ '^[a-z0-9_-]+\.v[0-9]+$'),
    -- agent_key NULL = a human-run block; NULLS NOT DISTINCT keeps it one row per day too.
    CONSTRAINT agente_scorecards_um_por_dia UNIQUE NULLS NOT DISTINCT (org_id, bloco, agent_key, dia)
);

COMMENT ON TABLE social_wiring.agente_scorecards IS
    'Maya daily scorecard per (org, bloco, agent_key, dia) (migration 286, maya-blocks); metricas formulas and '
    'sources are in the contract, rubrica_versao names the rubric that produced them (recomputing a day upserts).';

CREATE INDEX IF NOT EXISTS idx_agente_scorecards_org_dia
    ON social_wiring.agente_scorecards (org_id, dia DESC);

-- ── 4. supervisao_config ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.supervisao_config (
    org_id              uuid        PRIMARY KEY,
    supervisao_ativa    boolean     NOT NULL DEFAULT false,
    horas_para_assumir  integer     NOT NULL DEFAULT 24,
    updated_by          uuid,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT supervisao_config_horas_validas CHECK (horas_para_assumir BETWEEN 1 AND 168)
);

COMMENT ON TABLE social_wiring.supervisao_config IS
    'Per-org Maya supervision switch (migration 286): supervisao_ativa DEFAULT false (absent row = off); '
    'horas_para_assumir = the "handoff not assumido within N hours" threshold.';

-- ── 5. lais_interacoes.primeira_resposta_at ──────────────────────────────────
ALTER TABLE social_wiring.lais_interacoes ADD COLUMN IF NOT EXISTS primeira_resposta_at timestamptz;

COMMENT ON COLUMN social_wiring.lais_interacoes.primeira_resposta_at IS
    'First outbound reply of the episode (Julia or a human), written once (migration 286); '
    'primeira_resposta_at - iniciada_at is the first-response time of the Maya sdr scorecard.';

ALTER TABLE social_wiring.lais_interacoes DROP CONSTRAINT IF EXISTS lais_interacoes_primeira_resposta_coerente;
ALTER TABLE social_wiring.lais_interacoes ADD  CONSTRAINT lais_interacoes_primeira_resposta_coerente
    CHECK (primeira_resposta_at IS NULL OR primeira_resposta_at >= iniciada_at);

-- ── 6. RLS ───────────────────────────────────────────────────────────────────
ALTER TABLE social_wiring.atendimento_blocos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "atendimento_blocos_select_own_org" ON social_wiring.atendimento_blocos;
CREATE POLICY "atendimento_blocos_select_own_org" ON social_wiring.atendimento_blocos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "atendimento_blocos_service_role" ON social_wiring.atendimento_blocos;
CREATE POLICY "atendimento_blocos_service_role" ON social_wiring.atendimento_blocos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.atendimento_handoffs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "atendimento_handoffs_select_own_org" ON social_wiring.atendimento_handoffs;
CREATE POLICY "atendimento_handoffs_select_own_org" ON social_wiring.atendimento_handoffs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "atendimento_handoffs_service_role" ON social_wiring.atendimento_handoffs;
CREATE POLICY "atendimento_handoffs_service_role" ON social_wiring.atendimento_handoffs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.agente_scorecards ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agente_scorecards_select_own_org" ON social_wiring.agente_scorecards;
CREATE POLICY "agente_scorecards_select_own_org" ON social_wiring.agente_scorecards
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "agente_scorecards_service_role" ON social_wiring.agente_scorecards;
CREATE POLICY "agente_scorecards_service_role" ON social_wiring.agente_scorecards
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.supervisao_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "supervisao_config_select_own_org" ON social_wiring.supervisao_config;
CREATE POLICY "supervisao_config_select_own_org" ON social_wiring.supervisao_config
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "supervisao_config_service_role" ON social_wiring.supervisao_config;
CREATE POLICY "supervisao_config_service_role" ON social_wiring.supervisao_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── 7. page visibility (dev-only until the owner releases them) ──────────────
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
VALUES ('atendimento_blocos', 'desenvolvimento', 'Blocos do atendimento (Julia, corretor, negociação, jurídico, financeiro, contador)'),
       ('supervisao', 'desenvolvimento', 'Supervisão (Maya) — scorecards e handoffs dos blocos')
ON CONFLICT (nome_pagina) DO NOTHING;
