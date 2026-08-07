-- ============================================================================
-- Migration 005 — adconnect.invitations (the table the seed team router needs)
--
-- WHY THIS EXISTS
-- ---------------
-- `products/adconnect/backend/app/main.py` mounts `standard_routers=[…,"team",…]`,
-- so the product exposes POST /api/team/invite, GET /api/team/invitations and
-- POST /api/team/accept. Every one of those addresses `<schema>.invitations` —
-- and adconnect never had that table. Each call therefore 500'd with
-- "Could not find the table 'adconnect.invitations' in the schema cache".
--
-- This went unnoticed because a SEPARATE bug (a schema-qualified table name in
-- the seed router, fixed 2026-08-07 in 0dc45027) produced a nearly identical
-- error for every product, so the genuinely-missing table read as the same
-- known issue. Fixing the router turned this one from "same message everyone
-- gets" into a real, product-specific gap.
--
-- SHAPE: identical to the canonical scaffold in
-- `products/seed/backend/migrations/001_seed.sql` + `002_invitations_accepted_columns.sql`,
-- collapsed into one CREATE since there is no existing table to alter.
-- Keeping the shape byte-identical to the seed matters: the seed team router
-- is shared code that reads these exact columns for all nine mounting products.
--
-- PREREQUISITE: public.current_org_id() (products/core/.../001_noctusai_core.sql).
-- IDEMPOTENT: IF NOT EXISTS throughout + DROP POLICY IF EXISTS before CREATE.
-- ============================================================================

CREATE TABLE IF NOT EXISTS adconnect.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ,
    accepted_by UUID REFERENCES auth.users(id)
);

ALTER TABLE adconnect.invitations ENABLE ROW LEVEL SECURITY;

-- public.current_org_id() — the SECURITY DEFINER trusted-table resolver, NOT
-- the top-level `auth.jwt() ->> 'org_id'` claim, which is always NULL here
-- (org_id lives under user_metadata). Same correction as migration 004.
DROP POLICY IF EXISTS "invitations_select_own_org" ON adconnect.invitations;
CREATE POLICY "invitations_select_own_org" ON adconnect.invitations
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE INDEX IF NOT EXISTS idx_adconnect_invitations_org ON adconnect.invitations(org_id);
CREATE INDEX IF NOT EXISTS idx_adconnect_invitations_token ON adconnect.invitations(token);
