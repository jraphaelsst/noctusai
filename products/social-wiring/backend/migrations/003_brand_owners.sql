-- 003_brand_owners.sql — the agent/client layer of the branding system.
--
-- Project: social-wiring-branding-catalog (2026-05-24). Agency model: ONE org
-- manages many real-estate AGENTS (mc_brand_owners) as clients; each agent has
-- 1+ BRANDINGS (mc_brand_kits). Adds the owner layer + catalog-idempotency keys.
--
-- Forward-only + idempotent (001/002 already in prod). RLS org-scoped, mirrors
-- mc_brand_kits. Apply to the noctusai Supabase (social_wiring schema) at deploy.

-- The agent / brand owner — the real-estate agent (or any brand owner) whose
-- brandings this org manages. Org-scoped; `slug` is the stable catalog key.
CREATE TABLE IF NOT EXISTS social_wiring.mc_brand_owners (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'real_estate_agent',
    notes       TEXT,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);

ALTER TABLE social_wiring.mc_brand_owners ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "mc_brand_owners_select_own_org" ON social_wiring.mc_brand_owners;
CREATE POLICY "mc_brand_owners_select_own_org" ON social_wiring.mc_brand_owners
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.mc_brand_owners;
CREATE POLICY "service_role_bypass" ON social_wiring.mc_brand_owners
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- A branding (mc_brand_kits row) belongs to an owner (NULL = legacy/org-level
-- kit, back-compat). `slug` is the per-owner catalog key for idempotent seeds.
ALTER TABLE social_wiring.mc_brand_kits
    ADD COLUMN IF NOT EXISTS brand_owner_id UUID
        REFERENCES social_wiring.mc_brand_owners(id) ON DELETE SET NULL;

ALTER TABLE social_wiring.mc_brand_kits
    ADD COLUMN IF NOT EXISTS slug TEXT;

-- Catalog idempotency: at most one branding per (org, owner, slug). Partial so
-- existing slug-less kits are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS mc_brand_kits_owner_slug_uniq
    ON social_wiring.mc_brand_kits (org_id, brand_owner_id, slug)
    WHERE slug IS NOT NULL;
