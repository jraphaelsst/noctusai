-- ============================================================================
-- 104_public_browser_grants_service_only.sql -- SECURITY triage P2 (2026-11-07).
--
-- Supabase's default privileges grant `arwdDxtm` on every new `public` table to
-- anon + authenticated, and 42 core tables carried those grants. RLS was on and
-- anon read 0 rows, but the grants were far broader than any caller needs:
--   * `products_read_all` let any logged-in user read url_base / db_schema /
--     house_port / deploy_scope (platform config);
--   * `authenticated` held UPDATE on `noctus_users`, whose `role` is the
--     platform-admin gate (no UPDATE policy exists, so RLS was the only wall).
--
-- Step 1 evidence (grep of products/core/frontend/src + seed/lib/frontend/src for
-- supabase-js `.from()/.schema()/.rpc()/.channel()` and `/rest/v1`): the browser
-- reads NO core `public` table. The single `.from()` is `status_pagina`
-- (seed/lib `usePageStatus`), which lives in each PRODUCT schema, and whose RLS
-- goes through the SECURITY DEFINER helpers public.current_org_id()/
-- current_org_role() -- so it does not need table grants on noctus_users.
-- Every core read/write goes through the backend with the service role.
-- => nothing is granted back; every core `public` table becomes service-role only.
--
-- Scope: every `public` relation EXCEPT fin_* (103's work). `products` is only
-- revoked + its `products_read_all` policy dropped (migration 100 owns its shape).
-- The browser needs no product list; if one is wanted later it comes from the
-- backend (website_catalog_service), not from PostgREST.
--
-- Forward-only + idempotent. Backward-compatible with the previous image (the
-- backend uses service_role, which keeps its grants). Final DO block RAISEs if any
-- browser grant remains.
-- ============================================================================

-- 1. Future objects: no browser grant by default ------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- supabase_admin also owns objects created by Supabase tooling. Altering ITS
-- defaults needs membership of that role; where the migration role lacks it,
-- note it and carry on (never fail the deploy).
DO $sa$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    BEGIN
      ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
        REVOKE ALL ON TABLES FROM anon, authenticated;
      ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
        REVOKE ALL ON SEQUENCES FROM anon, authenticated;
    EXCEPTION WHEN insufficient_privilege THEN
      RAISE NOTICE '104: migration role cannot alter supabase_admin default privileges; run as supabase_admin separately';
    END;
  END IF;
END $sa$;

-- 2. Existing relations: service role only ------------------------------------
DO $revoke$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.oid, c.relname, c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
       AND c.relname NOT LIKE 'fin\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', r.relname);
    IF r.relkind IN ('r', 'p') THEN
      EXECUTE format('GRANT ALL ON public.%I TO service_role', r.relname);
    END IF;
  END LOOP;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;
END $revoke$;

-- 3. products: platform config, not for the browser ---------------------------
DROP POLICY IF EXISTS "products_read_all" ON public.products;

-- 4. Access tier of each touched table ----------------------------------------
DO $tier$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('act_as_sessions','platform'),('ai_consent','org'),('ai_feedback','org'),('ai_usage','org'),
      ('api_keys','org'),('api_token_audit','service'),('api_tokens','service'),
      ('app_integration_config','platform'),('audit_logs','org'),
      ('billing_customers','org'),('billing_events','org'),('billing_payments','org'),
      ('cost_ledger','platform'),('credit_entries','org'),('credit_pricing','platform'),
      ('credit_purchases','org'),('credit_wallets','org'),
      ('dev_telemetry_claude','platform'),('dev_telemetry_jobs','platform'),
      ('dev_telemetry_marks','platform'),('dev_telemetry_os','platform'),
      ('fx_rates','platform'),('help_chat_conversas','org'),('help_chat_mensagens','org'),
      ('invitations','org'),('jobs','service'),('licenses','org'),('mfa_policy','org'),
      ('noctus_users','org'),('notifications','org'),('org_brand_identities','org'),
      ('org_member_product_access','org'),('org_memberships','org'),('org_settings','org'),
      ('organizations','org'),('orgs','org'),('owner_briefs','platform'),
      ('payment_events','service'),('plan_prices','platform'),('plans','platform'),
      ('platform_org_selections','platform'),('platform_settings','platform'),
      ('platform_templates','platform'),('product_usage','org'),('products','platform'),
      ('roles','platform'),('scheduler_jobs','service'),('scheduler_runs','service'),
      ('service_accounts','platform'),('sso_token_redemptions','service'),
      ('storage_usage_snapshots','platform'),('subscriptions','org'),
      ('tool_call_audits','platform'),('transcricoes_api','org'),
      ('user_permission_grants','org'),('webhook_deliveries','org'),
      ('webhook_endpoints','org'),('website_events','platform'),
      ('website_lead_activities','platform'),('website_leads','platform'),
      ('website_settings','platform')
    ) AS t(name, tier)
  LOOP
    IF to_regclass(format('public.%I', r.name)) IS NOT NULL THEN
      EXECUTE format('COMMENT ON TABLE public.%I IS %L', r.name, 'tier:' || r.tier);
    END IF;
  END LOOP;
END $tier$;

-- 5. Assertion: no browser grant, no products_read_all, no UPDATE path --------
DO $assert$
DECLARE
  v_bad text;
BEGIN
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_bad
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
     AND c.relname NOT LIKE 'fin\_%'
     AND (has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES')
          OR has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '104: public relation(s) still reachable by anon/authenticated: %', v_bad;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'products'
                AND policyname = 'products_read_all') THEN
    RAISE EXCEPTION '104: products_read_all still present';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'noctus_users'
                AND cmd IN ('UPDATE', 'ALL') AND roles && ARRAY['public', 'authenticated', 'anon']::name[]) THEN
    RAISE EXCEPTION '104: noctus_users has a browser UPDATE policy';
  END IF;
END $assert$;
