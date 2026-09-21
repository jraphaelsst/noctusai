"""Structural tests for ``012_agent_studio_definitions.sql`` (contract §B1).

Parse-based, no database — same style as ``tests/stores/test_migration_006_shape.py``.
The statement-level parse uses ``pglast`` (the real Postgres parser), so a
syntax error in the migration fails here, not at deploy.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parents[3] / "migrations" / "012_agent_studio_definitions.sql"

NEW_TABLES = (
    "agent_versions",
    "agent_prompt_sections",
    "agent_skills",
    "agent_skill_files",
    "agent_clients",
    "agent_client_entries",
    "compiled_prompts",
)
VERSION_FUNCTIONS = ("create_agent_draft", "publish_agent_version", "discard_agent_draft")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _table_block(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE agents.{table} (")
    return sql[start : sql.index(");", start)]


def _function_block(sql: str, name: str) -> str:
    start = sql.index(f"CREATE OR REPLACE FUNCTION agents.{name}(")
    return sql[start : sql.index("$$;", start)]


class TestParses:
    def test_every_statement_parses_with_the_postgres_parser(self, sql):
        pglast = pytest.importorskip("pglast")
        assert len(pglast.parse_sql(sql)) > 50

    def test_every_plpgsql_body_parses(self, sql):
        parser = pytest.importorskip("pglast.parser")
        # pglast's PL/pgSQL parser cannot resolve a `schema.table` %ROWTYPE
        # outside pg_catalog/public; RECORD is equivalent for a syntax check.
        body = re.sub(r"(v_\w+) agents\.agent_versions;", r"\1 RECORD;", sql)
        fns = re.findall(r"CREATE OR REPLACE FUNCTION.*?\$\$;", body, re.S)
        assert len(fns) == 7
        for fn in fns:
            parser.parse_plpgsql_json(fn)


class TestStudioColumnsOnAgents:
    def test_definition_mode_defaults_legacy(self, sql):
        assert re.search(
            r"ADD COLUMN definition_mode TEXT NOT NULL DEFAULT 'legacy'\s+"
            r"CHECK \(definition_mode IN \('legacy', 'studio'\)\)",
            sql,
        )

    def test_descricao_and_limiar(self, sql):
        assert "ADD COLUMN descricao TEXT NULL" in sql
        assert re.search(
            r"ADD COLUMN publicacao_limiar NUMERIC\(4,3\) NOT NULL DEFAULT 0\.800\s+"
            r"CHECK \(publicacao_limiar >= 0 AND publicacao_limiar <= 1\)",
            sql,
        )

    def test_proof_of_use_columns(self, sql):
        assert re.search(
            r"ALTER TABLE agents\.conversations\s+ADD COLUMN version_id UUID NULL REFERENCES agents\.agent_versions\(id\),\s+"
            r"ADD COLUMN client_id UUID NULL REFERENCES agents\.agent_clients\(id\);",
            sql,
        )
        assert re.search(
            r"ALTER TABLE agents\.messages\s+ADD COLUMN version_id UUID NULL REFERENCES agents\.agent_versions\(id\),\s+"
            r"ADD COLUMN compiled_hash TEXT NULL;",
            sql,
        )


class TestConventions:
    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_common_columns(self, sql, table):
        block = _table_block(sql, table)
        assert re.search(r"id UUID PRIMARY KEY DEFAULT gen_random_uuid\(\)", block)
        assert re.search(r"org_id UUID NOT NULL", block)
        assert re.search(r"created_at TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)
        assert re.search(r"updated_at TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_rls_enabled(self, sql, table):
        assert f"ALTER TABLE agents.{table} ENABLE ROW LEVEL SECURITY" in sql

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_org_scoped_select_policy(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "{table}_select_own_org" ON agents\.{table}\s+'
            rf"FOR SELECT TO authenticated\s+USING \(org_id = current_org_id\(\)\)",
            sql,
        )

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_literal_service_role_bypass(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "service_role_bypass" ON agents\.{table}\s+'
            rf"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)",
            sql,
        )

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_org_index(self, sql, table):
        assert f"CREATE INDEX idx_agents_{table}_org ON agents.{table}(org_id);" in sql

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_updated_at_trigger(self, sql, table):
        assert re.search(
            rf"CREATE OR REPLACE TRIGGER set_updated_at_{table}\s+BEFORE UPDATE ON agents\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION agents\.set_updated_at\(\)",
            sql,
        )

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_anon_lockdown_restated(self, sql, table):
        """011 revoked anon from the schema default privileges; each new
        table restates it explicitly."""
        assert f"REVOKE ALL ON agents.{table} FROM anon;" in sql

    def test_no_new_grant_to_anon(self, sql):
        code = re.sub(r"--[^\n]*", "", sql)
        grants = re.findall(r"^\s*GRANT\b[^;]*;", code, re.M)
        assert grants, "expected the service_role GRANT statements"
        assert not [g for g in grants if re.search(r"\banon\b|\bauthenticated\b|\bPUBLIC\b", g)]


class TestPageVisibility:
    def test_studio_nav_page_is_seeded_in_development(self, sql):
        """Without a status_pagina row the `/studio` nav entry is hidden from
        everyone (KB § PATTERNS/frontend/status-pagina-dev-visibility.md)."""
        assert re.search(
            r"INSERT INTO agents\.status_pagina \(nome_pagina, status\) VALUES\s+"
            r"\('studio', 'desenvolvimento'\)\s+ON CONFLICT \(nome_pagina\) DO NOTHING;",
            sql,
        )


class TestVersionInvariants:
    def test_partial_uniques(self, sql):
        assert re.search(
            r"CREATE UNIQUE INDEX agent_versions_one_ativa_idx\s+ON agents\.agent_versions \(agent_id\) WHERE status = 'ativa'",
            sql,
        )
        assert re.search(
            r"CREATE UNIQUE INDEX agent_versions_one_rascunho_idx\s+ON agents\.agent_versions \(agent_id\) WHERE status = 'rascunho'",
            sql,
        )

    def test_checks(self, sql):
        block = _table_block(sql, "agent_versions")
        assert "CHECK (status IN ('rascunho', 'ativa', 'substituida'))" in block
        assert "CHECK (model IN ('claude-opus-5', 'claude-sonnet-5'))" in block
        assert "CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max'))" in block
        assert "CHECK (max_turns BETWEEN 1 AND 200)" in block
        assert "UNIQUE (agent_id, versao)" in block
        assert "UNIQUE (org_id, hash)" in _table_block(sql, "compiled_prompts")
        assert "UNIQUE (version_id, chave)" in _table_block(sql, "agent_prompt_sections")
        assert "UNIQUE (version_id, nome)" in _table_block(sql, "agent_skills")
        assert "UNIQUE (skill_id, caminho)" in _table_block(sql, "agent_skill_files")
        assert "UNIQUE (agent_id, slug)" in _table_block(sql, "agent_clients")

    def test_children_cascade_from_their_version(self, sql):
        for table in ("agent_prompt_sections", "agent_skills"):
            assert "REFERENCES agents.agent_versions(id) ON DELETE CASCADE" in _table_block(sql, table)
        assert "REFERENCES agents.agent_skills(id) ON DELETE CASCADE" in _table_block(sql, "agent_skill_files")


class TestImmutabilityTriggers:
    @pytest.mark.parametrize(
        "trigger, table, events, fn",
        [
            ("guard_agent_version_immutable", "agent_versions", "BEFORE UPDATE OR DELETE", "guard_agent_version_immutable"),
            ("guard_agent_prompt_sections_immutable", "agent_prompt_sections", "BEFORE INSERT OR UPDATE OR DELETE", "guard_version_child_immutable"),
            ("guard_agent_skills_immutable", "agent_skills", "BEFORE INSERT OR UPDATE OR DELETE", "guard_version_child_immutable"),
            ("guard_agent_skill_files_immutable", "agent_skill_files", "BEFORE INSERT OR UPDATE OR DELETE", "guard_skill_file_immutable"),
            ("guard_compiled_prompts_immutable", "compiled_prompts", "BEFORE UPDATE", "guard_compiled_prompt_immutable"),
        ],
    )
    def test_trigger_present(self, sql, trigger, table, events, fn):
        assert re.search(
            rf"CREATE OR REPLACE TRIGGER {trigger}\s+{events} ON agents\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION agents\.{fn}\(\)",
            sql,
        ), f"missing trigger {trigger} on {table}"

    def test_version_guard_only_allows_ativa_to_substituida(self, sql):
        body = _function_block(sql, "guard_agent_version_immutable")
        assert "OLD.status = 'ativa' AND NEW.status = 'substituida'" in body
        # Every content column is compared on the published path.
        for col in (
            "notas", "model", "effort", "max_turns", "idioma", "tool_policy", "compiled_hash",
            "eval_run_id", "publish_override_reason", "published_at", "published_by",
        ):
            assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in body, col

    def test_guards_raise_the_machine_code(self, sql):
        for fn in ("guard_agent_version_immutable", "guard_version_child_immutable", "guard_skill_file_immutable"):
            assert "RAISE EXCEPTION 'version_immutable'" in _function_block(sql, fn)
        assert "RAISE EXCEPTION 'compiled_prompt_immutable'" in _function_block(sql, "guard_compiled_prompt_immutable")


class TestVersionFunctions:
    def test_signatures(self, sql):
        assert re.search(
            r"FUNCTION agents\.create_agent_draft\(\s*p_org_id UUID,\s*p_agent_id UUID,\s*"
            r"p_source_version_id UUID,\s*p_created_by UUID\s*\) RETURNS UUID",
            sql,
        )
        assert re.search(
            r"FUNCTION agents\.publish_agent_version\(\s*p_org_id UUID,\s*p_version_id UUID,\s*"
            r"p_published_by UUID,\s*p_eval_run_id UUID,\s*p_override_reason TEXT\s*\) RETURNS VOID",
            sql,
        )
        assert re.search(
            r"FUNCTION agents\.discard_agent_draft\(\s*p_org_id UUID,\s*p_version_id UUID\s*\) RETURNS VOID",
            sql,
        )

    def test_create_draft_raises_draft_exists_and_deep_copies(self, sql):
        body = _function_block(sql, "create_agent_draft")
        assert "RAISE EXCEPTION 'draft_exists'" in body
        assert "COALESCE(MAX(versao), 0) + 1" in body
        assert "'claude-opus-5', 'high', 40" in body
        for table in ("agent_prompt_sections", "agent_skills", "agent_skill_files"):
            assert f"INSERT INTO agents.{table}" in body

    def test_publish_flips_ativa_before_setting_the_new_one(self, sql):
        body = _function_block(sql, "publish_agent_version")
        assert "RAISE EXCEPTION 'version_immutable'" in body
        assert body.index("SET status = 'substituida'") < body.index("SET status = 'ativa'")

    @pytest.mark.parametrize("fn", VERSION_FUNCTIONS)
    def test_version_functions_are_security_definer_with_locked_search_path(self, sql, fn):
        body = _function_block(sql, fn)
        assert "SECURITY DEFINER" in body
        assert "SET search_path = agents, public" in body


class TestSecurityDefinerExecuteGrants:
    """Generic walk (as in 006's test): EVERY SECURITY DEFINER function in 012
    has the REVOKE (PUBLIC, anon, authenticated) + GRANT service_role pair."""

    @staticmethod
    def _definer_names(sql: str) -> list[str]:
        names = []
        for m in re.finditer(r"CREATE OR REPLACE FUNCTION\s+(agents\.\w+)\s*\(", sql):
            nxt = sql.find("CREATE OR REPLACE FUNCTION", m.end())
            if "SECURITY DEFINER" in sql[m.end() : nxt if nxt != -1 else len(sql)]:
                names.append(m.group(1))
        return names

    def test_all_seven_functions_are_covered(self, sql):
        names = self._definer_names(sql)
        assert len(names) == 7
        for fn in VERSION_FUNCTIONS:
            assert f"agents.{fn}" in names

    def test_revoke_pairs(self, sql):
        for fname in self._definer_names(sql):
            m = re.search(rf"REVOKE ALL ON FUNCTION {re.escape(fname)}\b[^;]*FROM([^;]*);", sql)
            assert m, f"{fname} lacks its REVOKE"
            for role in ("PUBLIC", "ANON", "AUTHENTICATED"):
                assert role in m.group(1).upper(), f"{fname} REVOKE must name {role}"

    def test_grant_pairs_service_role_only(self, sql):
        for fname in self._definer_names(sql):
            m = re.search(rf"GRANT EXECUTE ON FUNCTION {re.escape(fname)}\b[^;]*TO([^;]*);", sql)
            assert m, f"{fname} lacks its GRANT"
            assert [r.strip() for r in m.group(1).split(",")] == ["service_role"]
