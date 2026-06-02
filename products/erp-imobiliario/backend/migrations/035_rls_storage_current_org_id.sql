-- ============================================================================
-- Migration 035 — Codify the live RLS fix: current_org_id() for storage.objects
--
-- WHY THIS EXISTS
-- ---------------
-- The erp storage bucket policies in storage.objects used:
--
--     (auth.jwt() -> 'user_metadata'::text) ->> 'org_id'::text
--
-- This is the user_metadata form — user-editable, a privilege escalation
-- hole. The Supabase advisor flags this as rls_references_user_metadata (ERROR).
--
-- Since storage.objects has no direct org_id column, the fix uses a subquery
-- against the trusted noctus_users table, which is equivalent to but different
-- from the current_org_id() function (which returns uuid, not text):
--
--     (storage.foldername(name))[1] = (SELECT org_id::text FROM public.noctus_users
--                                       WHERE id = (SELECT auth.uid()))
--
-- The fix was applied LIVE on 2026-06-02. This migration codifies that state.
--
-- PLACEMENT: erp-imobiliario owns these storage buckets (bucket_id ~~ 'erp-%').
-- The original storage policy was set in
--   products/erp-imobiliario/backend/migrations/011_storage_buckets.sql
-- This migration supersedes those policies.
--
-- IDEMPOTENT: DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- storage.objects — erp bucket policies -----
DROP POLICY IF EXISTS "erp_storage_delete" ON storage.objects;
CREATE POLICY "erp_storage_delete" ON storage.objects
  FOR DELETE TO authenticated
  USING (
    (bucket_id ~~ 'erp-%'::text)
    AND ((storage.foldername(name))[1] = (
      SELECT org_id::text FROM public.noctus_users WHERE id = (SELECT auth.uid())
    ))
  );

DROP POLICY IF EXISTS "erp_storage_insert" ON storage.objects;
CREATE POLICY "erp_storage_insert" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    (bucket_id ~~ 'erp-%'::text)
    AND ((storage.foldername(name))[1] = (
      SELECT org_id::text FROM public.noctus_users WHERE id = (SELECT auth.uid())
    ))
  );

DROP POLICY IF EXISTS "erp_storage_select" ON storage.objects;
CREATE POLICY "erp_storage_select" ON storage.objects
  FOR SELECT TO authenticated
  USING (
    (bucket_id ~~ 'erp-%'::text)
    AND ((storage.foldername(name))[1] = (
      SELECT org_id::text FROM public.noctus_users WHERE id = (SELECT auth.uid())
    ))
  );

DROP POLICY IF EXISTS "erp_storage_update" ON storage.objects;
CREATE POLICY "erp_storage_update" ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    (bucket_id ~~ 'erp-%'::text)
    AND ((storage.foldername(name))[1] = (
      SELECT org_id::text FROM public.noctus_users WHERE id = (SELECT auth.uid())
    ))
  );
