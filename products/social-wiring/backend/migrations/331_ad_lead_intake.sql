-- ============================================================================
-- Migration 331 -- social_wiring: ad-lead intake (Meta form lead -> property, both ways)
-- ============================================================================
-- WHY
-- ---
-- A Meta lead-form lead names its property in the `REF` answer. Until now the lead landed, the card spawned and a
-- cliente interesse was written, but: `leads.imovel_ref_id` stayed NULL, the interesse carried only `meta_ads_lead_id`
-- (never `lead_id`), the property was never refreshed from Vista at intake, the property's Vista corretor lived only
-- inside `imoveis.vista_raw`, and the form's qualification answers (budget / buying stage / region) stayed free text in
-- `observacoes`. CONTRACT: products/social-wiring/projects/ad-lead-intake-CONTRACT.md.
--
-- WHAT
--   1. lead_imovel_intakes        one row per lead: how the intake went (ok | imovel_nao_encontrado | sem_codigo |
--                                 pendente_retry | falhou), attempts, last error, the result summary. A Vista outage is a
--                                 durable, RETRYABLE row here -- never a lost lead, never a silent skip.
--   2. imovel_corretores          the property's Vista corretores as queryable rows, keyed by the Vista corretor Codigo
--                                 (the base of the later corretor-performance slice). `corretor_id` = the SW corretor the
--                                 Vista one resolves to (NULL when unmatched).
--   3. lead_corretor_divergencias "record and warn me": the lead's corretor differs from the property's Vista corretor(s).
--                                 Queryable + resolved by a human; the in-app warning goes through core notifications.
--   4. lead_corretores.vista_codigo  the Vista corretor Codigo of an SW corretor (nullable; unique per org when set).
--   5. leads.qualificacao_form    jsonb: the form's budget / stage / region answers, structured.
--   6. cliente_imovel_interesses: drop CHECK `lead_unico` so an interesse can carry lead_id AND meta_ads_lead_id.
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible with the previous image (only ADD COLUMN / new tables). No SECURITY
-- DEFINER function. Backend-only: RLS on, service role only, no browser-role grant.
-- ============================================================================

SET search_path = social_wiring, public;

-- 1. intake ledger ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lead_imovel_intakes (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid        NOT NULL,
    lead_id            uuid        NOT NULL REFERENCES social_wiring.leads (id) ON DELETE CASCADE,
    meta_ads_lead_id   text,
    codigo_canonical   text,
    status             text        NOT NULL DEFAULT 'pendente_retry'
                                   CHECK (status IN ('ok', 'imovel_nao_encontrado', 'sem_codigo', 'pendente_retry', 'falhou')),
    tentativas         integer     NOT NULL DEFAULT 0,
    ultimo_erro        text,
    resultado          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    concluido_em       timestamptz,
    CONSTRAINT uq_sw_lead_imovel_intakes_lead UNIQUE (org_id, lead_id)
);

CREATE INDEX IF NOT EXISTS idx_sw_lead_imovel_intakes_pendentes
    ON social_wiring.lead_imovel_intakes (org_id, updated_at)
    WHERE status IN ('pendente_retry', 'falhou');
CREATE INDEX IF NOT EXISTS idx_sw_lead_imovel_intakes_codigo
    ON social_wiring.lead_imovel_intakes (org_id, codigo_canonical);

-- 2. the property's Vista corretores ----------------------------------------
ALTER TABLE social_wiring.lead_corretores ADD COLUMN IF NOT EXISTS vista_codigo text;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_lead_corretores_vista_codigo
    ON social_wiring.lead_corretores (org_id, vista_codigo) WHERE vista_codigo IS NOT NULL;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_corretores (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                uuid        NOT NULL,
    codigo_canonical      text        NOT NULL,
    chave                 text        NOT NULL,
    vista_corretor_codigo text,
    nome                  text,
    email                 text,
    fone                  text,
    ordem                 smallint    NOT NULL DEFAULT 0,
    corretor_id           uuid        REFERENCES social_wiring.lead_corretores (id) ON DELETE SET NULL,
    ativo                 boolean     NOT NULL DEFAULT true,
    visto_em              timestamptz NOT NULL DEFAULT now(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_sw_imovel_corretores UNIQUE (org_id, codigo_canonical, chave)
);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_corretores_vista
    ON social_wiring.imovel_corretores (org_id, vista_corretor_codigo) WHERE ativo;
CREATE INDEX IF NOT EXISTS idx_sw_imovel_corretores_corretor
    ON social_wiring.imovel_corretores (org_id, corretor_id) WHERE ativo AND corretor_id IS NOT NULL;

-- 3. lead corretor x property corretor divergence ---------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lead_corretor_divergencias (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   uuid        NOT NULL,
    lead_id                  uuid        NOT NULL REFERENCES social_wiring.leads (id) ON DELETE CASCADE,
    codigo_canonical         text        NOT NULL,
    lead_corretor_id         uuid        REFERENCES social_wiring.lead_corretores (id) ON DELETE SET NULL,
    lead_corretor_nome       text,
    imovel_corretores        jsonb       NOT NULL DEFAULT '[]'::jsonb,
    status                   text        NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'resolvida', 'ignorada')),
    nota                     text,
    notificado_em            timestamptz,
    resolvido_em             timestamptz,
    resolvido_por            uuid,
    created_at               timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_sw_lead_corretor_divergencias UNIQUE (org_id, lead_id, codigo_canonical)
);

CREATE INDEX IF NOT EXISTS idx_sw_lead_corretor_divergencias_status
    ON social_wiring.lead_corretor_divergencias (org_id, status, created_at DESC);

-- 4. the form's qualification answers, structured ---------------------------
ALTER TABLE social_wiring.leads ADD COLUMN IF NOT EXISTS qualificacao_form jsonb;

-- 4b. an interesse may carry BOTH lead links. 182 allowed at most ONE of (lead_id, meta_ads_lead_id); the ad-lead intake
--     needs lead_id ("leads interested in this property") on rows that already carry the Meta id, and `leads` is the
--     mapped twin of the Meta row, so both is coherent. Relaxing a CHECK is backward-compatible with the previous image.
ALTER TABLE social_wiring.cliente_imovel_interesses DROP CONSTRAINT IF EXISTS cliente_imovel_interesses_lead_unico;

-- 5. access: backend-only ----------------------------------------------------
ALTER TABLE social_wiring.lead_imovel_intakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.imovel_corretores ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lead_corretor_divergencias ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lead_imovel_intakes_service_role ON social_wiring.lead_imovel_intakes;
CREATE POLICY lead_imovel_intakes_service_role ON social_wiring.lead_imovel_intakes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS imovel_corretores_service_role ON social_wiring.imovel_corretores;
CREATE POLICY imovel_corretores_service_role ON social_wiring.imovel_corretores
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS lead_corretor_divergencias_service_role ON social_wiring.lead_corretor_divergencias;
CREATE POLICY lead_corretor_divergencias_service_role ON social_wiring.lead_corretor_divergencias
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE social_wiring.lead_imovel_intakes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.imovel_corretores FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.lead_corretor_divergencias FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.lead_imovel_intakes TO service_role;
GRANT ALL ON TABLE social_wiring.imovel_corretores TO service_role;
GRANT ALL ON TABLE social_wiring.lead_corretor_divergencias TO service_role;

COMMENT ON TABLE social_wiring.lead_imovel_intakes IS 'tier:org';
COMMENT ON TABLE social_wiring.imovel_corretores IS 'tier:org';
COMMENT ON TABLE social_wiring.lead_corretor_divergencias IS 'tier:org';
COMMENT ON COLUMN social_wiring.leads.qualificacao_form IS
    'The Meta form''s qualification answers, structured: {orcamento_max, orcamento_texto, fase_compra_texto, regiao_interesse}.';
