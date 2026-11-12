-- orbity hardening, round 2 of the service-role refactor (security review of 034). Forward-only, re-runnable.
--
-- 1. UPSERT TAKEOVER (F1): the org-bound client now refuses an upsert whose conflict target lacks org_id, because
--    `ON CONFLICT (id) DO UPDATE SET org_id = <mine>` would move another tenant's row into the caller's org. The two
--    upserts whose arbiter was a global key get a COMPOSITE unique index that leads with org_id (the old, stricter keys
--    stay: they can never be violated by the new ones). Tables are small and new: plain CREATE UNIQUE INDEX, short lock_timeout.
-- 2. seed_default_lead_stages (F2): SECURITY DEFINER, no search_path and executable by PUBLIC => anyone could insert stages
--    into any org. Locked to service_role, search_path pinned (the body is already schema-qualified). set_updated_at gets
--    the pinned search_path too (a trigger function: nobody needs to EXECUTE it directly).
-- 3. Default privileges (F3): 001 granted ALL on every FUTURE orbity table to `authenticated` (and sequences to anon). Revoked,
--    and every existing table/sequence/function is swept: the browser roles keep ONLY `SELECT` on orbity.status_pagina (the
--    shared nav-status panel READS it through PostgREST under its SELECT policies; the writes go through the seed admin router
--    with the service role; anon reads it, 016).
--    NB: Postgres has no schema-scoped way to drop the implicit `EXECUTE ... TO PUBLIC` on future functions (only the
--    cluster-wide `ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`, which would change every product),
--    so a new function is gated by tests/test_service_only_lockdown.py: it must REVOKE ... FROM PUBLIC in the same file.
--    The schema-scoped FUNCTIONS revoke below is a NO-OP kept for the record: the test is the enforcement.
--
-- POST-APPLY VERIFICATION (run as postgres; default-privilege revokes only apply to the role that GRANTED them, so check the
-- creator role of future objects too -- `defaclrole`):
--   SELECT defaclrole::regrole, defaclobjtype, defaclacl FROM pg_default_acl WHERE defaclnamespace = 'orbity'::regnamespace;
--   -> no row may list anon / authenticated / PUBLIC (=) for tables 'r' or sequences 'S'; service_role may.
--   SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
--    WHERE table_schema = 'orbity' AND grantee IN ('anon', 'authenticated', 'PUBLIC');
--   -> only (anon|authenticated, status_pagina, SELECT).
SET search_path = orbity, public;
SET lock_timeout = '5s';

-- 1. composite arbiters ------------------------------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS campaign_metrics_org_campaign_date_ux ON orbity.campaign_metrics (org_id, campaign_id, date);
CREATE UNIQUE INDEX IF NOT EXISTS lead_scoring_results_org_lead_ux ON orbity.lead_scoring_results (org_id, lead_id);

-- 2. functions ---------------------------------------------------------------------------------------------------------
ALTER FUNCTION orbity.seed_default_lead_stages(UUID) SET search_path = '';
REVOKE ALL ON FUNCTION orbity.seed_default_lead_stages(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION orbity.seed_default_lead_stages(UUID) TO service_role;
ALTER FUNCTION orbity.set_updated_at() SET search_path = '';

-- 3. privileges --------------------------------------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES IN SCHEMA orbity REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA orbity REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
-- (no-op, see the header) ALTER DEFAULT PRIVILEGES IN SCHEMA orbity REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

REVOKE ALL ON ALL TABLES IN SCHEMA orbity FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA orbity FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA orbity FROM PUBLIC, anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA orbity TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA orbity TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA orbity TO service_role;
-- the one deliberate browser surface (see header)
GRANT SELECT ON orbity.status_pagina TO authenticated, anon;
