-- ============================================================================
-- 022 -- rename the Postgres schema `monica` -> `nosnolimiar` (product rename 2026-11-02)
-- ============================================================================
-- The product `monica` became `nosnolimiar` ("Nós no Limiar"). A schema RENAME alone is NOT enough -- four
-- things carry the OLD name as a *literal* that ALTER SCHEMA does not touch, and each fails SILENTLY:
--   1. RLS policies: `USING (org_id = (SELECT public.current_org_id_for('monica')))` -- a string literal. After the
--      rename it resolves to NULL, so every authenticated read returns nothing.
--   2. the acting-audit triggers (core 072): `audit_acting_write('monica')` -- TG_ARGV[0] is the schema name, so a
--      stale arg disables the platform-staff audit trail without an error.
--   3. the SECURITY DEFINER functions: `SET search_path = ..., monica, ...` (all three) and `monica.` in the bodies
--      of fin_settle_entry_locked / fin_reverse_settlement_locked.
--   4. PostgREST's exposed list (authenticator `pgrst.db_schemas`): a dangling `monica` plus a missing
--      `nosnolimiar` (ensure_schema_exposure is append-only and would leave the dangling entry).
-- INDEX NAMES (`idx_monica_*`) are deliberately NOT renamed: they are the names the frozen, applied migrations declare
-- (check_migration_guard_has_probe + verify_db_guards bind to them); an index name carries no behaviour.
-- Everything is derived from the live catalog (pg_policies / pg_get_functiondef / pg_class), never copied, and a
-- final guard RAISES (rolling the whole statement back) if any literal `monica` survives in the schema.
--
-- ORDER (prod): core 120 FIRST (products.db_schema = 'nosnolimiar' -- the acting-audit step needs it), then this file.
--   migrate_product product=nosnolimiar schema=monica confirm=True   -- the ledger still lives in `monica`
--   migrate_product product=nosnolimiar confirm=True                 -- no-op re-run: records 022 in the renamed ledger
-- FRESH DB: `nosnolimiar` holding only the ledger (migrate_product's default schema) is adopted -- see step 0.
-- IDEMPOTENT: re-runnable at any point (the rename is guarded; every other step is a no-op once converged).
-- ROLLBACK: projects/rename-2026-11/rollback-022.sql (this same block with the names swapped).
-- KB § PATTERNS/devops/product-lockfile-and-slug-drift.md · project-history/roadmaps/nosnolimiar-rename-2026-11.md
-- ============================================================================

DO $mig$
DECLARE
  v_old   constant text := 'monica';
  v_new   constant text := 'nosnolimiar';
  r       record;
  v_cur   text;
  v_next  text;
  v_left  text;
BEGIN
  -- 0. fresh-DB bootstrap: `migrate_product` WITHOUT schema=monica creates `nosnolimiar` + its ledger FIRST, then 001
  --    creates `monica`. Adopt that shape: when `nosnolimiar` holds NOTHING but the ledger, fold the ledger into
  --    `monica` (move it, or merge its rows into monica's own), drop the empty schema, and fall through to the rename.
  --    Anything else in `nosnolimiar` is a real second schema: keep refusing below. Prod (no `nosnolimiar` yet) never
  --    enters this branch.
  IF to_regnamespace(v_old) IS NOT NULL AND to_regnamespace(v_new) IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_class c
                      WHERE c.relnamespace = to_regnamespace(v_new)
                        AND c.relname <> 'schema_migrations' AND c.relkind <> 'i')
     AND NOT EXISTS (SELECT 1 FROM pg_proc p WHERE p.pronamespace = to_regnamespace(v_new)) THEN
    IF to_regclass(format('%I.schema_migrations', v_new)) IS NOT NULL THEN
      IF to_regclass(format('%I.schema_migrations', v_old)) IS NULL THEN
        EXECUTE format('ALTER TABLE %I.schema_migrations SET SCHEMA %I', v_new, v_old);
      ELSE
        EXECUTE format('INSERT INTO %I.schema_migrations (filename, applied_at, checksum) '
                       'SELECT filename, applied_at, checksum FROM %I.schema_migrations ON CONFLICT (filename) DO NOTHING',
                       v_old, v_new);
        EXECUTE format('DROP TABLE %I.schema_migrations', v_new);
      END IF;
    END IF;
    EXECUTE format('DROP SCHEMA %I', v_new);   -- RESTRICT: fails loudly if anything unexpected is left
  END IF;

  -- 1. rename the schema (guarded) ---------------------------------------------------------------------------
  IF to_regnamespace(v_old) IS NOT NULL AND to_regnamespace(v_new) IS NULL THEN
    EXECUTE format('ALTER SCHEMA %I RENAME TO %I', v_old, v_new);
  ELSIF to_regnamespace(v_new) IS NULL THEN
    RAISE EXCEPTION '022: neither schema % nor % exists', v_old, v_new;
  ELSIF to_regnamespace(v_old) IS NOT NULL THEN
    RAISE EXCEPTION '022: BOTH schemas % and % exist -- refusing to guess which one is live', v_old, v_new;
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
    RAISE EXCEPTION '022 requires public.attach_acting_audit_triggers(text, text) (core 072) -- apply core first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.products WHERE db_schema = v_new) THEN
    RAISE EXCEPTION '022: public.products has no row with db_schema = % -- apply core 120 first', v_new;
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
    RAISE EXCEPTION '022: literals of the old schema name survive in %: %', v_new, v_left;
  END IF;
END
$mig$;
