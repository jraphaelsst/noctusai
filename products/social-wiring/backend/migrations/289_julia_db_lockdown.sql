-- ============================================================================
-- Migration 289 -- social_wiring: julia_* / lais_* are backend-only (security audit 2026-10-19, H1 + H2)
-- ============================================================================
-- WHY
-- ---
-- The julia_* tables (contacts, interactions, events, applied actions, credit analyses + consents, notes, feedback,
-- dispatch rules, visits, ...) were readable by ANY member of the org straight over PostgREST (SELECT TO authenticated
-- with an org predicate). That bypasses the per-lead access rule A7 (services/julia_acesso.py: owner/admin only) that
-- the API enforces, so lead PII (names, phones, messages, credit data) was one browser fetch away for every member.
-- julia_perguntas_catalogo also had SELECT TO authenticated USING (true), exposing the model-instruction column `dica`.
--
-- The social-wiring FRONTEND reads NO julia table directly (grep of frontend/src: the supabase client is used for
-- auth.getSession() only; no .from()/.schema()/.channel()). Every read goes through the backend (service role), so the
-- direct-access allowlist is EMPTY.
--
-- WHAT (dynamic over catalog -- covers the post-287 julia_* names AND the lais_* security_invoker compat views)
--   1. REVOKE ALL on every social_wiring relation named julia_* / lais_* from PUBLIC, anon and authenticated;
--   2. DROP every RLS policy on those tables that targets public/anon/authenticated (RLS stays ENABLED: defense in depth;
--      service_role bypasses RLS and keeps its grants);
--   3. assert, in the same transaction, that no such relation still grants anything to anon/authenticated outside the
--      allowlist and no caller-facing policy is left.
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function. A future julia_* table must be locked the same way in its own
-- migration (this migration's assertion probe, julia_db_lockdown, fails the predeploy gate if one is not).
-- ============================================================================

SET search_path = social_wiring, public;

DO $lockdown$
DECLARE
  r       record;
  v_allow text[] := ARRAY[]::text[];  -- relations the FE legitimately reads directly: none (see WHY)
  v_n     int;
BEGIN
  FOR r IN
    SELECT c.relname, c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'social_wiring' AND c.relkind IN ('r', 'p', 'v', 'm')
       AND (c.relname LIKE 'julia\_%' OR c.relname LIKE 'lais\_%')
       AND c.relname <> ALL (v_allow)
     ORDER BY c.relname
  LOOP
    EXECUTE format('REVOKE ALL ON TABLE social_wiring.%I FROM PUBLIC, anon, authenticated', r.relname);
  END LOOP;

  FOR r IN
    SELECT p.policyname, p.tablename
      FROM pg_policies p
     WHERE p.schemaname = 'social_wiring'
       AND (p.tablename LIKE 'julia\_%' OR p.tablename LIKE 'lais\_%')
       AND p.tablename <> ALL (v_allow)
       AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[]
     ORDER BY p.tablename, p.policyname
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', r.policyname, r.tablename);
  END LOOP;

  -- assertion: nothing outside the allowlist still grants to a caller role
  SELECT count(*) INTO v_n
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
         LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
   WHERE n.nspname = 'social_wiring' AND c.relkind IN ('r', 'p', 'v', 'm')
     AND (c.relname LIKE 'julia\_%' OR c.relname LIKE 'lais\_%')
     AND c.relname <> ALL (v_allow)
     AND (a.grantee = 0 OR a.grantee IN (SELECT oid FROM pg_roles WHERE rolname IN ('anon', 'authenticated')));
  IF v_n > 0 THEN
    RAISE EXCEPTION 'migration 289: % julia_/lais_ grant(s) to PUBLIC/anon/authenticated remain outside the allowlist', v_n;
  END IF;

  SELECT count(*) INTO v_n
    FROM pg_policies p
   WHERE p.schemaname = 'social_wiring'
     AND (p.tablename LIKE 'julia\_%' OR p.tablename LIKE 'lais\_%')
     AND p.tablename <> ALL (v_allow)
     AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];
  IF v_n > 0 THEN
    RAISE EXCEPTION 'migration 289: % caller-facing julia_ RLS policy(ies) remain', v_n;
  END IF;
END
$lockdown$;
