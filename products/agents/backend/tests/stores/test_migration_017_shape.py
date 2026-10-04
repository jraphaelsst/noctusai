"""Structural tests for `017_agent_packages.sql` — parse-based, no database
needed (style of `test_migration_015_shape.py`)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION_PATH = MIGRATIONS / "017_agent_packages.sql"
NEW_TABLES = ("agent_package_trees", "agent_project_sources", "agent_learnings")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _table(sql: str, name: str) -> str:
    start = sql.index(f"CREATE TABLE agents.{name} (")
    return sql[start : sql.index("\n);", start)]


class TestNumbering:
    def test_017_follows_016_with_no_gap_or_duplicate(self):
        numbers = sorted(int(p.name.split("_", 1)[0]) for p in MIGRATIONS.glob("*.sql"))
        assert numbers == list(range(1, len(numbers) + 1))
        assert 17 in numbers


class TestAgentsKind:
    def test_kind_defaults_to_runtime_so_existing_rows_stay_valid(self, sql):
        assert "ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'runtime'" in sql

    def test_kind_check_allowlist(self, sql):
        assert "CHECK (kind IN ('runtime', 'dev-advisor'))" in sql

    def test_kind_is_immutable_by_trigger(self, sql):
        assert "RAISE EXCEPTION 'kind_immutable'" in sql
        assert re.search(r"CREATE OR REPLACE TRIGGER guard_agent_kind_immutable\s+BEFORE UPDATE ON agents\.agents", sql)


class TestVersionColumns:
    def test_semver_and_sha_are_nullable_and_checked(self, sql):
        assert "ADD COLUMN IF NOT EXISTS versao_semver TEXT NULL" in sql
        assert "ADD COLUMN IF NOT EXISTS package_sha TEXT NULL" in sql
        assert "versao_semver IS NULL" in sql and "package_sha IS NULL OR package_sha ~ '^[0-9a-f]{64}$'" in sql

    def test_a_published_semver_is_unique_per_agent(self, sql):
        assert re.search(
            r"CREATE UNIQUE INDEX IF NOT EXISTS agent_versions_published_semver_idx\s+"
            r"ON agents\.agent_versions \(agent_id, versao_semver\)\s+"
            r"WHERE versao_semver IS NOT NULL AND status <> 'rascunho'", sql)

    def test_the_012_guard_is_redeclared_with_every_original_frozen_column_plus_the_two_new_ones(self, sql):
        def body(text: str) -> str:
            start = text.index("CREATE OR REPLACE FUNCTION agents.guard_agent_version_immutable()")
            return text[start : text.index("\n$$;", start)]

        def frozen(text: str) -> set[str]:
            published = text[text.index("-- Published row") :]
            return set(re.findall(r"NEW\.(\w+) IS DISTINCT FROM OLD\.\1", published))

        old = (MIGRATIONS / "012_agent_studio_definitions.sql").read_text(encoding="utf-8")
        assert frozen(body(sql)) == frozen(body(old)) | {"versao_semver", "package_sha"}


@pytest.mark.parametrize("name", NEW_TABLES)
class TestEveryNewTable:
    def test_rls_org_scoped_select_and_the_literal_service_role_bypass(self, sql, name):
        assert f"ALTER TABLE agents.{name} ENABLE ROW LEVEL SECURITY" in sql
        assert re.search(
            rf'CREATE POLICY "{name}_select_own_org" ON agents\.{name}\s+FOR SELECT TO authenticated\s+'
            r"USING \(org_id = current_org_id\(\)\)", sql)
        assert re.search(
            rf'CREATE POLICY "service_role_bypass" ON agents\.{name}\s+FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)',
            sql)

    def test_anon_and_authenticated_write_grants_are_revoked(self, sql, name):
        assert f"REVOKE ALL ON agents.{name} FROM anon" in sql
        assert f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.{name} FROM authenticated" in sql

    def test_org_index_and_updated_at_trigger(self, sql, name):
        assert f"idx_agents_{name}_org ON agents.{name}(org_id)" in sql
        assert f"set_updated_at_{name}" in sql
        assert "org_id UUID NOT NULL" in _table(sql, name)

    def test_the_table_has_an_updated_at_column_for_the_trigger(self, sql, name):
        assert "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()" in _table(sql, name)


class TestTrees:
    def test_one_tree_per_version_cascading_with_a_discarded_draft(self, sql):
        t = _table(sql, "agent_package_trees")
        assert "REFERENCES agents.agent_versions(id) ON DELETE CASCADE" in t and "UNIQUE (version_id)" in t

    def test_write_once_once_the_parent_is_published(self, sql):
        assert "CREATE OR REPLACE FUNCTION agents.guard_package_tree_immutable()" in sql
        assert re.search(r"BEFORE INSERT OR UPDATE OR DELETE ON agents\.agent_package_trees", sql)
        assert "RAISE EXCEPTION 'version_immutable'" in sql


class TestSources:
    def test_ledger_key_and_enums(self, sql):
        t = _table(sql, "agent_project_sources")
        assert "UNIQUE (agent_id, project_slug, path)" in t
        assert "tipo IN ('doc', 'codigo', 'quadro')" in t
        assert "ON DELETE SET NULL" in t  # a deleted document must not erase the ledger


class TestLearnings:
    def test_row_identity_unique_per_agent(self, sql):
        assert "UNIQUE (agent_id, row_sha)" in _table(sql, "agent_learnings")

    def test_review_states(self, sql):
        assert "status IN ('novo', 'aceito', 'descartado', 'promovido')" in _table(sql, "agent_learnings")

    def test_content_columns_are_write_once(self, sql):
        assert "RAISE EXCEPTION 'learning_content_immutable'" in sql
        guard = sql[sql.index("FUNCTION agents.guard_agent_learning_content()"):]
        for col in ("row_sha", "data", "tipo", "texto", "evidencia", "project_slug"):
            assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in guard
        for review_col in ("status", "review_note", "reviewed_by", "reviewed_at"):
            assert f"NEW.{review_col} IS DISTINCT FROM" not in guard


class TestSecurityDefiner:
    def test_every_security_definer_function_is_locked_to_service_role(self, sql):
        fns = re.findall(r"CREATE OR REPLACE FUNCTION (agents\.\w+)\(\)", sql)
        assert len(fns) == 4
        for fn in fns:
            assert f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC, anon, authenticated" in sql
            assert f"GRANT EXECUTE ON FUNCTION {fn}() TO service_role" in sql

    def test_api_tokens_scopes_already_exist_so_it_is_not_re_added(self, sql):
        assert re.search(r"scopes\s+TEXT\[\] NOT NULL DEFAULT '\{\}'", (MIGRATIONS / "007_api_tokens.sql").read_text(encoding="utf-8"))
        assert not re.search(r"ALTER TABLE agents\.api_tokens", sql)
