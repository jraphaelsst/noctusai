-- ============================================================================
-- Migration 034 — Codify the live RLS fix: current_org_id() for media_scheduling
--
-- WHY THIS EXISTS
-- ---------------
-- The media_scheduling schema exists on prod with 1 broken authenticated RLS
-- policy on media_scheduling.invitations. The schema was the original home of
-- the media-scheduling product, which was absorbed into imobi-scheduling in
-- commit b91043fc (2026-05-11). No repo migration file existed for the
-- media_scheduling schema policy.
--
-- PLACEMENT DECISION: media-scheduling was absorbed into erp-imobiliario
-- (the imobi-scheduling container). This migration lives alongside the other
-- erp-imobiliario imobi/media schema migrations (032, 033).
--
-- FLAG FOR TECH-LEAD: confirm this placement is correct, or whether
-- media_scheduling should be treated as a standalone orphan migration.
-- If the schema is no longer actively used after the absorption, consider
-- dropping it after confirming no live data depends on it.
--
-- PREREQUISITE: public.current_org_id() must exist (defined in
--   products/seed/backend/migrations/001_seed.sql).
--
-- IDEMPOTENT: DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- media_scheduling.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON media_scheduling.invitations;
CREATE POLICY "invitations_select_own_org" ON media_scheduling.invitations
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));
