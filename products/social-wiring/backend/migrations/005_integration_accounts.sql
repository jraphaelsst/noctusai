-- 005_integration_accounts.sql — per-org multi-account integration credentials.
--
-- Project: sw-multi-account-integrations (2026-05-29). Lets an operator
-- register MULTIPLE credential accounts per provider (e.g. two YouTube
-- channels, a personal + business Google Drive) and pick one at job-time
-- instead of having a single org-level credential row.
--
-- Design rule (memory feedback_seed_shape_vs_primitive_consume):
--   The seed CredentialStore is single-row-per-(org, provider) — that
--   shape does NOT fit multi-row-per-account. This table is the
--   product-local multi-account table. The ENCRYPTION PRIMITIVE (Fernet)
--   is still consumed from the seed via `credential_vault.require_fernet`
--   — zero crypto code lives here. Forward-only + idempotent.
--
-- WAHA is explicitly excluded — whatsapp_connections already handles that.
--
-- Apply to the noctusai Supabase (social_wiring schema) at deploy.

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.integration_accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL CHECK (provider IN ('youtube', 'google_drive', 'gmail', 'meta', 'n8n')),
    account_label       TEXT NOT NULL,
    encrypted_credential BYTEA NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_default          BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, provider, account_label)
);

-- Only one default per provider per org.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_integration_accounts_one_default
    ON social_wiring.integration_accounts (org_id, provider)
    WHERE is_default = true;

CREATE INDEX IF NOT EXISTS idx_sw_integration_accounts_org_provider
    ON social_wiring.integration_accounts (org_id, provider);

ALTER TABLE social_wiring.integration_accounts ENABLE ROW LEVEL SECURITY;

-- Org-scoped RLS: reads/writes only rows whose org_id matches the
-- JWT-embedded org_id claim (mirrors the credentials table RLS pattern).
DROP POLICY IF EXISTS "integration_accounts_select_own_org"
    ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_select_own_org"
    ON social_wiring.integration_accounts
    FOR SELECT TO authenticated
    USING (
        org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
    );

DROP POLICY IF EXISTS "integration_accounts_insert_own_org"
    ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_insert_own_org"
    ON social_wiring.integration_accounts
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
    );

DROP POLICY IF EXISTS "integration_accounts_update_own_org"
    ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_update_own_org"
    ON social_wiring.integration_accounts
    FOR UPDATE TO authenticated
    USING (
        org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
    );

DROP POLICY IF EXISTS "integration_accounts_delete_own_org"
    ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_delete_own_org"
    ON social_wiring.integration_accounts
    FOR DELETE TO authenticated
    USING (
        org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
    );

-- Service role bypass: backend uses admin client for multi-tenant writes.
DROP POLICY IF EXISTS "integration_accounts_service_role"
    ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_service_role"
    ON social_wiring.integration_accounts
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── updated_at trigger ──────────────────────────────────────────────────
-- Mirror the pattern used in whatsapp_connections (no explicit trigger
-- there) — keep updated_at fresh via the service layer's explicit SET.
-- A DB-side trigger would require PL/pgSQL which isn't guaranteed in all
-- Supabase tiers. The service layer sets updated_at = now() on every UPDATE.


-- ── Nav: seed "integrations" page status ───────────────────────────────
-- The FE route `/integrations` will be added by the frontend slice. Seed
-- the status_pagina row now so the route is visible once added.
-- `ON CONFLICT DO NOTHING` is idempotent — safe to re-run.
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('integrations', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
