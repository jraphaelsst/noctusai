-- 101: plans / subscriptions writes are service-only (security P3).
--
-- 001 created `plans_admin_write` and `subscriptions_admin_all` as FOR ALL with no TO clause (=> PUBLIC),
-- gated only on noctus_users.role='admin'. A platform-admin JWT at aal1 (no MFA) could therefore write
-- plans/subscriptions straight through PostgREST, skipping the API's require_admin_assurance and the
-- audit log. Every writer is the backend on the service client (routers/plans.py, subscriptions.py,
-- test_accounts.py, oauth.py); no browser code writes these tables. service_role keeps full access via
-- the `service_role_bypass` policies (030). Reads are unchanged (plans_read_all, subscriptions_read_own).
-- Forward-safe for the previous image: it never relied on the browser write path. Re-runnable.
SET search_path = public, public;

DROP POLICY IF EXISTS "plans_admin_write" ON public.plans;
DROP POLICY IF EXISTS "subscriptions_admin_all" ON public.subscriptions;

REVOKE INSERT, UPDATE, DELETE ON public.plans FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.subscriptions FROM anon, authenticated;
