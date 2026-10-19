-- ============================================================================
-- 044_revoke_authenticated_content.sql -- SECURITY FINDING #5 (critical, 2026-10-19).
--
-- The `igig` schema is exposed to PostgREST and every logged-in user holds a
-- Supabase session plus the publishable key. 001 `GRANT ALL ... TO authenticated`
-- and 006/008/011/012/018/... added `*_org_isolation FOR ALL TO authenticated`
-- policies, so any member of an org could read AND WRITE, from the browser:
-- cliente, lead, contrato, fatura(+item), orcamento*, negocio, profissional,
-- publicacao, `acesso.senha_cifrada` (credential vault), `integracao.token_cifrado`...
--
-- The igig backend now reaches every table through the service-role (admin)
-- client with an explicit `org_id` on every query (app/store.py, app/pipelines.py
-- `get_db`); the frontend only talks to supabase-js for auth and the single
-- `status_pagina` read (page-visibility flags, no PII). So:
--   * every igig relation except `status_pagina` is service-role only: REVOKE ALL
--     from PUBLIC/anon/authenticated, and every policy naming those roles is
--     dropped -- discovered dynamically from pg_policies (some were created in
--     DO/format loops and are not greppable by name);
--   * `status_pagina` keeps SELECT for anon/authenticated (its visibility
--     policies stay) but loses 001's leftover write privileges;
--   * default privileges for FUTURE tables/sequences no longer reach the browser.
-- service_role has BYPASSRLS and keeps its grants.
--
-- Forward-only + idempotent. The final DO block RAISEs if anything outside the
-- allowlist is still reachable -- a half-applied lockdown is a loud failure.
-- ============================================================================

DO $revoke$
DECLARE
  r record;
  pol record;
BEGIN
  FOR r IN
    SELECT c.relname, c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'igig' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND c.relname <> 'status_pagina'
  LOOP
    EXECUTE format('REVOKE ALL ON igig.%I FROM PUBLIC, anon, authenticated', r.relname);
    IF r.relkind IN ('r', 'p') THEN
      FOR pol IN
        SELECT policyname FROM pg_policies
         WHERE schemaname = 'igig' AND tablename = r.relname
           AND roles && ARRAY['public', 'anon', 'authenticated']::name[]
      LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', pol.policyname, r.relname);
      END LOOP;
    END IF;
  END LOOP;
END $revoke$;

-- The one allowlisted table: the frontend reads page-visibility flags through supabase-js.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON igig.status_pagina FROM PUBLIC, anon, authenticated;
GRANT SELECT ON igig.status_pagina TO anon, authenticated;

-- 001 granted every FUTURE table/sequence to authenticated by default; new objects are now
-- private until a migration deliberately grants them.
REVOKE ALL ON ALL SEQUENCES IN SCHEMA igig FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA igig REVOKE ALL ON TABLES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA igig REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA igig REVOKE ALL ON SEQUENCES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA igig REVOKE ALL ON SEQUENCES FROM anon;

-- Assertion: fail the migration if anything outside the allowlist is still reachable.
DO $assert$
DECLARE
  v_bad text;
BEGIN
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_bad
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'igig' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') AND c.relname <> 'status_pagina'
     AND (has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES')
          OR has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '044: igig relation(s) still reachable by anon/authenticated: %', v_bad;
  END IF;

  SELECT string_agg(p.tablename || '.' || p.policyname, ', ') INTO v_bad
    FROM pg_policies p
   WHERE p.schemaname = 'igig' AND p.tablename <> 'status_pagina'
     AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '044: igig polic(ies) still name anon/authenticated/public: %', v_bad;
  END IF;

  IF has_table_privilege('authenticated', 'igig.status_pagina', 'INSERT, UPDATE, DELETE, TRUNCATE')
     OR has_table_privilege('anon', 'igig.status_pagina', 'INSERT, UPDATE, DELETE, TRUNCATE') THEN
    RAISE EXCEPTION '044: igig.status_pagina must stay read-only for the browser';
  END IF;
END $assert$;
