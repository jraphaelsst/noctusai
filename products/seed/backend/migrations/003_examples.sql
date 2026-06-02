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
-- ============================================================================

CREATE TABLE seed.examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE seed.examples ENABLE ROW LEVEL SECURITY;

CREATE POLICY "examples_select_own_org" ON seed.examples
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "examples_insert_own_org" ON seed.examples
    FOR INSERT TO authenticated
    WITH CHECK (org_id = current_org_id());

CREATE POLICY "examples_update_own_org" ON seed.examples
    FOR UPDATE TO authenticated
    USING (org_id = current_org_id())
    WITH CHECK (org_id = current_org_id());

CREATE POLICY "examples_delete_own_org" ON seed.examples
    FOR DELETE TO authenticated
    USING (org_id = current_org_id());

CREATE INDEX idx_seed_examples_org ON seed.examples(org_id);
CREATE INDEX idx_seed_examples_ativo ON seed.examples(org_id, ativo);
