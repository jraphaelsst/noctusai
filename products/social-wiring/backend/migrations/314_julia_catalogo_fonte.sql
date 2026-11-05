-- ============================================================================
-- Migration 314 -- social_wiring: per-org source of Julia's property catalog (julia-v3, CONTRACT 12.7)
-- ============================================================================
-- WHY
-- ---
-- Julia's listing tools (buscar_imoveis / imovel_campanha / detalhes_imovel) read the `imoveis` mirror, which lags Vista
-- (sync cadence, unpublished-then-republished listings). Owner 2026-11-03: Julia reads Vista LIVE for the One org.
--
-- WHAT
--   julia_catalogo_config: one row per org, `fonte` = 'vista' (live Vista via the seed integration) | 'espelho' (the
--   `imoveis` mirror, today's behaviour). A missing row means 'espelho' -- nothing changes for any org until an admin
--   (or the operator after deploy) flips it. Backend-only like every julia_* table (migration 289): RLS on, service role
--   only, no grant to browser roles.
--
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.julia_catalogo_config (
    org_id      uuid        PRIMARY KEY,
    fonte       text        NOT NULL DEFAULT 'espelho' CHECK (fonte IN ('vista', 'espelho')),
    updated_by  uuid,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.julia_catalogo_config IS
    'Per-org source of Julia''s property catalog (migration 314): vista = live Vista API, espelho = the imoveis mirror. '
    'A missing row means espelho. Backend-only.';

ALTER TABLE social_wiring.julia_catalogo_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS julia_catalogo_config_service_role ON social_wiring.julia_catalogo_config;
CREATE POLICY julia_catalogo_config_service_role ON social_wiring.julia_catalogo_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.julia_catalogo_config FROM PUBLIC, anon, authenticated;
