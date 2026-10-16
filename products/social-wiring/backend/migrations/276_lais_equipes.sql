-- ============================================================================
-- Migration 276 -- social_wiring: Lais wave 11 "Distribuicao / Equipes"
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 13 (wave 11).
-- Owner decision 2026-10-15 #5: distribution data and rules live in SW; Julia only consumes them.
--
--   lais_equipes               a team: nome, atende_apos_julia (Sim/Nao), modo funil|julia, manter_ultimo.
--   lais_equipe_membros        org users of a team (ativo, ordem).
--   lais_distribuicao_cursor   round-robin cursor: the last user picked per team.
--   lais_atribuicoes           append-only log of every attendant pick (feeds TPR + the "distribuicao" metric).
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 267.
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: core 070, 014 (status_pagina), 267 (lais_contatos).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.lais_contatos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_contatos (migration 267) -- apply 267 first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'this migration requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

-- -- 1. lais_equipes -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_equipes (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid        NOT NULL,
    nome               text        NOT NULL,
    atende_apos_julia  boolean     NOT NULL DEFAULT true,
    modo               text        NOT NULL DEFAULT 'funil',
    manter_ultimo      boolean     NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_equipes_nome_valido CHECK (length(btrim(nome)) BETWEEN 1 AND 60),
    CONSTRAINT lais_equipes_modo_valido CHECK (modo IN ('funil', 'julia'))
);

COMMENT ON TABLE social_wiring.lais_equipes IS
    'Attendant team (migration 276, contract 13 / page-map 59.0b): atende_apos_julia = the team takes the chat after '
    'Julia; modo funil = the SW lead/card flow decides, julia = Julia''s handoff assigns an attendant directly.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_equipes_org_nome_uq
    ON social_wiring.lais_equipes (org_id, lower(nome));

-- -- 2. lais_equipe_membros -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_equipe_membros (
    equipe_id   uuid        NOT NULL REFERENCES social_wiring.lais_equipes (id) ON DELETE CASCADE,
    user_id     uuid        NOT NULL,
    org_id      uuid        NOT NULL,
    ativo       boolean     NOT NULL DEFAULT true,
    ordem       integer     NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_equipe_membros_pk PRIMARY KEY (equipe_id, user_id),
    CONSTRAINT lais_equipe_membros_ordem_nao_negativa CHECK (ordem >= 0)
);

CREATE INDEX IF NOT EXISTS idx_lais_equipe_membros_user ON social_wiring.lais_equipe_membros (org_id, user_id);

-- -- 3. lais_distribuicao_cursor ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_distribuicao_cursor (
    equipe_id        uuid        PRIMARY KEY REFERENCES social_wiring.lais_equipes (id) ON DELETE CASCADE,
    org_id           uuid        NOT NULL,
    ultimo_user_id   uuid,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- -- 4. lais_atribuicoes ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_atribuicoes (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid        NOT NULL,
    contato_id  uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    equipe_id   uuid        REFERENCES social_wiring.lais_equipes (id) ON DELETE SET NULL,
    user_id     uuid        NOT NULL,
    motivo      text        NOT NULL DEFAULT 'handoff',
    criterio    text        NOT NULL DEFAULT 'round_robin',
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_atribuicoes_motivo_valido CHECK (motivo IN ('handoff', 'qualificacao', 'envio')),
    CONSTRAINT lais_atribuicoes_criterio_valido CHECK (criterio IN ('round_robin', 'ultimo_responsavel'))
);

COMMENT ON TABLE social_wiring.lais_atribuicoes IS
    'Append-only log of attendant picks (migration 276): the denominator of the team "distribuicao" metric and the '
    'start of the TPR (first human reply) measurement.';

CREATE INDEX IF NOT EXISTS idx_lais_atribuicoes_org_user ON social_wiring.lais_atribuicoes (org_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lais_atribuicoes_contato ON social_wiring.lais_atribuicoes (contato_id, created_at DESC);

-- -- 5. RLS: select own org + service_role -------------------------------------------------------
ALTER TABLE social_wiring.lais_equipes             ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_equipe_membros      ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_distribuicao_cursor ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_atribuicoes         ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_equipes_select_own_org" ON social_wiring.lais_equipes;
CREATE POLICY "lais_equipes_select_own_org" ON social_wiring.lais_equipes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_equipes_service_role" ON social_wiring.lais_equipes;
CREATE POLICY "lais_equipes_service_role" ON social_wiring.lais_equipes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_equipe_membros_select_own_org" ON social_wiring.lais_equipe_membros;
CREATE POLICY "lais_equipe_membros_select_own_org" ON social_wiring.lais_equipe_membros
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_equipe_membros_service_role" ON social_wiring.lais_equipe_membros;
CREATE POLICY "lais_equipe_membros_service_role" ON social_wiring.lais_equipe_membros
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_distribuicao_cursor_select_own_org" ON social_wiring.lais_distribuicao_cursor;
CREATE POLICY "lais_distribuicao_cursor_select_own_org" ON social_wiring.lais_distribuicao_cursor
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_distribuicao_cursor_service_role" ON social_wiring.lais_distribuicao_cursor;
CREATE POLICY "lais_distribuicao_cursor_service_role" ON social_wiring.lais_distribuicao_cursor
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_atribuicoes_select_own_org" ON social_wiring.lais_atribuicoes;
CREATE POLICY "lais_atribuicoes_select_own_org" ON social_wiring.lais_atribuicoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_atribuicoes_service_role" ON social_wiring.lais_atribuicoes;
CREATE POLICY "lais_atribuicoes_service_role" ON social_wiring.lais_atribuicoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 6. status_pagina: Lais > Equipes (copies whatsapp_chat, like 273) ----------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('lais_equipes', 'Lais — Equipes')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
