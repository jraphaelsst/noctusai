-- ============================================================================
-- 086_revoke_browser_secrets_tables.sql -- SECURITY FINDINGS #1/#2/#3 (critical, 2026-10-19).
--
-- `public` is exposed to PostgREST and every logged-in user holds a Supabase
-- session plus the publishable key. Four core tables carried org-scoped
-- `authenticated` policies (055: `FOR ALL` on org_settings / webhook_endpoints /
-- api_keys, `FOR SELECT` on webhook_deliveries) and Supabase's default grants, so
-- any non-customer member of an org could, straight from the browser:
--   * read AND WRITE `org_settings` -- per-org vendor credentials, tier 1 of
--     `resolve_credential`, so a write injects keys the backend then USES;
--   * read AND WRITE `webhook_endpoints` -- url + signing secret, i.e. forge
--     signed deliveries or redirect the event stream; read `webhook_deliveries`;
--   * insert / delete `api_keys` rows (key hashes), bypassing the admin gate.
--
-- Every backend path (credentials/settings/api_keys/webhooks routers, webhook
-- delivery + retention, the seed credential resolver and LLM budget) already uses
-- the service-role client with explicit `org_id` filters and API-level role
-- checks; the frontend never reads these tables through supabase-js. So all four
-- tables become service-role only: REVOKE from PUBLIC/anon/authenticated and drop
-- every policy naming those roles. service_role has BYPASSRLS and keeps its grants.
--
-- Out of scope (needs a SECURITY DEFINER refactor first): `noctus_users` and the
-- policies that subquery it.
--
-- Forward-only + idempotent. The final DO block RAISEs if any browser grant or
-- policy remains -- a half-applied lockdown is a loud failure.
-- ============================================================================

DO $revoke$
DECLARE
  t text;
  pol record;
  v_tables constant text[] := ARRAY['org_settings', 'webhook_endpoints', 'webhook_deliveries', 'api_keys'];
BEGIN
  FOREACH t IN ARRAY v_tables LOOP
    IF to_regclass(format('public.%I', t)) IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
    -- Covers org_settings_org_members, webhook_endpoints_org, webhook_deliveries_via_endpoint,
    -- api_keys_read_own, api_keys_write_own and anything created outside the chain.
    FOR pol IN
      SELECT policyname FROM pg_policies
       WHERE schemaname = 'public' AND tablename = t
         AND roles && ARRAY['public', 'anon', 'authenticated']::name[]
    LOOP
      EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pol.policyname, t);
    END LOOP;
  END LOOP;
END $revoke$;

-- Assertion: nothing reachable from the browser remains on these tables.
DO $assert$
DECLARE
  v_bad text;
BEGIN
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_bad
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
     AND c.relname = ANY (ARRAY['org_settings', 'webhook_endpoints', 'webhook_deliveries', 'api_keys'])
     AND (has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES')
          OR has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '086: core table(s) still reachable by anon/authenticated: %', v_bad;
  END IF;

  SELECT string_agg(p.tablename || '.' || p.policyname, ', ') INTO v_bad
    FROM pg_policies p
   WHERE p.schemaname = 'public'
     AND p.tablename = ANY (ARRAY['org_settings', 'webhook_endpoints', 'webhook_deliveries', 'api_keys'])
     AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '086: core polic(ies) still name anon/authenticated/public: %', v_bad;
  END IF;
END $assert$;
