-- ============================================================================
-- Migration 245 — drop the retired legacy `mailing` schema.
--
-- WHY: owner decision 2026-10-10 — the legacy `mailing` product is retired
-- for good; everything of value was harvested into app/modules/email_marketing
-- (its own ai_outputs/ai_feedback in 239; consent keys renamed; tests ported;
-- unsubscribe / segmentation UI; the four missing capabilities built). Prod
-- `mailing` held 16 tables, 0 rows except status_pagina (9 legacy nav rows);
-- no FK, view or function outside the schema depends on it. Snapshot (catalog
-- + every row) taken before the drop: ~/.noctusai/private/incidents/
-- 2026-10-10-mailing-teardown/.
--
-- ORDER, by construction: core 077 must have removed `mailing` from
-- authenticator's pgrst.db_schemas first — dropping an exposed schema can break
-- PostgREST's schema reload for every product. This refuses while it is still
-- exposed. Idempotent (DROP ... IF EXISTS).
--
-- SW 012/212/214 (which altered `mailing`) stay — applied files are immutable;
-- on a fresh chain they remain known residue [mailing-schema-migration].
-- ============================================================================

DO $$
DECLARE
    v_exposed text;
BEGIN
    SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_exposed
    FROM (
        SELECT unnest(setconfig) AS cfg
        FROM pg_db_role_setting s
        JOIN pg_roles r ON r.oid = s.setrole
        WHERE r.rolname = 'authenticator'
    ) t
    WHERE cfg LIKE 'pgrst.db_schemas=%';

    IF v_exposed IS NOT NULL AND v_exposed ~ '(^|,)\s*mailing\s*(,|$)' THEN
        RAISE EXCEPTION 'migration 245 requires core 077 (mailing still in pgrst.db_schemas) -- apply core first';
    END IF;

    DROP SCHEMA IF EXISTS mailing CASCADE;
END
$$;
