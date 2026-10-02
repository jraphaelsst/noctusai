-- Migration 006_customer_role_isolation.sql — SEC-2 customer-role isolation
-- (2026-09-28). Forward-only + idempotent.
--
-- WHY: end customers (org_role in CUSTOMER_ORG_ROLES, today 'membro') are
-- about to self-register into the platform's own org. Every org-scoped RLS
-- policy in this schema keys on public.current_org_id(), which (until now)
-- answered the caller's org with no role check — a customer would have read
-- and written this product's whole back office.
--
-- 1. Re-assert the canonical org-identity functions. current_org_id()
--    returns NULL for a customer, so every `org_id = current_org_id()`
--    policy denies them at once. The block is RENDERED from
--    noctusai_lib.domain.sql_templates.org_identity_functions_sql() — it is
--    the one definition; keeper check_org_identity_function_parity fails any
--    copy that drifts (a stale copy in ANY chain re-opens the whole fleet on
--    a fresh apply, because they all write the same shared public function).
-- 2. invitations.token is no longer readable through the API roles: the
--    invite flow reads/validates tokens with the service role only, and any
--    org member could otherwise lift a pending invite's token. anon loses
--    the table entirely.

SET search_path = store, public;

-- ---------------------------------------------------------------------------
-- 1. Canonical org-identity functions (shared public schema)
-- ---------------------------------------------------------------------------

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

CREATE OR REPLACE FUNCTION public.current_org_role()
  RETURNS text
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_role FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;

CREATE OR REPLACE FUNCTION public.is_customer()
  RETURNS boolean
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT COALESCE(
    (SELECT org_role = ANY (ARRAY['membro'])
       FROM public.noctus_users WHERE id = (SELECT auth.uid())),
    false
  );
$f$;

CREATE OR REPLACE FUNCTION public.current_customer_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users
   WHERE id = (SELECT auth.uid())
     AND org_role = ANY (ARRAY['membro']);
$f$;

-- ---------------------------------------------------------------------------
-- 2. invitations.token — service-role only
-- ---------------------------------------------------------------------------

DO $lock$
DECLARE
  v_cols text;
BEGIN
  IF to_regclass('store.invitations') IS NULL THEN
    RAISE NOTICE 'no store.invitations table — nothing to lock';
    RETURN;
  END IF;
  SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
    INTO v_cols
    FROM information_schema.columns
   WHERE table_schema = 'store' AND table_name = 'invitations'
     AND column_name <> 'token';
  REVOKE ALL ON store.invitations FROM anon;
  REVOKE SELECT ON store.invitations FROM authenticated;
  EXECUTE format('GRANT SELECT (%s) ON store.invitations TO authenticated', v_cols);
END
$lock$;
