-- ============================================================================
-- Migration 334 -- social_wiring: main broker vs partners, per-org fallback, and the in-house brokers refined from Vista (owner 2026-11-09)
-- ============================================================================
-- 1. imovel_corretores.papel (principal|parceiro) + principal_origem (vista|fallback) + nota. The MAIN broker is Vista's `CodigoCorretor`
--    (== `Agenciador`, `CorretorNome` = "<cod>:<nome>"); every other entry of the `Corretor` relation is a PARTNER. When no main is
--    determinable the org's configured fallback broker is used (ad_lead_intake_config) and the row says so.
-- 2. ad_lead_intake_config: per-org settings of the intake (the fallback main broker's Vista Codigo). Seeded for the One org with Gilson
--    Tangerino (Vista corretor 16) per the owner.
-- 3. lead_corretores gets the Vista roster fields (/corretores/listar): never deleted; a broker missing from Vista or marked Inativo is
--    MARKED (vista_status) and noticed (corretor_avisos, tipo corretor_sumiu_no_vista).
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible with the previous image (new columns are nullable / defaulted). Backend-only tables.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_corretores
    ADD COLUMN IF NOT EXISTS papel text NOT NULL DEFAULT 'parceiro' CONSTRAINT imovel_corretores_papel_check CHECK (papel IN ('principal', 'parceiro')),
    ADD COLUMN IF NOT EXISTS principal_origem text CONSTRAINT imovel_corretores_principal_origem_check CHECK (principal_origem IS NULL OR principal_origem IN ('vista', 'fallback')),
    ADD COLUMN IF NOT EXISTS nota text;

CREATE TABLE IF NOT EXISTS social_wiring.ad_lead_intake_config (
    org_id                                  uuid        PRIMARY KEY,
    corretor_principal_fallback_vista_codigo text,
    updated_at                              timestamptz NOT NULL DEFAULT now(),
    updated_by                              uuid
);
ALTER TABLE social_wiring.ad_lead_intake_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ad_lead_intake_config_service_role ON social_wiring.ad_lead_intake_config;
CREATE POLICY ad_lead_intake_config_service_role ON social_wiring.ad_lead_intake_config FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.ad_lead_intake_config FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.ad_lead_intake_config TO service_role;
COMMENT ON TABLE social_wiring.ad_lead_intake_config IS 'tier:org';

-- the One org: Gilson Tangerino (Vista corretor Codigo 16) is the main broker when Vista does not say (owner 2026-11-09)
INSERT INTO social_wiring.ad_lead_intake_config (org_id, corretor_principal_fallback_vista_codigo)
VALUES ('fd169d29-4d0a-4b04-9a5e-25e69407614d', '16')
ON CONFLICT (org_id) DO NOTHING;

ALTER TABLE social_wiring.lead_corretores
    ADD COLUMN IF NOT EXISTS vista_nome text,
    ADD COLUMN IF NOT EXISTS nome_completo text,
    ADD COLUMN IF NOT EXISTS email text,
    ADD COLUMN IF NOT EXISTS celular text,
    ADD COLUMN IF NOT EXISTS creci text,
    ADD COLUMN IF NOT EXISTS equipe text,
    ADD COLUMN IF NOT EXISTS codigo_equipe text,
    ADD COLUMN IF NOT EXISTS gerente boolean,
    ADD COLUMN IF NOT EXISTS agenciador boolean,
    ADD COLUMN IF NOT EXISTS eh_corretor boolean,
    ADD COLUMN IF NOT EXISTS atuacao_venda boolean,
    ADD COLUMN IF NOT EXISTS atuacao_locacao boolean,
    ADD COLUMN IF NOT EXISTS data_saida date,
    ADD COLUMN IF NOT EXISTS vista_status text CONSTRAINT lead_corretores_vista_status_check CHECK (vista_status IS NULL OR vista_status IN ('ativo', 'inativo', 'ausente')),
    ADD COLUMN IF NOT EXISTS vista_sincronizado_em timestamptz,
    ADD COLUMN IF NOT EXISTS vista_ausente_em timestamptz;

CREATE TABLE IF NOT EXISTS social_wiring.corretor_avisos (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    corretor_id    uuid        NOT NULL REFERENCES social_wiring.lead_corretores (id) ON DELETE CASCADE,
    vista_codigo   text,
    tipo           text        NOT NULL CONSTRAINT corretor_avisos_tipo_check CHECK (tipo IN ('corretor_sumiu_no_vista')),
    status         text        NOT NULL DEFAULT 'pendente' CONSTRAINT corretor_avisos_status_check CHECK (status IN ('pendente', 'resolvida', 'ignorada')),
    notas          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    notificado_em  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    resolvido_em   timestamptz,
    resolvido_por  uuid
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_corretor_avisos_aberto ON social_wiring.corretor_avisos (org_id, corretor_id, tipo) WHERE status = 'pendente';
CREATE INDEX IF NOT EXISTS idx_sw_corretor_avisos_lista ON social_wiring.corretor_avisos (org_id, status, created_at DESC);
ALTER TABLE social_wiring.corretor_avisos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS corretor_avisos_service_role ON social_wiring.corretor_avisos;
CREATE POLICY corretor_avisos_service_role ON social_wiring.corretor_avisos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.corretor_avisos FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.corretor_avisos TO service_role;
COMMENT ON TABLE social_wiring.corretor_avisos IS 'tier:org';
