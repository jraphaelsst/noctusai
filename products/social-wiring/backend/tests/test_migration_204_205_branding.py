"""Structural tests for `*_branding_model.sql` (schema) and
`*_branding_marcas_data.sql` (the owner's marca data).

Parse-based like the other migration tests: the migrations are FILES, not
applied changes. They pin the safety shape the owner asked for — forward-only,
idempotent, private bucket, the data step org-guarded and separate.
"""
from __future__ import annotations

from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
OWNER_ORG = "6dd73140-74a4-41c6-aeff-bc94b5312b53"


def _load(name: str) -> tuple[str, str, str]:
    path = migration_path(MIGRATIONS, name)
    sql = path.read_text(encoding="utf-8")
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return sql, code, " ".join(code.split())


@pytest.fixture(scope="module")
def schema():
    return _load("branding_model.sql")


@pytest.fixture(scope="module")
def data():
    return _load("branding_marcas_data.sql")


@pytest.mark.parametrize("name", ["branding_model.sql", "branding_marcas_data.sql"])
def test_migrations_parse(name):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(migration_path(MIGRATIONS, name).read_text(encoding="utf-8"))) > 0


class TestSchema:
    def test_forward_only(self, schema):
        upper = schema[1].upper()
        for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM"):
            assert forbidden not in upper

    def test_idempotent_ddl(self, schema):
        flat = schema[2]
        assert "SET search_path = social_wiring, public;" in flat
        for stmt in ("ADD COLUMN IF NOT EXISTS tokens", "ADD COLUMN IF NOT EXISTS brand_book",
                     "ADD COLUMN IF NOT EXISTS sections", "ADD COLUMN IF NOT EXISTS is_template",
                     "CREATE TABLE IF NOT EXISTS social_wiring.mc_brand_components",
                     "ADD COLUMN IF NOT EXISTS storage_path"):
            assert stmt in flat, stmt
        # every CREATE INDEX is IF NOT EXISTS
        assert flat.upper().count("CREATE UNIQUE INDEX") == flat.upper().count("CREATE UNIQUE INDEX IF NOT EXISTS")
        assert flat.count("CREATE INDEX") == flat.count("CREATE INDEX IF NOT EXISTS")

    def test_one_template_per_org_and_template_has_no_marca(self, schema):
        flat = schema[2]
        assert "ON social_wiring.mc_brand_kits (org_id) WHERE is_template" in flat
        assert "CHECK (NOT is_template OR marca_id IS NULL)" in flat

    def test_components_table_is_rls_protected(self, schema):
        flat = schema[2]
        assert "ALTER TABLE social_wiring.mc_brand_components ENABLE ROW LEVEL SECURITY" in flat
        assert "FOR SELECT TO authenticated USING (org_id = current_org_id())" in flat
        assert "FOR ALL TO service_role USING (true) WITH CHECK (true)" in flat
        assert "UNIQUE (brand_kit_id, name)" in flat

    def test_reference_kinds_gain_logo_and_font(self, schema):
        assert "CHECK (kind IN ('model','prompt','palette','typography','logo','font'))" in schema[2]

    def test_bucket_is_private_with_org_first_object_rls(self, schema):
        flat = schema[2]
        assert "VALUES ('social-wiring-branding', 'social-wiring-branding', false)" in flat
        assert "true)" not in flat.split("storage.buckets")[1].split(";")[0]
        assert flat.count("(storage.foldername(name))[1] = public.current_org_id()::text") == 4

    def test_svg_render_override_column_untouched(self, schema):
        assert "design_tokens" not in schema[1].replace("COMMENT ON COLUMN social_wiring.mc_brand_kits.design_tokens", "")


class TestData:
    def test_is_org_guarded_noop_elsewhere(self, data):
        flat = data[2]
        assert OWNER_ORG in flat
        assert "IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = v_org)" in flat
        assert "RETURN;" in flat

    def test_adds_exactly_the_three_marcas_idempotently(self, data):
        flat = data[2]
        assert "INSERT INTO social_wiring.marcas (org_id, slug, name, kind)" in flat
        assert "'gilson-tangerino', 'Gilson Tangerino', 'pessoa_fisica'" in flat
        assert "'nos-no-limiar', 'Nós no Limiar', 'empresa'" in flat
        assert "'noctusai', 'NoctusAI', 'empresa'" in flat
        assert "ON CONFLICT (org_id, slug) DO NOTHING" in flat

    def test_attaches_one_design_to_one_consultoria_only_when_unattached(self, data):
        flat = data[2]
        assert "ddfd4c20-fdab-4466-94a0-21f411f55adc" in flat
        assert "c2b77620-c550-48e1-b789-b680c7e6bb0d" in flat
        assert "AND k.marca_id IS NULL" in flat
        assert "AND k.org_id = v_org" in flat

    def test_data_only_no_ddl_no_deletes(self, data):
        upper = data[1].upper()
        for forbidden in ("CREATE TABLE", "ALTER TABLE", "DROP ", "DELETE FROM", "TRUNCATE"):
            assert forbidden not in upper
