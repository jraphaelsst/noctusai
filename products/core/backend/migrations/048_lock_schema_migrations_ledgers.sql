-- ============================================================================
-- 048_lock_schema_migrations_ledgers — RLS-lock every product's migration
-- ledger against PostgREST
-- ============================================================================
--
-- WHY THIS EXISTS
-- ---------------
-- `noctus.dev.migrate_product` creates `<schema>.schema_migrations` per
-- product (filename TEXT PRIMARY KEY, applied_at, checksum) via
-- `_ensure_tracking_table_sql`. Every product schema is exposed via
-- PostgREST (`authenticator`'s `pgrst.db_schemas`) with Postgres' default
-- grants to `anon`/`authenticated` on new tables — so a bare
-- `schema_migrations` table was readable AND writable over the REST API by
-- ANYONE. In particular: an unauthenticated caller could `INSERT` a fake
-- filename to make a future `migrate_product` run silently skip applying a
-- real migration (the ledger is trusted as "already applied").
--
-- LIVE FIX (already applied 2026-09-16, Supabase project
-- nyplttplcoyiiqjrvtiw): for every `schema_migrations` table outside the
-- Supabase-internal schemas (`auth`, `realtime`, `supabase_migrations`),
--   ALTER TABLE <schema>.schema_migrations ENABLE ROW LEVEL SECURITY;
--   REVOKE ALL ON <schema>.schema_migrations FROM anon, authenticated;
-- Verified: an anon REST call now returns `42501`; the Management-API
-- executor (the table owner — RLS never restricts the owner) still reads
-- and writes it fine, so `migrate_product` itself is unaffected.
--
-- This migration codifies that live fix as an idempotent DO-loop so a
-- fresh/rebuilt DB reproduces it, and `_ensure_tracking_table_sql` (in
-- `mcp/noctusai/tools/noctus/dev/migrate_product.py`) now emits both
-- statements for every NEWLY created ledger — preventing recurrence for
-- every product scaffolded from here on.
--
-- IDEMPOTENT
-- ----------
-- - `rowsecurity` is checked before the `ENABLE` so a table that is
--   already RLS'd is skipped for that leg (`ALTER ... ENABLE ROW LEVEL
--   SECURITY` is itself a no-op re-run, but the check keeps the loop from
--   emitting redundant DDL against tables it has already handled).
-- - `REVOKE ALL ... FROM anon, authenticated` is idempotent unconditionally
--   — revoking a privilege a role does not hold is a no-op, never an
--   error — so it always runs.
-- - A DB with zero `schema_migrations` tables (unlikely, but e.g. a fresh
--   scaffold-only checkout) is a no-op loop, not an error.
--
-- SOURCE OF TRUTH: verified live on Supabase project nyplttplcoyiiqjrvtiw,
-- 2026-09-16.
--
-- KB § PATTERNS/backend/database-rls.md
-- KB § PATTERNS/backend/migrate-product-mcp-tool.md
-- ============================================================================

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT n.nspname AS schema_name, c.relname AS table_name, c.relrowsecurity AS rls_enabled
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'schema_migrations'
          AND c.relkind = 'r'  -- ordinary table only
          AND n.nspname NOT IN ('auth', 'realtime', 'supabase_migrations')
    LOOP
        IF NOT r.rls_enabled THEN
            EXECUTE format(
                'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
                r.schema_name, r.table_name
            );
        END IF;

        EXECUTE format(
            'REVOKE ALL ON %I.%I FROM anon, authenticated',
            r.schema_name, r.table_name
        );
    END LOOP;
END
$$;
