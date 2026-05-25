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
-- RLS mirrors {{SCHEMA_NAME}}.invitations (the `org_id = jwt.org_id` subquery shape the
-- scaffold convention uses). Full CRUD ⇒ a policy per command.
-- ============================================================================

CREATE TABLE {{SCHEMA_NAME}}.examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE {{SCHEMA_NAME}}.examples ENABLE ROW LEVEL SECURITY;

CREATE POLICY "examples_select_own_org" ON {{SCHEMA_NAME}}.examples
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "examples_insert_own_org" ON {{SCHEMA_NAME}}.examples
    FOR INSERT TO authenticated
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "examples_update_own_org" ON {{SCHEMA_NAME}}.examples
    FOR UPDATE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "examples_delete_own_org" ON {{SCHEMA_NAME}}.examples
    FOR DELETE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_{{SCHEMA_NAME}}_examples_org ON {{SCHEMA_NAME}}.examples(org_id);
CREATE INDEX idx_{{SCHEMA_NAME}}_examples_ativo ON {{SCHEMA_NAME}}.examples(org_id, ativo);
