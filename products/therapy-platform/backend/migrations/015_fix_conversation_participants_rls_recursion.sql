-- ============================================================
-- 015 — Fix infinite recursion in conversation_participants RLS policy
-- ============================================================
-- Latent PostgREST 42P17 in therapy.conversation_participants:
--   "infinite recursion detected in policy for relation
--    'conversation_participants'"
-- Any authenticated read/write of conversation_participants that reaches the
-- "same-conversation member" arm trips it (e.g. a user listing their chat
-- participants), 500ing the request.
--
-- Root cause: the FOR ALL policy `conversation_participants_access` (created
-- in 001_therapy_platform.sql) reads `conversation_participants` from inside
-- its OWN USING and WITH CHECK clauses:
--     EXISTS (SELECT 1 FROM therapy.conversation_participants cp2
--             WHERE cp2.conversation_id = conversation_participants.conversation_id
--               AND cp2.participant_id = auth.uid())
-- Evaluating conversation_participants' policy requires reading
-- conversation_participants, which re-applies the policy → loop → 42P17.
-- Exactly the shape fixed for erp.equipe_membros in
-- 026_fix_equipe_membros_rls_recursion.sql and public.noctus_users in
-- 035_fix_noctus_users_rls_recursion.sql.
--
-- Fix: a SECURITY DEFINER membership-check helper that resolves "is the
-- caller a participant of this conversation?" bypassing RLS (runs as the
-- function owner, which has BYPASSRLS), and rewrite the policy to call it
-- instead of self-querying the table. The original three-arm intent is
-- preserved exactly:
--   platform_admin  OR  it's my own participant row  OR  I'm a member of the
--   same conversation (now resolved via the bypass helper → no recursion).
-- ============================================================

-- ─── SECURITY DEFINER helper ────────────────────────────────────────────────
-- Runs as the function owner (postgres / superuser) which has BYPASSRLS, so
-- the inner SELECT does NOT re-trigger conversation_participants' RLS policy.
-- STABLE: constant within a statement. SET search_path = '' hardens against
-- search-path-based privilege escalation (every object fully-qualified).
CREATE OR REPLACE FUNCTION therapy.is_conversation_member(p_conversation_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = p_conversation_id
          AND cp.participant_id = (SELECT auth.uid())
    );
$$;

-- Lock down: only authenticated users may invoke; revoke from PUBLIC.
REVOKE ALL ON FUNCTION therapy.is_conversation_member(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION therapy.is_conversation_member(uuid) TO authenticated;

-- ─── Rewrite the recursive policy ───────────────────────────────────────────
-- conversation_participants: platform_admin sees all; otherwise my own row
-- (cheap, no function call), OR a row in a conversation I'm a member of
-- (resolved via the bypass helper → no recursion). The "my own row" arm
-- short-circuits before the helper for the common case.
DROP POLICY IF EXISTS "conversation_participants_access" ON therapy.conversation_participants;
CREATE POLICY "conversation_participants_access" ON therapy.conversation_participants
    FOR ALL TO authenticated
    USING (
        (SELECT therapy.current_user_role()) = 'platform_admin'
        OR participant_id = (SELECT auth.uid())
        OR therapy.is_conversation_member(conversation_id)
    )
    WITH CHECK (
        (SELECT therapy.current_user_role()) = 'platform_admin'
        OR participant_id = (SELECT auth.uid())
        OR therapy.is_conversation_member(conversation_id)
    );
