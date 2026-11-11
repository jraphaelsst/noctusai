-- ROLLBACK of product migration 022 (nosnolimiar -> monica). RUN ONLY during the cutover window, BEFORE the app serves
-- traffic as `nosnolimiar` again. It is 022 with the two names swapped (same catalog-derived re-pointing of the
-- functions / RLS policies / acting-audit triggers / exposed-schemas list, same convergence guard).
-- ORDER: reverse core 120 FIRST (products.db_schema = 'monica' -- the acting-audit helper needs it), then this file,
-- afterwards the ledger lives in `monica.schema_migrations` again and step 7 deletes its 022 row, so a forward retry re-applies 022.
-- Not a migration: never place it under backend/migrations/.
DO $mig$
DECLARE
  v_old   constant text := 'nosnolimiar';
  v_new   constant text := 'monica';
  r       record;
  v_cur   text;
  v_next  text;
  v_left  text;
BEGIN
  -- 1. rename the schema (guarded) ---------------------------------------------------------------------------
  IF to_regnamespace(v_old) IS NOT NULL AND to_regnamespace(v_new) IS NULL THEN
    EXECUTE format('ALTER SCHEMA %I RENAME TO %I', v_old, v_new);
  ELSIF to_regnamespace(v_new) IS NULL THEN
    RAISE EXCEPTION 'rollback: neither schema % nor % exists', v_old, v_new;
  ELSIF to_regnamespace(v_old) IS NOT NULL THEN
    RAISE EXCEPTION 'rollback: BOTH schemas % and % exist -- refusing to guess which one is live', v_old, v_new;
  END IF;

  -- 2. the three SECURITY DEFINER functions: re-create from the live definition with the new name --------------
  FOR r IN
    SELECT p.oid, pg_get_functiondef(p.oid) AS def
      FROM pg_proc p
     WHERE p.pronamespace = to_regnamespace(v_new)
       AND (pg_get_functiondef(p.oid) LIKE '%' || v_old || '%')
  LOOP
    EXECUTE replace(r.def, v_old, v_new);
  END LOOP;

  -- 3. RLS policies carrying the 'monica' literal --------------------------------------------------------------
  FOR r IN
    SELECT schemaname, tablename, policyname, qual, with_check
      FROM pg_policies
     WHERE schemaname = v_new
       AND (coalesce(qual, '') LIKE '%''' || v_old || '''%' OR coalesce(with_check, '') LIKE '%''' || v_old || '''%')
  LOOP
    IF r.qual IS NOT NULL AND r.qual LIKE '%''' || v_old || '''%' THEN
      EXECUTE format('ALTER POLICY %I ON %I.%I USING (%s)', r.policyname, r.schemaname, r.tablename,
                     replace(r.qual, '''' || v_old || '''', '''' || v_new || ''''));
    END IF;
    IF r.with_check IS NOT NULL AND r.with_check LIKE '%''' || v_old || '''%' THEN
      EXECUTE format('ALTER POLICY %I ON %I.%I WITH CHECK (%s)', r.policyname, r.schemaname, r.tablename,
                     replace(r.with_check, '''' || v_old || '''', '''' || v_new || ''''));
    END IF;
  END LOOP;

  -- 4. acting-audit triggers (core 072) re-attached with the new schema arg (idempotent: drops + re-creates) -----
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'rollback requires public.attach_acting_audit_triggers(text, text) (core 072) -- apply core first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.products WHERE db_schema = v_new) THEN
    RAISE EXCEPTION 'rollback: public.products has no row with db_schema = % -- reverse core 120 FIRST', v_new;
  END IF;
  PERFORM public.attach_acting_audit_triggers(v_new);

  -- 5. PostgREST exposed schemas: SWAP old -> new in place (never leave a dangling schema) ----------------------
  SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_cur
    FROM (SELECT unnest(s.setconfig) AS cfg
            FROM pg_db_role_setting s JOIN pg_roles ro ON ro.oid = s.setrole
           WHERE ro.rolname = 'authenticator') t
   WHERE cfg LIKE 'pgrst.db_schemas=%';
  v_cur := coalesce(v_cur, 'public, graphql_public');
  SELECT string_agg(x, ', ' ORDER BY ord) INTO v_next
    FROM (SELECT DISTINCT ON (x) x, ord
            FROM (SELECT CASE WHEN btrim(e) = v_old THEN v_new ELSE btrim(e) END AS x, ord
                    FROM unnest(string_to_array(v_cur, ',')) WITH ORDINALITY AS u(e, ord)) m
           ORDER BY x, ord) d;
  IF v_next !~ ('(^|, )' || v_new || '(,|$)') THEN
    v_next := v_next || ', ' || v_new;
  END IF;
  IF v_next IS DISTINCT FROM v_cur THEN
    EXECUTE format('ALTER ROLE authenticator SET pgrst.db_schemas = %L', v_next);
    NOTIFY pgrst, 'reload config';
    NOTIFY pgrst, 'reload schema';
  END IF;

  -- 6. convergence guard: no literal of the old name may survive in the renamed schema ----------------------------
  SELECT string_agg(what, '; ') INTO v_left FROM (
    SELECT 'policy ' || policyname || ' on ' || tablename AS what FROM pg_policies
     WHERE schemaname = v_new AND (coalesce(qual, '') LIKE '%' || v_old || '%' OR coalesce(with_check, '') LIKE '%' || v_old || '%')
    UNION ALL
    SELECT 'function ' || p.proname FROM pg_proc p
     WHERE p.pronamespace = to_regnamespace(v_new) AND pg_get_functiondef(p.oid) LIKE '%' || v_old || '%'
    UNION ALL
    SELECT 'trigger ' || t.tgname || ' on ' || c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
     WHERE c.relnamespace = to_regnamespace(v_new) AND NOT t.tgisinternal
       AND encode(t.tgargs, 'escape') LIKE '%' || v_old || '%'
  ) z;
  IF v_left IS NOT NULL THEN
    RAISE EXCEPTION 'rollback: literals of the old schema name survive in %: %', v_new, v_left;
  END IF;

  -- 7. forget 022 in the ledger we just renamed back, so a forward retry re-applies it (otherwise migrate_product
  --    sees 022 as done and leaves the schema named `monica`). The ledger travelled with the schema rename.
  IF to_regclass(format('%I.schema_migrations', v_new)) IS NOT NULL THEN
    EXECUTE format('DELETE FROM %I.schema_migrations WHERE filename = %L', v_new, '022_rename_schema.sql');
  END IF;
END
$mig$;
