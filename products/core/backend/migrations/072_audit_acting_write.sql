-- Migration: 072_audit_acting_write
-- Schema: public (core)
-- Contract: projects/org-picker/CONTRACT.md -- closes NOC-REMEDIATE[org-picker-postgrest-audit]
--
-- WHY: a platform staff member who picked another org (core 070) can write that org's rows two
-- ways. FastAPI writes carry the audit row from the seed sink (role 'platform_support',
-- org_id = target, acting_org_id = home). A write the BROWSER sends straight to PostgREST while
-- acting carried NO audit row. This trigger closes that door at the data layer.
--
-- WHAT: public.audit_acting_write() -- AFTER INSERT/UPDATE/DELETE ... FOR EACH ROW,
-- TG_ARGV[0] = the product db_schema. Acting means
--   current_org_id_for(<schema>) IS DISTINCT FROM current_org_id()   (target <> home)
-- Anything else (customers, staff in their own org, service_role / migrations where auth.uid()
-- is NULL) exits on the first cheap checks and writes nothing. The audit row stores ids and
-- changed column NAMES only (never values -- LGPD):
--   org_id = target, user_id = auth.uid(), action = lower(TG_OP),
--   resource_type = '<schema>.<table>', resource_id = the row id, role = 'platform_support',
--   acting_org_id = home, act_as_session_id = the live platform_org_selections id.
-- A failed audit INSERT fails the write (fail closed: no unaudited acting write).
--
-- public.attach_acting_audit_triggers(p_schema) attaches the trigger idempotently to every base
-- table of a schema that has an org_id column (names starting '_' are skipped); product
-- migrations call it in one line once their schema is org-picker ready.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
SET search_path = public, public;

-- A selection id is not a session of the dropped act_as_sessions table; the column is reused
-- (no FK on either side), so say so.
COMMENT ON COLUMN public.audit_logs.act_as_session_id IS
    'The platform_org_selections.id (core 070) live while a platform staff member wrote as another '
    'org. Historic rows (<= core 066) hold the dropped act_as_sessions id.';

CREATE OR REPLACE FUNCTION public.audit_acting_write()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
DECLARE
  v_schema  text := TG_ARGV[0];
  v_uid     uuid := auth.uid();
  v_home    uuid;
  v_target  uuid;
  v_row     jsonb;
  v_cols    jsonb;
  v_sel     uuid;
  v_slug    text;
BEGIN
  IF v_schema IS NULL THEN
    RAISE EXCEPTION 'audit_acting_write: TG_ARGV[0] (product db_schema) is required';
  END IF;
  -- service_role / migrations / anon: no user, nothing to attribute.
  IF v_uid IS NULL THEN
    RETURN NULL;
  END IF;

  v_target := public.current_org_id_for(v_schema);
  v_home   := public.current_org_id();
  IF v_target IS NULL OR v_target IS NOT DISTINCT FROM v_home THEN
    RETURN NULL;  -- not acting in another org
  END IF;

  v_row := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;

  IF TG_OP = 'UPDATE' THEN
    SELECT COALESCE(jsonb_agg(k ORDER BY k), '[]'::jsonb) INTO v_cols
      FROM (SELECT COALESCE(n.key, o.key) AS k
              FROM jsonb_each(to_jsonb(NEW)) n
              FULL JOIN jsonb_each(to_jsonb(OLD)) o ON o.key = n.key
             WHERE n.value IS DISTINCT FROM o.value) d;
  ELSIF TG_OP = 'INSERT' THEN
    SELECT COALESCE(jsonb_agg(e.key ORDER BY e.key), '[]'::jsonb) INTO v_cols
      FROM jsonb_each(v_row) e WHERE e.value <> 'null'::jsonb;
  ELSE
    v_cols := '[]'::jsonb;
  END IF;

  SELECT s.id, p.slug INTO v_sel, v_slug
    FROM public.products p
    JOIN public.platform_org_selections s
      ON s.product_id = p.id AND s.user_id = v_uid AND s.ended_at IS NULL
   WHERE p.db_schema = v_schema
     AND s.auth_session_id = NULLIF(auth.jwt() ->> 'session_id', '')::uuid;

  INSERT INTO public.audit_logs
         (user_id, org_id, action, resource_type, resource_id, details,
          product_slug, role, actor_kind, client_hint, acting_org_id, act_as_session_id)
  VALUES (v_uid, v_target, lower(TG_OP), TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, v_row ->> 'id',
          jsonb_build_object('columns', v_cols, 'via', 'postgrest-trigger'),
          v_slug, 'platform_support', 'user', 'postgrest-trigger', v_home, v_sel);
  RETURN NULL;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.audit_acting_write() FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.audit_acting_write() TO service_role;

COMMENT ON FUNCTION public.audit_acting_write() IS
    'Row trigger (TG_ARGV[0] = product db_schema): when the caller is platform staff acting in another '
    'org (current_org_id_for(schema) <> current_org_id()), writes one audit_logs row (ids + changed '
    'column names only). No-op for everyone else.';

-- Idempotent attach: AFTER INSERT OR UPDATE OR DELETE on every base table of p_schema with an
-- org_id column. Returns how many tables carry the trigger afterwards.
-- p_product_schema = the PRODUCT's db_schema (what the selection is keyed by) when the tables live in
-- a sibling schema of the same chain (social-wiring's `mailing`); default = p_schema.
CREATE OR REPLACE FUNCTION public.attach_acting_audit_triggers(
    p_schema         text,
    p_product_schema text DEFAULT NULL
) RETURNS integer
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
DECLARE
  r record;
  v_count integer := 0;
  v_product text := COALESCE(p_product_schema, p_schema);
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.products WHERE db_schema = COALESCE(p_product_schema, p_schema)) THEN
    RAISE EXCEPTION 'attach_acting_audit_triggers: % is not a product db_schema', COALESCE(p_product_schema, p_schema);
  END IF;
  IF p_schema IS NULL OR NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = p_schema) THEN
    RAISE EXCEPTION 'attach_acting_audit_triggers: schema % does not exist', p_schema;
  END IF;
  FOR r IN
    SELECT c.oid, c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = p_schema
       AND c.relkind IN ('r', 'p')
       AND NOT c.relispartition
       AND left(c.relname, 1) <> '_'
       AND EXISTS (SELECT 1 FROM pg_attribute a
                    WHERE a.attrelid = c.oid AND a.attname = 'org_id'
                      AND a.attnum > 0 AND NOT a.attisdropped)
     ORDER BY c.relname
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS audit_acting_write ON %I.%I', p_schema, r.relname);
    EXECUTE format(
      'CREATE TRIGGER audit_acting_write AFTER INSERT OR UPDATE OR DELETE ON %I.%I '
      'FOR EACH ROW EXECUTE FUNCTION public.audit_acting_write(%L)',
      p_schema, r.relname, v_product);
    v_count := v_count + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.attach_acting_audit_triggers(text, text) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.attach_acting_audit_triggers(text, text) TO service_role;
