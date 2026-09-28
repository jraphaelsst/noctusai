-- Migration 056_invitation_token_lockdown_all_schemas.sql (2026-09-28)
-- Forward-only + idempotent.
--
-- WHY: SEC-2 locked `invitations.token` away from the API roles in every
-- product that has a live migration chain (core 055 + each product's
-- *_customer_role_isolation.sql). The platform-wide probe
-- `invitations.token_not_api_readable` still found 10 schemas exposing it
-- on prod: asleep/legacy products whose tables live in the shared DB but
-- that no awake product migrates (daily_life, erp, imobi_scheduling,
-- mailing, media_scheduling, personal-finance, therapy) plus orbity,
-- p_studio and igig. Core — the platform owner — sweeps them all.
--
-- Customers were already denied these ROWS (current_org_id() is NULL for a
-- customer role since 055); this closes the column PRIVILEGE for every org
-- member and anon, which is what the probe asserts.
--
-- Rendered from noctusai_lib.domain.sql_templates.invitation_token_lockdown_all_sql()
-- — the per-schema invitation_token_lockdown_sql()'s platform-wide sibling.

DO $lock_all$
DECLARE
  r record;
  v_cols text;
BEGIN
  FOR r IN
    SELECT n.nspname AS sch
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relname = 'invitations' AND c.relkind = 'r'
       AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
                    AND a.attname = 'token' AND NOT a.attisdropped)
  LOOP
    SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
      INTO v_cols
      FROM information_schema.columns
     WHERE table_schema = r.sch AND table_name = 'invitations'
       AND column_name <> 'token';
    EXECUTE format('REVOKE ALL ON %I.invitations FROM anon', r.sch);
    EXECUTE format('REVOKE SELECT ON %I.invitations FROM authenticated', r.sch);
    EXECUTE format('GRANT SELECT (%s) ON %I.invitations TO authenticated', v_cols, r.sch);
  END LOOP;
END
$lock_all$;
