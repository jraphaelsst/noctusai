-- ============================================================================
-- 003_examples.sql — the canonical example domain table.
--
-- This is the **page-scoped CRUD reference** every scaffolded product
-- inherits (product-internal-wiring rule, KB § PATTERNS/product-internal-wiring.md):
-- the `example` router/service/schema + this table + the `Example.tsx`
-- page that consumes `<ResourceManager/>` together demonstrate a *fully
-- wired, fully manageable* surface — list + create + edit + soft-delete,
-- all from the page, no raw SQL.
--
-- TODO(new-product): rename `examples` → your domain table everywhere
-- (migration + service + router + schema + page) and replace the
-- placeholder `title`/`description` columns with your real fields.
--
-- RLS uses public.current_org_id() — the SECURITY DEFINER trusted-table resolver
-- declared in 001_seed.sql. auth.jwt() ->> 'org_id' (top-level) is always NULL
-- in Supabase; see memory/feedback_rls_never_key_on_user_metadata.md.
-- Full CRUD ⇒ a policy per command.
--
-- IDEMPOTENT BY CONSTRUCTION (safe on a second apply — `noctus.dev.migration_replay`
-- applies every new migration twice). Diverges on purpose from the applied,
-- immutable products/seed copy; declared in templates/product-seed-divergences.json.
-- ============================================================================

CREATE TABLE IF NOT EXISTS monica.examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE monica.examples ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "examples_select_own_org" ON monica.examples;
CREATE POLICY "examples_select_own_org" ON monica.examples
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

DROP POLICY IF EXISTS "examples_insert_own_org" ON monica.examples;
CREATE POLICY "examples_insert_own_org" ON monica.examples
    FOR INSERT TO authenticated
    WITH CHECK (org_id = current_org_id());

DROP POLICY IF EXISTS "examples_update_own_org" ON monica.examples;
CREATE POLICY "examples_update_own_org" ON monica.examples
    FOR UPDATE TO authenticated
    USING (org_id = current_org_id())
    WITH CHECK (org_id = current_org_id());

DROP POLICY IF EXISTS "examples_delete_own_org" ON monica.examples;
CREATE POLICY "examples_delete_own_org" ON monica.examples
    FOR DELETE TO authenticated
    USING (org_id = current_org_id());

CREATE INDEX IF NOT EXISTS idx_monica_examples_org ON monica.examples(org_id);
CREATE INDEX IF NOT EXISTS idx_monica_examples_ativo ON monica.examples(org_id, ativo);
