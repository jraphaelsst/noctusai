-- ============================================================================
-- Migration 004 — Codify the live RLS fix: current_org_id() for orbity schema
--
-- WHY THIS EXISTS
-- ---------------
-- The live orbity schema's invitations table SELECT policy used the broken
-- TOP-LEVEL JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This is ALWAYS NULL in Supabase. The fix was applied LIVE on 2026-06-02.
-- This migration codifies that live state.
--
-- NOTE: The orbity template file at
--   products/orbity/backend/migrations/001_seed.sql
-- was already root-fixed in the same session (feat/rls-codify-org-fn) to
-- use current_org_id() for NEW product scaffolds. However, the LIVE orbity
-- schema on prod still had the broken form — this migration fixes that.
--
-- IDEMPOTENT: DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- orbity.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON orbity.invitations;
CREATE POLICY "invitations_select_own_org" ON orbity.invitations
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));
