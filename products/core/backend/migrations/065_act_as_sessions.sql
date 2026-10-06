-- Migration: act_as_sessions (round 2 — superadmin act-as-org + license gate)
-- Schema: public (core)
--
-- WHAT
--   1. public.act_as_sessions — the platform owner (a SUPERADMIN =
--      noctus_users.role = 'admin') enters a product AS a customer org. One
--      LIVE row (ended_at IS NULL) per superadmin; ends only on "Sair"
--      (exit), a new act-as (replaced) or core logout (logout). No expiry.
--      SERVICE-ROLE ONLY: RLS on, NO policy, anon/authenticated REVOKEd.
--   2. current_org_id() / current_user_org_id() re-created with the act-as
--      branch (canonical rendering of sql_templates.org_identity_function_sql —
--      keeper check_org_identity_function_parity). Still SECURITY DEFINER with
--      a pinned search_path and still caller-executable: they are RLS helpers.
--   3. audit_logs.acting_org_id / act_as_session_id — every mutating request
--      made while acting is tagged. Rows written while acting carry org_id
--      NULL (the acted-as org is in acting_org_id), so the customer's own
--      `audit_logs_org_read` policy never shows them: act-as audit is visible
--      to the superadmin only.
SET search_path = public, public;

CREATE TABLE IF NOT EXISTS public.act_as_sessions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    superadmin_id      uuid NOT NULL REFERENCES public.noctus_users(id),
    target_org_id      uuid NOT NULL REFERENCES public.organizations(id),
    entry_product_slug text NOT NULL,
    reason             text,
    started_at         timestamptz NOT NULL DEFAULT now(),
    ended_at           timestamptz,
    ended_by           text CHECK (ended_by IN ('exit', 'replaced', 'logout')),
    ip                 text,
    user_agent         text
);

-- At most one LIVE act-as per superadmin (also what keeps the helper's
-- LEFT JOIN from ever fanning out to two rows).
CREATE UNIQUE INDEX IF NOT EXISTS idx_act_as_sessions_one_live
    ON public.act_as_sessions (superadmin_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_act_as_sessions_started
    ON public.act_as_sessions (started_at DESC);

ALTER TABLE public.act_as_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.act_as_sessions FROM anon, authenticated;
GRANT ALL ON public.act_as_sessions TO service_role;

ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS acting_org_id uuid;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS act_as_session_id uuid;
CREATE INDEX IF NOT EXISTS idx_audit_logs_act_as_session
    ON public.audit_logs (act_as_session_id) WHERE act_as_session_id IS NOT NULL;

-- secdef-execute-ok: rls-helper policies call current_org_id() as the caller (EXECUTE must stay)
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT CASE
           WHEN u.role = 'admin' AND a.target_org_id IS NOT NULL
             THEN a.target_org_id
           WHEN COALESCE(u.org_role, '') <> ALL (ARRAY['membro'])
             THEN u.org_id
         END
    FROM public.noctus_users u
    LEFT JOIN public.act_as_sessions a
      ON a.superadmin_id = u.id AND a.ended_at IS NULL
   WHERE u.id = (SELECT auth.uid());
$f$;

-- secdef-execute-ok: rls-helper policies call current_user_org_id() as the caller (EXECUTE must stay)
CREATE OR REPLACE FUNCTION public.current_user_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT CASE
           WHEN u.role = 'admin' AND a.target_org_id IS NOT NULL
             THEN a.target_org_id
           WHEN COALESCE(u.org_role, '') <> ALL (ARRAY['membro'])
             THEN u.org_id
         END
    FROM public.noctus_users u
    LEFT JOIN public.act_as_sessions a
      ON a.superadmin_id = u.id AND a.ended_at IS NULL
   WHERE u.id = (SELECT auth.uid());
$f$;
