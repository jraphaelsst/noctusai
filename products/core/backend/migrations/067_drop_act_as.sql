-- Migration: drop act-as-org (owner decision 2026-10-07)
-- Schema: public (core)
--
-- WHAT
--   The superadmin "act-as-org" / "Entrar como org" feature (core 065) is
--   removed end to end: NoctusAI staff no longer enter customer orgs at all.
--   The LICENSE GATE (403 org_sem_licenca) is unaffected.
--
--   1. current_org_id() / current_user_org_id() re-declared with the
--      canonical home-org rendering (sql_templates.org_identity_function_sql —
--      keeper check_org_identity_function_parity): no act_as_sessions join.
--      Still SECURITY DEFINER with a pinned search_path and still
--      caller-executable: they are RLS helpers. Swapped FIRST, so the table
--      drop below never leaves a helper referencing a missing relation.
--   2. DROP TABLE public.act_as_sessions (service-role only; nothing reads it
--      once the helpers above no longer join it).
--   3. audit_logs.acting_org_id / act_as_session_id are KEPT: historical rows
--      written while the feature existed still carry them. Nothing writes
--      them any more; they are marked historical.
--
-- KB § PATTERNS/backend/tenancy-license-gate.md
SET search_path = public, public;

-- secdef-execute-ok: rls-helper policies call current_org_id() as the caller (EXECUTE must stay)
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users
   WHERE id = (SELECT auth.uid())
     AND COALESCE(org_role, '') <> ALL (ARRAY['membro']);
$f$;

-- secdef-execute-ok: rls-helper policies call current_user_org_id() as the caller (EXECUTE must stay)
CREATE OR REPLACE FUNCTION public.current_user_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users
   WHERE id = (SELECT auth.uid())
     AND COALESCE(org_role, '') <> ALL (ARRAY['membro']);
$f$;

DROP TABLE IF EXISTS public.act_as_sessions;

COMMENT ON COLUMN public.audit_logs.acting_org_id IS
    'HISTORICAL (core 065, removed by 067): org a superadmin acted as. No longer written.';
COMMENT ON COLUMN public.audit_logs.act_as_session_id IS
    'HISTORICAL (core 065, removed by 067): the act-as session id. No longer written.';
