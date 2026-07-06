-- 022_app_integration_config.sql — app-wide encrypted key→value config.
--
-- Backs `noctusai_lib.security.app_config.RealAppConfigStore` (seed Wave 1)
-- — a single row per config KEY (not per-org, unlike credentials /
-- mailchimp_connections / integration_accounts). Wave 2 uses this for
-- the Meta App ID / App Secret pair (`meta_app_id` / `meta_app_secret`,
-- see `noctusai_lib.security.app_config.META_APP_ID_KEY` /
-- `META_APP_SECRET_KEY`) so an admin can set them in-app (Settings) with
-- the env vars (`META_APP_ID` / `META_APP_SECRET`) as fallback, instead
-- of requiring a container redeploy to rotate a Meta app credential.
--
-- RLS: ON, service_role ALL only. Deliberately NO authenticated policy —
-- this is app-admin-only config, read/written exclusively via the admin
-- client (never exposed through PostgREST to an authenticated end-user
-- session; the product's `PUT /api/settings/meta-app` /
-- `GET /api/settings/meta-app/status` endpoints are the only sanctioned
-- read/write path, both admin-gated).

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.app_integration_config (
    key             TEXT PRIMARY KEY,
    encrypted_value TEXT NOT NULL,              -- Fernet(value) — TEXT not bytea
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.app_integration_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "app_integration_config_service_role" ON social_wiring.app_integration_config;
CREATE POLICY "app_integration_config_service_role" ON social_wiring.app_integration_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);
