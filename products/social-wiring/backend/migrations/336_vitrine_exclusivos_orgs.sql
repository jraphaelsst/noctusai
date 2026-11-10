-- ============================================================================
-- Migration 336 -- social_wiring: opt-in config for the exclusives showcase feed
-- (owner 2026-11-09: the exclusividades site consumes OUR mirror, not Vista; reads are key-authenticated, 1 key = 1 consumer)
-- ============================================================================
-- WHY
-- ---
-- `GET /api/vitrine/exclusivos` serves an org's exclusive listings to ONE server-side consumer holding a `noc_` product
-- token (scope `vitrine:exclusivos:read`, minted by an org admin through the existing `POST /api/settings/api-tokens`;
-- stored hashed, revocable, named, `last_used_at`). The token binds the org; this table is the second lock: an org is
-- served ONLY if it has an active row here (default deny). `site_url` is the agency's own site (listing links are built
-- on it).
--
-- Backend-only (service role); tier:service. FORWARD-ONLY, IDEMPOTENT, NO SECURITY DEFINER function.
-- Opt-in One after deploy (not part of this migration):
--   INSERT INTO social_wiring.vitrine_exclusivos_orgs (org_id, site_url)
--   VALUES ('fd169d29-4d0a-4b04-9a5e-25e69407614d', 'https://oneconsultoriaimobiliaria.com.br')
--   ON CONFLICT (org_id) DO NOTHING;
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.vitrine_exclusivos_orgs (
    org_id      uuid        PRIMARY KEY,
    site_url    text        NOT NULL CHECK (site_url ~ '^https://[^/]+$'),
    ativo       boolean     NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.vitrine_exclusivos_orgs IS 'tier:service';

ALTER TABLE social_wiring.vitrine_exclusivos_orgs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vitrine_exclusivos_orgs_service_role ON social_wiring.vitrine_exclusivos_orgs;
CREATE POLICY vitrine_exclusivos_orgs_service_role ON social_wiring.vitrine_exclusivos_orgs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.vitrine_exclusivos_orgs FROM PUBLIC, anon, authenticated;
GRANT ALL ON social_wiring.vitrine_exclusivos_orgs TO service_role;
