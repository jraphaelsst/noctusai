-- Migration 055_customer_role_isolation.sql — SEC-2 customer-role isolation
-- (2026-09-28). Forward-only + idempotent. Core owns `public`, so this is the
-- canonical forward home of the shared org-identity functions; each product's
-- own *_customer_role_isolation.sql re-asserts the SAME rendering so no chain
-- order can revert it.
--
-- WHY: end customers (org_role in CUSTOMER_ORG_ROLES, today 'membro') are
-- about to self-register into the platform's own org, which is licensed to
-- most products. Every org-scoped RLS policy fleet-wide keyed on "the
-- caller's org" with no role check — a customer would have inherited the
-- whole back office of every licensed product.
--
-- 1. Canonical org-identity functions: current_org_id() / current_user_org_id()
--    return NULL for a customer; is_customer() + current_customer_org_id()
--    are new (a product that serves customers keys its customer-facing
--    policies on current_customer_org_id(), never on current_org_id()).
-- 2. Core's own org-scoped policies that inlined
--    `org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid())`
--    are rewritten onto current_org_id(), so the one exclusion covers them.
--    users_read_own already goes through current_user_org_id() (035): a
--    customer keeps reading their OWN profile row and nothing else.
--    `product_usage.org_read_own` is renamed product_usage_org_read_own:
--    `org_read_own` is also the organizations policy's name, and a DROP by
--    that name is ambiguous to a reader even though Postgres scopes it.
-- 3. public.invitations.token — service-role only (same lockdown as every
--    product schema).
-- 4. products.aceita_clientes — the DATA declaration of which products
--    serve customers. Core's SSO bridge + product switcher refuse a
--    customer everywhere else. Only community (Ninho Vazio) opts in.

SET search_path = public;

-- ---------------------------------------------------------------------------
-- 1. Canonical org-identity functions
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
-- 2. Core org-scoped policies → current_org_id()
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS "org_read_own" ON public.product_usage;

DROP POLICY IF EXISTS "org_read_own" ON public.organizations;
CREATE POLICY "org_read_own" ON public.organizations
    FOR SELECT TO authenticated
    USING (id = public.current_org_id());

DROP POLICY IF EXISTS "licenses_read_own_org" ON public.licenses;
CREATE POLICY "licenses_read_own_org" ON public.licenses
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "subscriptions_read_own" ON public.subscriptions;
CREATE POLICY "subscriptions_read_own" ON public.subscriptions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "api_keys_read_own" ON public.api_keys;
CREATE POLICY "api_keys_read_own" ON public.api_keys
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "api_keys_write_own" ON public.api_keys;
CREATE POLICY "api_keys_write_own" ON public.api_keys
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "invitations_read_own" ON public.invitations;
CREATE POLICY "invitations_read_own" ON public.invitations
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "audit_logs_org_read" ON public.audit_logs;
CREATE POLICY "audit_logs_org_read" ON public.audit_logs
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "webhook_endpoints_org" ON public.webhook_endpoints;
CREATE POLICY "webhook_endpoints_org" ON public.webhook_endpoints
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "webhook_deliveries_via_endpoint" ON public.webhook_deliveries;
CREATE POLICY "webhook_deliveries_via_endpoint" ON public.webhook_deliveries
    FOR SELECT TO authenticated
    USING (endpoint_id IN (SELECT id FROM public.webhook_endpoints WHERE org_id = public.current_org_id()));

DROP POLICY IF EXISTS "org_settings_org_members" ON public.org_settings;
CREATE POLICY "org_settings_org_members" ON public.org_settings
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "product_usage_org_read_own" ON public.product_usage;
CREATE POLICY "product_usage_org_read_own" ON public.product_usage
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "roles_read_own_org" ON public.roles;
CREATE POLICY "roles_read_own_org" ON public.roles
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

-- ---------------------------------------------------------------------------
-- 3. public.invitations.token — service-role only
-- ---------------------------------------------------------------------------

DO $lock$
DECLARE
  v_cols text;
BEGIN
  IF to_regclass('public.invitations') IS NULL THEN
    RAISE NOTICE 'no public.invitations table — nothing to lock';
    RETURN;
  END IF;
  SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
    INTO v_cols
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'invitations'
     AND column_name <> 'token';
  REVOKE ALL ON public.invitations FROM anon;
  REVOKE SELECT ON public.invitations FROM authenticated;
  EXECUTE format('GRANT SELECT (%s) ON public.invitations TO authenticated', v_cols);
END
$lock$;

-- ---------------------------------------------------------------------------
-- 4. products.aceita_clientes — which products serve end customers
-- ---------------------------------------------------------------------------

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS aceita_clientes boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.products.aceita_clientes IS
    'true = end customers (org_role in CUSTOMER_ORG_ROLES) may SSO into this '
    'product. Default false: a customer is refused by core SSO + hidden from '
    'the product switcher. SEC-2, 2026-09-28.';

UPDATE public.products SET aceita_clientes = true WHERE slug = 'community';
