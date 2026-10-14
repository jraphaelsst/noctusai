-- ============================================================================
-- Migration 255 -- social_wiring: per-org public privacy notice for Julia
-- ============================================================================
-- WHY
-- ---
-- Julia (SW's lead-facing WhatsApp agent) discloses on the first turn and links
-- the org's OWN privacy notice (the org is the LGPD controller, not NoctusAI).
-- One row per org; `secoes` uses the seed consent shape (DocSection[]).
-- The public page is served by the backend's service client returning ONLY the
-- notice fields -- no anon policy: RLS stays closed to anon.
--
-- Contract: products/social-wiring/projects/lais/specs/julia-agent-contract.md
-- section 11.2. FORWARD-ONLY, IDEMPOTENT. No trigger; the slug UNIQUE is a
-- constraint, covered by the API tests (slug uniqueness).
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.lais_aviso_privacidade (
    org_id            UUID PRIMARY KEY,
    slug              TEXT NOT NULL UNIQUE,
    titulo            TEXT,
    empresa_nome      TEXT,
    contato_email     TEXT,
    contato_whatsapp  TEXT,
    secoes            JSONB NOT NULL,
    mensagem_inicial  TEXT NOT NULL,
    versao            INTEGER NOT NULL DEFAULT 1,
    atualizado_em     TIMESTAMPTZ,
    atualizado_por    UUID
);

COMMENT ON TABLE social_wiring.lais_aviso_privacidade IS
    'Per-org public privacy notice for the Lais/Julia agent (migration 255). '
    'secoes = seed DocSection[]; slug is generated once and not editable.';

ALTER TABLE social_wiring.lais_aviso_privacidade ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_aviso_privacidade_select_own_org"
    ON social_wiring.lais_aviso_privacidade;
CREATE POLICY "lais_aviso_privacidade_select_own_org"
    ON social_wiring.lais_aviso_privacidade
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "lais_aviso_privacidade_service_role"
    ON social_wiring.lais_aviso_privacidade;
CREATE POLICY "lais_aviso_privacidade_service_role"
    ON social_wiring.lais_aviso_privacidade
    FOR ALL TO service_role USING (true) WITH CHECK (true);
