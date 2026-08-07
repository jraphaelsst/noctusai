-- ============================================================================
-- Migration 0004 — dev_team.invitations (the table the seed team router needs)
--
-- WHY THIS EXISTS
-- ---------------
-- `products/dev-team/backend/app/main.py` mounts `standard_routers=[…,"team"]`,
-- so the product exposes the invite/accept endpoints — all of which address
-- `<schema>.invitations`. dev_team never had that table, so every call 500'd
-- with "Could not find the table 'dev_team.invitations' in the schema cache".
--
-- Masked until 2026-08-07 by a schema-qualified table name in the seed router
-- (fixed in 0dc45027) that produced a near-identical error fleet-wide; with
-- that gone, the genuinely-missing table is visible as its own gap.
--
-- SHAPE: byte-identical to the canonical scaffold
-- (`products/seed/backend/migrations/001_seed.sql` + `002_invitations_accepted_columns.sql`),
-- because the seed team router is shared code reading these exact columns
-- across all nine mounting products.
--
-- NOTE ON NUMBERING: this product uses a FOUR-digit prefix (0001…0003), unlike
-- the three-digit convention elsewhere. Following the local convention keeps
-- lexical and numeric order agreeing within this directory.
--
-- PREREQUISITE: public.current_org_id() (products/core/.../001_noctusai_core.sql).
-- IDEMPOTENT: IF NOT EXISTS throughout + DROP POLICY IF EXISTS before CREATE.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.invitations (
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

ALTER TABLE dev_team.invitations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "invitations_select_own_org" ON dev_team.invitations;
CREATE POLICY "invitations_select_own_org" ON dev_team.invitations
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE INDEX IF NOT EXISTS idx_dev_team_invitations_org ON dev_team.invitations(org_id);
CREATE INDEX IF NOT EXISTS idx_dev_team_invitations_token ON dev_team.invitations(token);
