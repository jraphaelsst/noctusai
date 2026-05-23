-- ============================================================
-- 035 — Fix infinite recursion in noctus_users RLS policy
-- ============================================================
-- PostgREST 42P17 surfaced 2026-05-23 on GET /api/auth/me (prod):
--   "infinite recursion detected in policy for relation 'noctus_users'"
-- It blocks login: POST /api/auth/login returns 200, but the very next
-- call GET /api/auth/me (session bootstrap) 500s, so the UI can't finish
-- logging in. The same recursion also fails the login audit-log write
-- (caught → "login proceeds").
--
-- Root cause: the SELECT policy `users_read_own` (created in
-- 001_noctusai_core.sql) reads `noctus_users` from inside its OWN USING
-- clause:
--     org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid())
-- Evaluating noctus_users' policy requires reading noctus_users, which
-- re-applies the policy → loop → 42P17. Exactly the shape fixed for
-- erp.equipe_membros in 026_fix_equipe_membros_rls_recursion.sql.
--
-- Note: this policy applies only TO authenticated. The backend admin
-- client (service_role) has BYPASSRLS and never trips this — so a query
-- that DOES trip it is running as `authenticated`, not service_role.
-- That mis-privilege is a SEPARATE concern (see the deploy note). This
-- migration fixes the genuine policy defect, which is correct regardless:
-- it unblocks the recursion for any authenticated reader (the frontend's
-- direct supabase-js reads included) and is defense-in-depth for the
-- backend.
--
-- Fix: a SECURITY DEFINER helper that resolves the caller's org_id
-- bypassing RLS (runs as the function owner), and rewrite users_read_own
-- to call it instead of self-querying noctus_users. Fixing just this one
-- policy cures the whole cascade — the ~10 other policies that subquery
-- `SELECT org_id FROM noctus_users WHERE id = auth.uid()` become safe once
-- noctus_users' own policy no longer recurses.
-- ============================================================

-- ─── SECURITY DEFINER helper ────────────────────────────────────────────────
-- Runs as the function owner (postgres / superuser) which has BYPASSRLS,
-- so the inner SELECT does NOT re-trigger noctus_users' RLS policy.
-- STABLE: constant within a statement. search_path '' hardens against
-- search-path privilege escalation (fully-qualify every object).
CREATE OR REPLACE FUNCTION public.current_user_org_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT org_id
    FROM public.noctus_users
    WHERE id = (SELECT auth.uid());
$$;

-- Lock down: only authenticated users may invoke; revoke from PUBLIC.
REVOKE ALL ON FUNCTION public.current_user_org_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_user_org_id() TO authenticated;

-- ─── Rewrite the recursive SELECT policy ────────────────────────────────────
-- noctus_users: my own row (cheap, no function call), OR a row in my org
-- (resolved via the bypass helper → no recursion).
DROP POLICY IF EXISTS "users_read_own" ON public.noctus_users;
CREATE POLICY "users_read_own" ON public.noctus_users
    FOR SELECT TO authenticated
    USING (
        id = (SELECT auth.uid())
        OR org_id = public.current_user_org_id()
    );
