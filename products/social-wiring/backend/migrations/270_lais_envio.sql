-- ============================================================================
-- Migration 270 -- social_wiring: Lais wave 3 "Envio ao SW" (rules, policies,
--                  deliveries) + Lais > Leads support columns + status_pagina
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md
--   section 5 (wave 3) + specs/page-map-v2.md 29 (wizard) / 27 (Envio ao CRM) / 59.0 a8.
--
--   lais_envio_regras      the send criteria per operation. `grupos` = [[{campo, operador, valor}]]:
--                          groups are OR'd, the criteria of one group AND'd. `operacao` is
--                          compra | aluguel (checkbox "Configuracoes diferentes para compra e aluguel"
--                          on) or ambas (off): at most ONE rule row per (org, operacao).
--   lais_envio_politicas   one row per org: leads frios (switch + interval / next-morning window),
--                          potenciais captacoes (enviar | notificar), WhatsApp invalido, pesquisa.
--   lais_envio_entregas    one row per send attempt (ledger): trigger, outcome, the SW lead it
--                          produced. An `erro` row always names its error.
--   lais_contatos          + campanha_origem / anuncio_origem (the "Filtro de leads" fields of 59.0 a8).
--
-- RLS: select-own-org + service_role policy per table (pattern 267); writes go through the backend
-- service client only. NO SECURITY DEFINER function in this file.
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: core 070 (current_org_id_for), 014 (status_pagina),
-- 267 (lais_contatos), 025 (leads). The tech-lead applies it with noctus.dev.migrate_product.
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

-- -- 1. lais_envio_regras ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_envio_regras (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    operacao   text        NOT NULL,
    grupos     jsonb       NOT NULL DEFAULT '[]'::jsonb,
    versao     integer     NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_envio_regras_operacao_valida CHECK (operacao IN ('compra', 'aluguel', 'ambas')),
    CONSTRAINT lais_envio_regras_grupos_array CHECK (jsonb_typeof(grupos) = 'array')
);

COMMENT ON TABLE social_wiring.lais_envio_regras IS
    'Send criteria of the Lais "Envio de leads qualificados" wizard (migration 270, contract 5): '
    'grupos = [[{campo, operador, valor}]], groups OR, criteria AND.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_envio_regras_operacao_uq
    ON social_wiring.lais_envio_regras (org_id, operacao);

-- -- 2. lais_envio_politicas -------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_envio_politicas (
    org_id            uuid        PRIMARY KEY,
    frios             jsonb       NOT NULL DEFAULT '{"ativo": false}'::jsonb,
    captacoes         text        NOT NULL DEFAULT 'notificar',
    whatsapp_invalido boolean     NOT NULL DEFAULT false,
    pesquisa          boolean     NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_envio_politicas_frios_objeto CHECK (jsonb_typeof(frios) = 'object'),
    CONSTRAINT lais_envio_politicas_captacoes_valida CHECK (captacoes IN ('enviar', 'notificar'))
);

COMMENT ON TABLE social_wiring.lais_envio_politicas IS
    'Per-org policies of the Envio ao CRM tab (migration 270, page-map 27): leads frios, captacoes, '
    'WhatsApp invalido, pesquisa com clientes.';

-- -- 3. lais_envio_entregas --------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_envio_entregas (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    contato_id uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    gatilho    text        NOT NULL,
    status     text        NOT NULL,
    erro       text,
    lead_id    uuid        REFERENCES social_wiring.leads (id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_envio_entregas_gatilho_valido
        CHECK (gatilho IN ('qualificado', 'visita', 'frio', 'captacao', 'invalido', 'manual')),
    CONSTRAINT lais_envio_entregas_status_valido CHECK (status IN ('ok', 'erro')),
    CONSTRAINT lais_envio_entregas_erro_exige_mensagem CHECK (status = 'ok' OR erro IS NOT NULL)
);

COMMENT ON TABLE social_wiring.lais_envio_entregas IS
    'Ledger of every attempt to send a lais_contato to the SW CRM (migration 270, contract 5).';

CREATE INDEX IF NOT EXISTS idx_lais_envio_entregas_contato
    ON social_wiring.lais_envio_entregas (org_id, contato_id, created_at DESC);

-- -- 4. lais_contatos: origin campaign / ad (Filtro de leads, page-map 59.0 a8) ------
ALTER TABLE social_wiring.lais_contatos ADD COLUMN IF NOT EXISTS campanha_origem text;
ALTER TABLE social_wiring.lais_contatos ADD COLUMN IF NOT EXISTS anuncio_origem  text;

-- the Lais > Leads list is ordered by first contact, newest first
CREATE INDEX IF NOT EXISTS idx_lais_contatos_org_criado
    ON social_wiring.lais_contatos (org_id, created_at DESC);

-- -- 5. RLS ------------------------------------------------------------------------
ALTER TABLE social_wiring.lais_envio_regras    ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_envio_politicas ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_envio_entregas  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_envio_regras_select_own_org" ON social_wiring.lais_envio_regras;
CREATE POLICY "lais_envio_regras_select_own_org" ON social_wiring.lais_envio_regras
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_envio_regras_service_role" ON social_wiring.lais_envio_regras;
CREATE POLICY "lais_envio_regras_service_role" ON social_wiring.lais_envio_regras
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_envio_politicas_select_own_org" ON social_wiring.lais_envio_politicas;
CREATE POLICY "lais_envio_politicas_select_own_org" ON social_wiring.lais_envio_politicas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_envio_politicas_service_role" ON social_wiring.lais_envio_politicas;
CREATE POLICY "lais_envio_politicas_service_role" ON social_wiring.lais_envio_politicas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_envio_entregas_select_own_org" ON social_wiring.lais_envio_entregas;
CREATE POLICY "lais_envio_entregas_select_own_org" ON social_wiring.lais_envio_entregas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_envio_entregas_service_role" ON social_wiring.lais_envio_entregas;
CREATE POLICY "lais_envio_entregas_service_role" ON social_wiring.lais_envio_entregas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 6. status_pagina: Lais > Envio + Lais > Leads (copies whatsapp_chat, like 259) ---
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_envio', 'Lais — Envio de leads qualificados'),
          ('lais_leads', 'Lais — Leads')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
