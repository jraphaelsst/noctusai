"""Regression tests for ``noctus.dev.compliance.check_table_has_rls`` —
ADVISORY detector for a `CREATE TABLE` with no matching `ENABLE ROW LEVEL
SECURITY`, static or dynamic.

THE FALSE-POSITIVE INCIDENT this keeper's dynamic-form resolution exists
for: RLS is very often enabled on a BATCH of tables via a `DO $$ ...
FOREACH t IN ARRAY ARRAY[...] LOOP EXECUTE format('ALTER TABLE %I ENABLE
ROW LEVEL SECURITY', t) ... END $$;` block (see `products/social-wiring/
backend/migrations/065_campanhas.sql:165-190` and
`101_permutas_matching.sql:430-458`) — or, on `erp-imobiliario`, the
`FOR t IN SELECT unnest(ARRAY[...])` loop shape. A naive literal
`grep "ENABLE ROW LEVEL SECURITY"` cannot see either dynamic form and
reported 66 "exposed" tables in `social_wiring` when the live number was 4.
This keeper resolves BOTH dynamic shapes.

All tests operate against an isolated ``tmp_path`` tree, never the real
repo — hermetic and fast.

KB § PATTERNS/backend/database-rls.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_table_has_rls


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_products_root(tmp_path: Path) -> Path:
    (tmp_path / "products").mkdir()
    return tmp_path


class TestUnprotectedTableIsFlagged:
    """The actual-refusal bar: a genuinely unprotected table must produce
    a finding, not just an empty successful run."""

    def test_create_table_with_no_rls_at_all_is_flagged(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "CREATE TABLE demo.widgets (\n"
            "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
            "    org_id UUID NOT NULL\n"
            ");\n",
        )

        issues = check_table_has_rls(repo_root=root)

        assert len(issues) == 1
        assert issues[0]["file"] == "products/demo/backend/migrations/001_demo.sql"
        assert "demo.widgets" in issues[0]["issue"]
        assert issues[0]["severity"] == "high"

    def test_bare_table_no_schema_prefix_with_no_rls_is_flagged(self, tmp_path):
        """`core`-style tables (public schema, no explicit prefix)."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/core/backend/migrations/001_core.sql",
            "CREATE TABLE IF NOT EXISTS widgets (\n"
            "    id UUID PRIMARY KEY\n"
            ");\n",
        )

        issues = check_table_has_rls(repo_root=root)

        assert len(issues) == 1
        assert "widgets" in issues[0]["issue"]


class TestStaticRlsIsRecognized:
    def test_create_table_with_static_enable_rls_is_clean(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "CREATE TABLE demo.widgets (id UUID PRIMARY KEY);\n"
            "ALTER TABLE demo.widgets ENABLE ROW LEVEL SECURITY;\n",
        )

        assert check_table_has_rls(repo_root=root) == []

    def test_quoted_hyphenated_schema_is_recognized(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/personal-finance/backend/migrations/001_pf.sql",
            'CREATE TABLE "personal-finance".contas (id UUID PRIMARY KEY);\n'
            'ALTER TABLE "personal-finance".contas ENABLE ROW LEVEL SECURITY;\n',
        )

        assert check_table_has_rls(repo_root=root) == []


class TestDynamicForeachArrayShapeIsRecognized:
    """The exact shape from social-wiring 065_campanhas.sql / 101 —
    MUST NOT be flagged. This is the regression for the 66-vs-4 incident."""

    def test_foreach_in_array_batch_enable_is_recognized(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/social-wiring/backend/migrations/065_campanhas.sql",
            "CREATE TABLE social_wiring.campanhas (id UUID PRIMARY KEY);\n"
            "CREATE TABLE social_wiring.campanha_imoveis (id UUID PRIMARY KEY);\n"
            "CREATE TABLE social_wiring.campanha_veiculacoes (id UUID PRIMARY KEY);\n"
            "CREATE TABLE social_wiring.campanha_solicitacoes (id UUID PRIMARY KEY);\n"
            "\n"
            "DO $$\n"
            "DECLARE t TEXT;\n"
            "BEGIN\n"
            "    FOREACH t IN ARRAY ARRAY[\n"
            "        'campanhas', 'campanha_imoveis', 'campanha_veiculacoes', 'campanha_solicitacoes'\n"
            "    ] LOOP\n"
            "        EXECUTE format('ALTER TABLE social_wiring.%I ENABLE ROW LEVEL SECURITY', t);\n"
            "        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_select_own_org', t);\n"
            "        EXECUTE format(\n"
            "            'CREATE POLICY %I ON social_wiring.%I FOR SELECT TO authenticated '\n"
            "            'USING (org_id = public.current_org_id())',\n"
            "            t || '_select_own_org', t);\n"
            "    END LOOP;\n"
            "END $$;\n",
        )

        assert check_table_has_rls(repo_root=root) == []

    def test_foreach_array_shape_from_permutas_migration_is_recognized(self, tmp_path):
        """101_permutas_matching.sql's shape — a second, differently-named
        write policy inside the same loop must not confuse the correlation."""
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/social-wiring/backend/migrations/101_permutas_matching.sql",
            "CREATE TABLE social_wiring.permuta_ativos (id UUID PRIMARY KEY);\n"
            "CREATE TABLE social_wiring.permuta_interesses (id UUID PRIMARY KEY);\n"
            "CREATE TABLE social_wiring.permuta_matches (id UUID PRIMARY KEY);\n"
            "\n"
            "DO $$\n"
            "DECLARE\n"
            "    t TEXT;\n"
            "BEGIN\n"
            "    FOREACH t IN ARRAY ARRAY['permuta_ativos', 'permuta_interesses', 'permuta_matches']\n"
            "    LOOP\n"
            "        EXECUTE format('ALTER TABLE social_wiring.%I ENABLE ROW LEVEL SECURITY', t);\n"
            "        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_write_own_org', t);\n"
            "        EXECUTE format(\n"
            "            'CREATE POLICY %I ON social_wiring.%I FOR ALL TO authenticated '\n"
            "            'USING (org_id = public.current_org_id()) '\n"
            "            'WITH CHECK (org_id = public.current_org_id())',\n"
            "            t || '_write_own_org', t);\n"
            "    END LOOP;\n"
            "END\n"
            "$$;\n",
        )

        assert check_table_has_rls(repo_root=root) == []


class TestDynamicForUnnestArrayShapeIsRecognized:
    """erp-imobiliario 001's `FOR t IN SELECT unnest(ARRAY[...])` shape —
    a second recurring dynamic-batch convention on this platform."""

    def test_for_unnest_array_batch_enable_is_recognized(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql",
            "CREATE TABLE erp.propostas (id UUID PRIMARY KEY);\n"
            "CREATE TABLE erp.contratos (id UUID PRIMARY KEY);\n"
            "\n"
            "DO $$\n"
            "DECLARE\n"
            "  tbl text;\n"
            "BEGIN\n"
            "  FOR tbl IN SELECT unnest(ARRAY[\n"
            "    'propostas','contratos'\n"
            "  ])\n"
            "  LOOP\n"
            "    EXECUTE format('ALTER TABLE erp.%I ENABLE ROW LEVEL SECURITY', tbl);\n"
            "    EXECUTE format(\n"
            "      'CREATE POLICY %I ON erp.%I FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> ''org_id'')::uuid)',\n"
            "      tbl || '_select_policy', tbl);\n"
            "  END LOOP;\n"
            "END $$;\n",
        )

        assert check_table_has_rls(repo_root=root) == []


class TestUnrelatedDoBlockDoesNotSuppressFindings:
    def test_do_block_naming_a_different_table_does_not_clear_an_unrelated_one(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "CREATE TABLE demo.protected (id UUID PRIMARY KEY);\n"
            "CREATE TABLE demo.unprotected (id UUID PRIMARY KEY);\n"
            "\n"
            "DO $$\n"
            "DECLARE t TEXT;\n"
            "BEGIN\n"
            "    FOREACH t IN ARRAY ARRAY['protected'] LOOP\n"
            "        EXECUTE format('ALTER TABLE demo.%I ENABLE ROW LEVEL SECURITY', t);\n"
            "    END LOOP;\n"
            "END $$;\n",
        )

        issues = check_table_has_rls(repo_root=root)

        assert len(issues) == 1
        assert "demo.unprotected" in issues[0]["issue"]


class TestPathsScoping:
    def test_paths_none_scans_whole_tree(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "CREATE TABLE demo.widgets (id UUID PRIMARY KEY);\n",
        )

        assert len(check_table_has_rls(repo_root=root)) == 1

    def test_paths_scoped_ignores_untouched_file(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/001_demo.sql",
            "CREATE TABLE demo.widgets (id UUID PRIMARY KEY);\n",
        )
        _write(
            root,
            "products/demo/backend/migrations/002_unrelated.sql",
            "ALTER TABLE demo.widgets ADD COLUMN foo text;\n",
        )

        issues = check_table_has_rls(
            repo_root=root,
            paths=["products/demo/backend/migrations/002_unrelated.sql"],
        )

        assert issues == []


class TestNoCreateTableIsCheapNoOp:
    def test_file_with_no_create_table_produces_no_findings(self, tmp_path):
        root = _make_products_root(tmp_path)
        _write(
            root,
            "products/demo/backend/migrations/002_alter_only.sql",
            "ALTER TABLE demo.widgets ADD COLUMN foo text;\n",
        )

        assert check_table_has_rls(repo_root=root) == []
