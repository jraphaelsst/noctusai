-- ============================================================================
-- Migration 002 — knowledge_extractor.invitations (seed team router dependency)
--
-- WHY THIS EXISTS
-- ---------------
-- `products/knowledge-extractor/backend/app/main.py` mounts
-- `standard_routers=[…,"team",…]`, so the product exposes the invite/accept
-- endpoints — all of which address `<schema>.invitations`. The schema never had
-- that table, so every call 500'd with "Could not find the table
-- 'knowledge_extractor.invitations' in the schema cache".
--
-- Masked until 2026-08-07 by a schema-qualified table name in the seed router
-- (fixed in 0dc45027) that produced a near-identical error fleet-wide.
--
-- NOTE: knowledge-extractor has no deployed container today, so this gap was
-- never hit by a user. Shipping the migration anyway keeps the product's schema
-- honest about the routes its own main.py mounts — a product whose table set
-- does not cover its mounted routers is a deploy-time surprise waiting to
-- happen, not a dormant one.
--
-- SHAPE: byte-identical to the canonical scaffold
-- (`products/seed/backend/migrations/001_seed.sql` + `002_invitations_accepted_columns.sql`).
--
-- PREREQUISITE: public.current_org_id() (products/core/.../001_noctusai_core.sql).
-- IDEMPOTENT: IF NOT EXISTS throughout + DROP POLICY IF EXISTS before CREATE.
-- ============================================================================

CREATE TABLE IF NOT EXISTS knowledge_extractor.invitations (
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

ALTER TABLE knowledge_extractor.invitations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "invitations_select_own_org" ON knowledge_extractor.invitations;
CREATE POLICY "invitations_select_own_org" ON knowledge_extractor.invitations
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE INDEX IF NOT EXISTS idx_knowledge_extractor_invitations_org ON knowledge_extractor.invitations(org_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_extractor_invitations_token ON knowledge_extractor.invitations(token);
