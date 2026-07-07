-- ============================================================================
-- Migration 038 — Org source-of-truth hardening (PILOT) + platform super-admin
--
-- WHY THIS EXISTS
-- ---------------
-- The matrícula extractor 500'd on upload for a freshly-provisioned user
-- (org set in public.noctus_users but NOT yet in the JWT user_metadata).
-- Root cause: the app sourced `org_id` for the INSERT from the JWT
-- (`user_metadata.org_id`), while RLS derives the org from the DB
-- (`current_org_id()` → public.noctus_users). The two drift trivially —
-- a stale/missing JWT claim yields a NULL org, the app omits the NOT NULL
-- column, and the insert 500s.
--
-- This migration begins closing that drift by making the DB the single
-- source of truth for org on writes, and introduces the platform
-- super-admin primitive. It is a PILOT: it hardens ONLY erp.matricula_extracoes.
-- Fan-out to the other 73 org-scoped tables + the seed is tracked in
-- project-history/roadmaps/erp-org-source-of-truth-2026-07.md (Phase 2).
--
-- IDEMPOTENT: CREATE OR REPLACE / DROP POLICY IF EXISTS / ALTER ... SET DEFAULT.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Platform super-admin primitive — single source of truth: noctus_users.role
--
-- A platform admin (the operator) transcends org isolation: they can see and
-- manage every org's data. This reads the SAME trusted table that
-- current_org_id() reads (public.noctus_users), so there is one identity
-- source, not five. SECURITY DEFINER so the authenticated role can evaluate it
-- inside RLS without direct table grants.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.is_platform_admin()
  RETURNS boolean
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $fn$
  SELECT EXISTS (
    SELECT 1 FROM public.noctus_users
    WHERE id = (SELECT auth.uid()) AND role = 'admin'
  );
$fn$;

-- ----------------------------------------------------------------------------
-- 2. Org on writes comes from the DB, not the app/JWT.
--
-- With this DEFAULT, an INSERT that omits org_id is stamped with the caller's
-- DB-derived org (erp.current_org_id() → noctus_users). The app no longer has
-- to know the org, so a stale JWT can never again produce a NULL org / 500.
-- RLS WITH CHECK still enforces it, so this is safe defense-in-depth.
-- ----------------------------------------------------------------------------
ALTER TABLE erp.matricula_extracoes
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

-- ----------------------------------------------------------------------------
-- 3. Rebuild the org-isolation policy with the platform-admin cross-org bypass.
--
-- Everyone still sees only their own org (org_id = current_org_id());
-- a platform admin additionally sees/manages every org.
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS "org_isolation" ON erp.matricula_extracoes;
CREATE POLICY "org_isolation" ON erp.matricula_extracoes
  FOR ALL TO authenticated
  USING (org_id = erp.current_org_id() OR public.is_platform_admin())
  WITH CHECK (org_id = erp.current_org_id() OR public.is_platform_admin());
