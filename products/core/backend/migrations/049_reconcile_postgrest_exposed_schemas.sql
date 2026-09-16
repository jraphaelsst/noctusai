-- ============================================================================
-- 049_reconcile_postgrest_exposed_schemas — codify the live PostgREST
-- schema-exposure list, append-only + idempotent
-- ============================================================================
--
-- WHY THIS EXISTS
-- ---------------
-- A new product's schema MUST be in `authenticator`'s `pgrst.db_schemas`
-- GUC, or every REST call the product's backend makes against its own
-- tables fails with `PGRST106` (memory
-- `feedback_new_product_schema_must_be_postgrest_exposed`). Every product
-- scaffolded so far has appended itself to this list one at a time — over
-- many separate migrations across many products (see e.g.
-- `products/p-studio/backend/migrations/002_plataforma_e_seeds.sql`) — so
-- there has never been ONE place a fresh/rebuilt DB could read to
-- reproduce the CURRENT live list in one shot.
--
-- This migration is that place. Verified live on Supabase project
-- nyplttplcoyiiqjrvtiw, 2026-09-16:
--
--   public, graphql_public, erp, personal-finance, therapy, seed,
--   daily_life, mailing, social_wiring, orbity, pilates, igig, p_studio,
--   community, academia_de_reciclagem, agents
--
-- `public` + `graphql_public` are Supabase's own defaults (the
-- `COALESCE` fallback every per-product append migration already assumes
-- when the GUC is entirely unset) and are never appended by this file —
-- only the product schemas that were added ON TOP of those defaults are
-- listed below.
--
-- APPEND-ONLY + IDEMPOTENT — SAME AS EVERY PER-PRODUCT LEG
-- ---------------------------------------------------------
-- This does NOT overwrite `pgrst.db_schemas` with the literal list above.
-- Doing so would be exactly the near-miss documented in
-- `products/p-studio/backend/migrations/002_plataforma_e_seeds.sql`
-- (memory `feedback_postgrest_exposed_schema_drop`): a literal list
-- written against a shared, constantly-mutating DB can DROP a schema that
-- was added between when the list was copied and when the migration
-- runs, taking that product's REST API down fleet-wide with no error at
-- all (`ALTER ROLE ... SET` always "succeeds").
--
-- Instead: for each schema below, in order, read the CURRENT
-- `pgrst.db_schemas` value and append that schema ONLY if it is not
-- already present. Run against:
--   - a FRESH DB (GUC unset → falls back to `public, graphql_public`) —
--     every schema below gets appended in order, reproducing the live
--     list exactly;
--   - the ALREADY-LIVE DB — every schema is already present, so every
--     iteration is a no-op;
--   - a DB somewhere in between (a product's own onboarding migration
--     already ran, others haven't) — only the missing ones get appended,
--     nothing already-present is touched, nothing is dropped or
--     reordered.
--
-- One `NOTIFY pgrst` pair fires at the end (not once per schema) — no
-- functional difference for a DDL-only reload, and avoids N redundant
-- schema-cache rebuilds when bootstrapping a fresh DB.
--
-- SOURCE OF TRUTH: verified live on Supabase project nyplttplcoyiiqjrvtiw,
-- 2026-09-16.
--
-- KB § PATTERNS/backend/database-rls.md
-- KB § PATTERNS/backend/migrate-product-mcp-tool.md
-- KB § GUIDES/new-product.md
-- ============================================================================

DO $$
DECLARE
    v_targets  CONSTANT text[] := ARRAY[
        'erp', 'personal-finance', 'therapy', 'seed', 'daily_life',
        'mailing', 'social_wiring', 'orbity', 'pilates', 'igig',
        'p_studio', 'community', 'academia_de_reciclagem', 'agents'
    ];
    v_target   text;
    v_current  text;
BEGIN
    FOREACH v_target IN ARRAY v_targets LOOP
        SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_current
        FROM (
            SELECT unnest(setconfig) AS cfg
            FROM pg_db_role_setting s
            JOIN pg_roles r ON r.oid = s.setrole
            WHERE r.rolname = 'authenticator'
        ) t
        WHERE cfg LIKE 'pgrst.db_schemas=%';

        v_current := COALESCE(v_current, 'public, graphql_public');

        IF v_current !~ ('(^|,)\s*' || v_target || '\s*(,|$)') THEN
            EXECUTE format(
                'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
                v_current || ', ' || v_target
            );
        END IF;
    END LOOP;

    NOTIFY pgrst, 'reload config';
    NOTIFY pgrst, 'reload schema';
END
$$;
