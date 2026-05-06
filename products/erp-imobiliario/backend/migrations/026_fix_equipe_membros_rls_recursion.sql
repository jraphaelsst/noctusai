-- ============================================================
-- 026 — Fix infinite recursion in equipe_membros RLS policies
-- ============================================================
-- PostgREST 42P17 surfaced 2026-05-05 on /api/metas/rankings:
--   "infinite recursion detected in policy for relation 'equipe_membros'"
-- Root cause: the SELECT policy `corretor_select_equipe_membros` (created
-- in 016_metas_domain.sql) reads `equipe_membros` from inside its own
-- USING clause; Postgres re-evaluates the policy on the inner SELECT and
-- loops. Same shape in `corretor_select_equipes` and
-- `corretor_select_metas_equipe` (both query equipe_membros from inside
-- their USING clauses, which fails once equipe_membros' policy is broken).
--
-- Fix: a SECURITY DEFINER membership-check function that bypasses RLS
-- for the membership lookup, and rewrite the three corretor SELECT
-- policies to call it instead of querying equipe_membros directly.
-- ============================================================

SET search_path = erp, public;

-- ─── SECURITY DEFINER helper ────────────────────────────────────────────────
-- Runs as the function owner (postgres / superuser) which has BYPASSRLS,
-- so the inner SELECT does not re-trigger equipe_membros' RLS policy.
-- STABLE because the result is constant within a statement; SET search_path
-- to '' to harden against search-path-based privilege escalation.
CREATE OR REPLACE FUNCTION erp.is_equipe_member(_equipe_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM erp.equipe_membros m
        WHERE m.equipe_id = _equipe_id
          AND m.user_id = (SELECT auth.uid())
          AND m.left_at IS NULL
    );
$$;

-- Lock down: only authenticated users may invoke; revoke from PUBLIC.
REVOKE ALL ON FUNCTION erp.is_equipe_member(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION erp.is_equipe_member(uuid) TO authenticated;

-- ─── Rewrite the three recursive SELECT policies ───────────────────────────

-- equipes: visible if I am a member.
DROP POLICY IF EXISTS corretor_select_equipes ON erp.equipes;
CREATE POLICY corretor_select_equipes ON erp.equipes
    FOR SELECT
    USING (erp.is_equipe_member(id));

-- equipe_membros: visible if it's MY row, OR if it belongs to a team I'm in.
-- The "my row" arm avoids any function call (cheap path); the team arm
-- uses the helper so no recursion.
DROP POLICY IF EXISTS corretor_select_equipe_membros ON erp.equipe_membros;
CREATE POLICY corretor_select_equipe_membros ON erp.equipe_membros
    FOR SELECT
    USING (
        user_id = (SELECT auth.uid())
        OR erp.is_equipe_member(equipe_id)
    );

-- metas_equipe: visible if I am a member of the team the meta belongs to.
DROP POLICY IF EXISTS corretor_select_metas_equipe ON erp.metas_equipe;
CREATE POLICY corretor_select_metas_equipe ON erp.metas_equipe
    FOR SELECT
    USING (erp.is_equipe_member(equipe_id));
