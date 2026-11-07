-- 102: billing_customers / billing_payments platform read path uses platform STAFF, not any role='admin'.
--
-- 050 let `is_platform_admin()` (noctus_users.role='admin', no org check) read every org's billing rows.
-- That is wider than the staff rule in 083 (`platform_staff_role`: role=admin AND home org is_platform AND
-- org_role owner/admin). New `public.is_platform_staff()` is exactly `platform_staff_role(auth.uid()) IS NOT NULL`.
-- is_platform_admin() and its other callers are deliberately untouched. Re-runnable.
SET search_path = public, public;

CREATE OR REPLACE FUNCTION public.is_platform_staff()
  RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$ SELECT public.platform_staff_role((SELECT auth.uid())) IS NOT NULL; $$;

COMMENT ON FUNCTION public.is_platform_staff() IS
    'True for NoctusAI platform staff (same rule as platform_staff_role). Narrower than is_platform_admin().';

REVOKE ALL ON FUNCTION public.is_platform_staff() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_platform_staff() TO authenticated, service_role;

DROP POLICY IF EXISTS "billing_customers_select_own_org" ON public.billing_customers;
CREATE POLICY "billing_customers_select_own_org" ON public.billing_customers
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() OR public.is_platform_staff());

DROP POLICY IF EXISTS "billing_payments_select_own_org" ON public.billing_payments;
CREATE POLICY "billing_payments_select_own_org" ON public.billing_payments
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() OR public.is_platform_staff());
