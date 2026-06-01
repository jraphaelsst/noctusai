-- 007_clients.sql — canonical clients entity (folds mc_brand_owners).
--
-- Project: social-wiring-multi-account-clients (2026-06-01). Promotes the
-- branding system's mc_brand_owners into a first-class `clients` table so
-- the same entity can also anchor per-account integration channels.
--
-- NOTE: `security_invoker = true` on the compat view requires PG15+. The
-- tech-lead will verify the live PG version before applying; if it must
-- change, that's their call.
--
-- Forward-only + idempotent. Apply to the noctusai Supabase
-- (social_wiring schema) at deploy.
--
-- Deferred removals (tracked for a follow-up migration):
--   - DROP TABLE social_wiring.mc_brand_owners_legacy (after all reads
--     confirmed to go through the clients table / compat view)
--   - DROP COLUMN social_wiring.mc_brand_kits.brand_owner_id (after
--     client_id column has been backfilled and callers migrated)
--   - DROP INDEX mc_brand_kits_owner_slug_uniq (superseded by
--     mc_brand_kits_client_slug_uniq below)

SET search_path = social_wiring, public;

-- ── 1. clients table ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS social_wiring.clients (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'real_estate_agent',
    notes       TEXT,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);

ALTER TABLE social_wiring.clients ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clients_select_own_org" ON social_wiring.clients;
CREATE POLICY "clients_select_own_org"
    ON social_wiring.clients
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

DROP POLICY IF EXISTS "clients_insert_own_org" ON social_wiring.clients;
CREATE POLICY "clients_insert_own_org"
    ON social_wiring.clients
    FOR INSERT TO authenticated
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

DROP POLICY IF EXISTS "clients_update_own_org" ON social_wiring.clients;
CREATE POLICY "clients_update_own_org"
    ON social_wiring.clients
    FOR UPDATE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

DROP POLICY IF EXISTS "clients_delete_own_org" ON social_wiring.clients;
CREATE POLICY "clients_delete_own_org"
    ON social_wiring.clients
    FOR DELETE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

DROP POLICY IF EXISTS "clients_service_role" ON social_wiring.clients;
CREATE POLICY "clients_service_role"
    ON social_wiring.clients
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS ix_sw_clients_org
    ON social_wiring.clients (org_id);

-- ── 2. UUID-preserving backfill from mc_brand_owners ─────────────────────────

INSERT INTO social_wiring.clients
    (id, org_id, slug, name, kind, notes, created_by, created_at, updated_at)
SELECT
    id, org_id, slug, name, kind, notes, created_by, created_at, updated_at
FROM social_wiring.mc_brand_owners
ON CONFLICT (id) DO NOTHING;

-- ── 3. mc_brand_kits client_id column + backfill ────────────────────────────

ALTER TABLE social_wiring.mc_brand_kits
    ADD COLUMN IF NOT EXISTS client_id UUID
        REFERENCES social_wiring.clients(id) ON DELETE SET NULL;

UPDATE social_wiring.mc_brand_kits
    SET client_id = brand_owner_id
    WHERE client_id IS NULL
      AND brand_owner_id IS NOT NULL;

-- Catalog idempotency under the new canonical key; the legacy
-- mc_brand_kits_owner_slug_uniq index is NOT dropped here — deferred.
CREATE UNIQUE INDEX IF NOT EXISTS mc_brand_kits_client_slug_uniq
    ON social_wiring.mc_brand_kits (org_id, client_id, slug)
    WHERE slug IS NOT NULL;

-- ── 4. Guarded rename + compat view ─────────────────────────────────────────

DO $$ BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'social_wiring'
          AND table_name   = 'mc_brand_owners'
          AND table_type   = 'BASE TABLE'
    ) THEN
        ALTER TABLE social_wiring.mc_brand_owners RENAME TO mc_brand_owners_legacy;
    END IF;
END $$;

-- Transparent compat view so existing callers reading mc_brand_owners
-- continue to work unmodified. security_invoker = true means the view
-- is evaluated under the CALLER's RLS context (PG15+ required).
CREATE OR REPLACE VIEW social_wiring.mc_brand_owners
    WITH (security_invoker = true)
AS
    SELECT id, org_id, slug, name, kind, notes, created_by, created_at, updated_at
    FROM social_wiring.clients;

GRANT SELECT ON social_wiring.mc_brand_owners TO authenticated, service_role;
