-- 024_integration_accounts_instagram_provider.sql — extend the
-- integration_accounts.provider CHECK constraint to allow 'instagram'.
--
-- Instagram Business Login (Instagram-Login model) is a SEPARATE provider
-- row from 'meta': it authenticates against its own Instagram App
-- ID/Secret (not the Facebook-Login app 'meta' uses) and its token chain
-- runs through api.instagram.com / graph.instagram.com rather than
-- graph.facebook.com. See
-- noctusai_lib.integrations.meta.instagram_login_adapter +
-- app/routers/integration_accounts_router.py's Instagram OAuth endpoints.
--
-- The original CHECK was declared inline in
-- 005_integration_accounts.sql (`provider TEXT NOT NULL CHECK (provider
-- IN (...))`) with no explicit constraint name, so Postgres assigned the
-- default `integration_accounts_provider_check`. Looked up dynamically
-- here (pg_constraint, not hardcoded) so a differently-named auto
-- constraint (e.g. a prior manual rename) never causes this migration to
-- silently no-op. Forward-only + idempotent — safe to re-run.

SET search_path = social_wiring, public;

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'social_wiring'
          AND rel.relname = 'integration_accounts'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%provider%'
    LOOP
        EXECUTE format(
            'ALTER TABLE social_wiring.integration_accounts DROP CONSTRAINT IF EXISTS %I',
            r.conname
        );
    END LOOP;
END $$;

ALTER TABLE social_wiring.integration_accounts
    ADD CONSTRAINT integration_accounts_provider_check
    CHECK (provider IN ('youtube', 'google_drive', 'gmail', 'meta', 'n8n', 'instagram'));
