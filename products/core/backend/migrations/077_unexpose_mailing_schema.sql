-- ============================================================================
-- Migration 077 — PostgREST stops exposing the retired `mailing` schema.
--
-- WHY: the owner retired the legacy `mailing` product for good (2026-10-10):
-- its value was harvested into social-wiring's email_marketing module and the
-- schema is dropped by social-wiring 245. 049 had added `mailing` to
-- `authenticator`'s pgrst.db_schemas; an exposed schema that no longer exists
-- can break PostgREST's schema-cache reload for EVERY product, so this runs
-- FIRST — SW 245 refuses to drop while `mailing` is still exposed.
--
-- Removes exactly the `mailing` entry from the current list (whatever else is
-- there is kept verbatim, order preserved) and reloads PostgREST. Idempotent.
-- ============================================================================

DO $$
DECLARE
    v_current text;
    v_kept    text;
BEGIN
    SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_current
    FROM (
        SELECT unnest(setconfig) AS cfg
        FROM pg_db_role_setting s
        JOIN pg_roles r ON r.oid = s.setrole
        WHERE r.rolname = 'authenticator'
    ) t
    WHERE cfg LIKE 'pgrst.db_schemas=%';

    IF v_current IS NULL THEN
        RAISE NOTICE 'authenticator has no pgrst.db_schemas setting — nothing to unexpose';
        RETURN;
    END IF;

    SELECT string_agg(s, ', ' ORDER BY ord) INTO v_kept
    FROM (
        SELECT btrim(part) AS s, ord
        FROM unnest(string_to_array(v_current, ',')) WITH ORDINALITY AS u(part, ord)
    ) parts
    WHERE s <> '' AND s <> 'mailing';

    IF v_kept IS DISTINCT FROM v_current THEN
        EXECUTE format('ALTER ROLE authenticator SET pgrst.db_schemas = %L', v_kept);
        NOTIFY pgrst, 'reload config';
        NOTIFY pgrst, 'reload schema';
    END IF;
END
$$;
