-- ============================================================================
-- Migration 007 — Codify the live RLS fix: current_org_id() for daily_life schema
--
-- WHY THIS EXISTS
-- ---------------
-- The daily_life.invitations table's SELECT policy used the broken TOP-LEVEL
-- JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This is ALWAYS NULL in Supabase (see social-wiring 011_rls_current_org_id.sql
-- for the root cause explanation). The fix was applied LIVE on 2026-06-02.
-- This migration codifies that live state.
--
-- The broken policy was created in
--   products/daily-life/backend/migrations/001_daily_life.sql
-- This migration is the forward-only correction for that policy.
--
-- PREREQUISITE: public.current_org_id() must exist (defined in
--   products/seed/backend/migrations/001_seed.sql).
--
-- IDEMPOTENT: DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- daily_life.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON daily_life.invitations;
CREATE POLICY "invitations_select_own_org" ON daily_life.invitations
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));
