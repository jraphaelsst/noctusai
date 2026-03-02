-- ============================================================
-- License History — Allow multiple license records per org+product
--
-- Previously: UNIQUE(org_id, product_id) enforced one record per pair.
-- Now: Multiple records allowed (active + historical revoked/expired).
-- A partial unique index ensures only ONE active license per org+product.
--
-- Idempotent — safe to re-run.
-- ============================================================

-- 1. Drop ALL unique constraints on licenses that cover (org_id, product_id)
--    This catches every possible naming convention Supabase/PostgreSQL may use.
DO $$
DECLARE
    r RECORD;
BEGIN
    -- Drop unique CONSTRAINTS (from ALTER TABLE ... ADD CONSTRAINT / inline UNIQUE)
    FOR r IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'licenses'
          AND con.contype = 'u'  -- unique constraint
          AND EXISTS (
              SELECT 1 FROM unnest(con.conkey) k
              JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = k
              WHERE a.attname IN ('org_id', 'product_id')
          )
    LOOP
        RAISE NOTICE 'Dropping constraint: %', r.conname;
        EXECUTE format('ALTER TABLE licenses DROP CONSTRAINT IF EXISTS %I', r.conname);
    END LOOP;

    -- Drop unique INDEXES (from CREATE UNIQUE INDEX) that are NOT the partial one
    FOR r IN
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'licenses'
          AND indexdef LIKE '%UNIQUE%'
          AND indexdef LIKE '%org_id%'
          AND indexdef LIKE '%product_id%'
          AND indexdef NOT LIKE '%WHERE%'
    LOOP
        RAISE NOTICE 'Dropping index: %', r.indexname;
        EXECUTE format('DROP INDEX IF EXISTS %I', r.indexname);
    END LOOP;
END $$;

-- 2. Ensure the partial unique index exists (only one ACTIVE license per org+product)
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_one_active_per_org_product
    ON licenses (org_id, product_id)
    WHERE status = 'active';
