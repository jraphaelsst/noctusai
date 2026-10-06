-- Migration: 061_secdef_execute_lockdown
-- Schema(s): public, core
--
-- SECURITY HOTFIX (2026-10-06): PostgREST auto-exposes every function in an
-- exposed schema as /rpc/<name>, and Postgres grants EXECUTE to PUBLIC by
-- default (Supabase also grants anon/authenticated). Every SECURITY DEFINER
-- function was therefore callable by any logged-in user (e.g.
-- public.enforce_session_cap deletes ANY user's auth.sessions).
--
-- Rule: a SECURITY DEFINER function keeps caller EXECUTE ONLY if an RLS policy
-- (or a column DEFAULT) depends on it -- derived LIVE from pg_depend, never a
-- hand list. Everything else (trigger fns, provisioning, backend RPCs) is
-- revoked from PUBLIC/anon/authenticated and granted to service_role only.
-- Extension-owned and non-owned functions are skipped (REVOKE would fail).
-- Idempotent; safe to re-run.
--
-- KB § PATTERNS/backend/database-rls.md (SECURITY DEFINER EXECUTE lockdown).

DO $secdef$
DECLARE
  r record;
  -- Extra always-keep helpers (also kept automatically when a policy uses them).
  v_keep text[] := ARRAY['current_org_id','current_user_org_id','current_org_role','current_user_id','is_customer','current_customer_org_id','is_platform_admin'];
BEGIN
  FOR r IN
    SELECT n.nspname, p.proname, p.oid,
           pg_get_function_identity_arguments(p.oid) AS args
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = ANY (ARRAY['public','core'])
       AND p.prosecdef
       AND p.prokind = 'f'
       AND pg_get_userbyid(p.proowner) = current_user
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.objid = p.oid AND d.deptype = 'e')
       AND NOT (p.proname = ANY (v_keep))
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.refclassid = 'pg_proc'::regclass
                          AND d.refobjid = p.oid
                          AND d.classid IN ('pg_policy'::regclass,
                                            'pg_attrdef'::regclass))
  LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %I.%I(%s) FROM PUBLIC, anon, authenticated',
                   r.nspname, r.proname, r.args);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(%s) TO service_role',
                   r.nspname, r.proname, r.args);
  END LOOP;
END
$secdef$;

-- Future functions: no auto-grant to PUBLIC; service_role only.
DO $d$ BEGIN IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='public') THEN
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;
END IF; END $d$;
DO $d$ BEGIN IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='core') THEN
  ALTER DEFAULT PRIVILEGES IN SCHEMA core REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
  ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT EXECUTE ON FUNCTIONS TO service_role;
END IF; END $d$;
