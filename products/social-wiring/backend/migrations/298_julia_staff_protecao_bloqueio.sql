-- ============================================================================
-- Migration 298 -- social_wiring: Julia on a public number -- org staff registry, abuse limits, blocklist (owner 2026-10-21)
-- ============================================================================
-- WHY
-- ---
-- Julia goes live on a public WhatsApp number. Owner (2026-10-21, verbatim): "staff will be set in-org. only those registered on
-- the sw are staff and their roles... opt-outs and staff are org-level configs... by default, if not in the staff list, it's an
-- incoming lead." and "please set limits and rates limitings and more so we protect our operation... from someone trying to
-- break our system on purpose".
--
-- WHAT (three org-level configs, all backend-only like every julia_* table -- migration 289)
--   1. julia_staff: THE per-org staff list (who is staff, their WhatsApp number(s), their role). A message from a number that is
--      NOT here is an incoming lead, always. Operator-role numbers are mirrored into whatsapp_connections.authorized_numbers by
--      the application (the One Chat operator path keeps reading that column; this table is the single place it is edited).
--      Backfilled from every connection's existing authorized_numbers (role `operador`), so nothing that is authorized today stops.
--   2. julia_protecao_config: one row per org with the abuse limits (per-number inbound rate, per-chat / per-connection media AI
--      budget, automatic-block thresholds) and the operator-editable lead document prompt. A missing row = the code defaults.
--   3. julia_numeros_bloqueados: the per-org blocklist (manual or automatic-temporary): number, reason, who, when, expiry,
--      unblock record. Inbound from a blocked number is recorded and never reaches agents or an AI call.
--   4. status_pagina rows for the two new pages (copying julia_leads, as 252/259/273/297).
--
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function. The tech-lead applies it with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.whatsapp_connections') IS NULL OR to_regclass('social_wiring.status_pagina') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.whatsapp_connections + status_pagina -- apply the earlier migrations first';
  END IF;
END
$guard$;

-- 1. staff ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_staff (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid        NOT NULL,
    user_id     uuid,
    nome        text        NOT NULL CHECK (char_length(btrim(nome)) BETWEEN 1 AND 120),
    papel       text        NOT NULL CHECK (papel IN ('admin', 'operador', 'corretor', 'atendente', 'outro')),
    telefone    text        CHECK (telefone ~ '^[0-9]{10,15}$'),
    ativo       boolean     NOT NULL DEFAULT true,
    criado_por  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    -- a staff entry that can be neither matched to a number nor to a user identifies no one
    CONSTRAINT julia_staff_identificavel CHECK (telefone IS NOT NULL OR user_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS julia_staff_org_telefone_uk
    ON social_wiring.julia_staff (org_id, telefone) WHERE telefone IS NOT NULL;
CREATE INDEX IF NOT EXISTS julia_staff_org_user_idx
    ON social_wiring.julia_staff (org_id, user_id) WHERE user_id IS NOT NULL;

COMMENT ON TABLE social_wiring.julia_staff IS
    'THE org staff list (migration 298): only a number registered here is staff; any other inbound is a lead. papel decides the route '
    'of a staff message on Julia''s public line (admin/operador -> One Chat operator path; the rest -> logged + operator notice). Backend-only.';

-- 2. abuse limits -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_protecao_config (
    org_id                    uuid        PRIMARY KEY,
    entrada_limite            integer     NOT NULL DEFAULT 20  CHECK (entrada_limite BETWEEN 1 AND 500),
    entrada_janela_s          integer     NOT NULL DEFAULT 60  CHECK (entrada_janela_s BETWEEN 10 AND 3600),
    midia_limite_chat_dia     integer     NOT NULL DEFAULT 10  CHECK (midia_limite_chat_dia BETWEEN 0 AND 10000),
    midia_limite_conexao_dia  integer     NOT NULL DEFAULT 200 CHECK (midia_limite_conexao_dia BETWEEN 0 AND 100000),
    bloqueio_auto_ativo       boolean     NOT NULL DEFAULT true,
    bloqueio_auto_limiar      integer     NOT NULL DEFAULT 3   CHECK (bloqueio_auto_limiar BETWEEN 1 AND 100),
    bloqueio_auto_janela_min  integer     NOT NULL DEFAULT 60  CHECK (bloqueio_auto_janela_min BETWEEN 1 AND 1440),
    bloqueio_auto_duracao_min integer     NOT NULL DEFAULT 1440 CHECK (bloqueio_auto_duracao_min BETWEEN 1 AND 43200),
    prompt_documento_lead     text        CHECK (prompt_documento_lead IS NULL OR char_length(prompt_documento_lead) BETWEEN 20 AND 4000),
    atualizado_por            uuid,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.julia_protecao_config IS
    'Per-org abuse limits + the lead document prompt (migration 298). A missing row means the code defaults (visible in the UI). Backend-only.';

-- 3. blocklist ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_numeros_bloqueados (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid        NOT NULL,
    numero           text        NOT NULL CHECK (numero ~ '^[0-9]{10,15}$' OR numero ~ '^[0-9]{6,20}@lid$'),
    motivo           text        NOT NULL CHECK (char_length(btrim(motivo)) BETWEEN 1 AND 300),
    origem           text        NOT NULL CHECK (origem IN ('manual', 'automatico')),
    gatilho          text        NOT NULL DEFAULT 'manual'
                     CHECK (gatilho IN ('manual', 'entrada_flood', 'limite_taxa', 'loop_detectado')),
    criado_por       uuid,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    expira_em        timestamptz,
    ativo            boolean     NOT NULL DEFAULT true,
    desbloqueado_por uuid,
    desbloqueado_em  timestamptz,
    notificacao_status text      NOT NULL DEFAULT 'nao_aplica'
                     CHECK (notificacao_status IN ('nao_aplica', 'enviada', 'falhou')),
    -- an automatic block is always TEMPORARY
    CONSTRAINT julia_numeros_bloqueados_auto_expira CHECK (origem <> 'automatico' OR expira_em IS NOT NULL),
    -- an automatic block has a trigger; a manual one is by a user
    CONSTRAINT julia_numeros_bloqueados_origem_gatilho CHECK (
        (origem = 'manual' AND gatilho = 'manual') OR (origem = 'automatico' AND gatilho <> 'manual')
    ),
    -- a lifted block records the lift (the rows are history, never deleted)
    CONSTRAINT julia_numeros_bloqueados_desbloqueio CHECK (ativo OR desbloqueado_em IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS julia_numeros_bloqueados_ativo_uk
    ON social_wiring.julia_numeros_bloqueados (org_id, numero) WHERE ativo;
CREATE INDEX IF NOT EXISTS julia_numeros_bloqueados_org_idx
    ON social_wiring.julia_numeros_bloqueados (org_id, ativo, criado_em DESC);

COMMENT ON TABLE social_wiring.julia_numeros_bloqueados IS
    'Per-org number blocklist (migration 298): manual (admin, reason, who/when) or automatic-temporary (abuse thresholds). A blocked '
    'number''s inbound is recorded and never reaches agents or an AI call. Rows are history: a lift sets ativo=false. Backend-only.';

-- RLS: service role only (the julia_* lockdown, migration 289)
DO $rls$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['julia_staff', 'julia_protecao_config', 'julia_numeros_bloqueados'] LOOP
    EXECUTE format('ALTER TABLE social_wiring.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_service_role', t);
    EXECUTE format('CREATE POLICY %I ON social_wiring.%I FOR ALL TO service_role USING (true) WITH CHECK (true)', t || '_service_role', t);
    EXECUTE format('REVOKE ALL ON social_wiring.%I FROM PUBLIC, anon, authenticated', t);
  END LOOP;
END
$rls$;

-- 4. backfill: every number that is authorized today stays authorized (as an operator) --------------------------------
-- Phone-shaped entries only; a LID literal (`<digits>@lid`) has no phone and stays in authorized_numbers, where the
-- application mirror preserves it.
INSERT INTO social_wiring.julia_staff (org_id, nome, papel, telefone)
SELECT DISTINCT ON (c.org_id, d.digitos)
       c.org_id, 'Operador importado (final ' || right(d.digitos, 4) || ')', 'operador', d.digitos
  FROM social_wiring.whatsapp_connections c
 CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(c.authorized_numbers) = 'array' THEN c.authorized_numbers ELSE '[]'::jsonb END) AS e(valor)
 CROSS JOIN LATERAL (SELECT regexp_replace(e.valor, '[^0-9]', '', 'g') AS digitos) AS d
 WHERE e.valor ~ '^\s*\+?[0-9][0-9 ()-]{8,20}$'
   AND d.digitos ~ '^[0-9]{10,15}$'
ON CONFLICT DO NOTHING;

-- 5. status_pagina: Julia > Equipe (staff) and Julia > Proteção (copies julia_leads) ---------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('julia_equipe_whatsapp', 'Julia — Equipe (staff do WhatsApp)'),
               ('julia_protecao', 'Julia — Proteção (limites e bloqueios)')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'julia_leads'
ON CONFLICT (nome_pagina) DO NOTHING;
