"""Structural tests for `013_agent_studio_knowledge_evals.sql` —
parse-based, no database needed. Mirrors the style of
`tests/stores/test_migration_006_shape.py`."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "migrations" / "013_agent_studio_knowledge_evals.sql"
)

TABLES = (
    "knowledge_collections",
    "knowledge_documents",
    "knowledge_revisions",
    "eval_cases",
    "eval_runs",
    "eval_results",
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _table_block(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE agents.{table} (")
    return sql[start : sql.index(");", start)]


class TestRls:
    @pytest.mark.parametrize("table", TABLES)
    def test_rls_is_enabled(self, sql, table):
        assert f"ALTER TABLE agents.{table} ENABLE ROW LEVEL SECURITY" in sql

    @pytest.mark.parametrize("table", TABLES)
    def test_the_select_policy_is_org_scoped_via_current_org_id(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "{table}_select_own_org"\s+ON agents\.{table}\s+'
            rf"FOR SELECT TO authenticated\s+USING \(org_id = current_org_id\(\)\)",
            sql,
        ), f"{table} is missing the org-scoped SELECT policy"

    @pytest.mark.parametrize("table", TABLES)
    def test_the_bypass_policy_uses_the_literal_keeper_name(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "service_role_bypass" ON agents\.{table}\s+'
            rf"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)",
            sql,
        ), f"{table} must name its bypass policy literally `service_role_bypass`"


class TestUpdatedAtTriggers:
    @pytest.mark.parametrize("table", TABLES)
    def test_every_table_has_an_updated_at_trigger(self, sql, table):
        assert re.search(
            rf"CREATE OR REPLACE TRIGGER set_updated_at_{table}\s+"
            rf"BEFORE UPDATE ON agents\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION agents\.set_updated_at\(\)",
            sql,
        ), f"{table} is missing its updated_at trigger"


class TestCommonColumns:
    @pytest.mark.parametrize("table", TABLES)
    def test_every_table_has_the_common_columns(self, sql, table):
        block = _table_block(sql, table)
        assert re.search(r"id\s+UUID PRIMARY KEY DEFAULT gen_random_uuid\(\)", block)
        assert re.search(r"org_id\s+UUID NOT NULL", block)
        assert re.search(r"created_at\s+TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)
        assert re.search(r"updated_at\s+TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)


class TestUniqueSlugsPerAgent:
    @pytest.mark.parametrize("table", ("knowledge_collections", "knowledge_documents", "eval_cases"))
    def test_slug_is_unique_per_agent(self, sql, table):
        block = _table_block(sql, table)
        assert "UNIQUE (agent_id, slug)" in block


class TestKnowledgeDocumentsSearch:
    def test_busca_tsvector_is_generated_and_weighted(self, sql):
        block = _table_block(sql, "knowledge_documents")
        assert "busca tsvector GENERATED ALWAYS AS" in block
        assert "'A'" in block and "'B'" in block and "'C'" in block
        assert "STORED" in block

    def test_gin_index_on_busca(self, sql):
        assert "CREATE INDEX idx_agents_knowledge_documents_busca ON agents.knowledge_documents USING GIN (busca)" in sql

    def test_pg_trgm_extension_and_titulo_index(self, sql):
        assert "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;" in sql
        assert (
            "CREATE INDEX idx_agents_knowledge_documents_titulo_trgm\n"
            "    ON agents.knowledge_documents USING GIN (titulo extensions.gin_trgm_ops);"
            in sql
        )

    def test_source_sha_column_exists(self, sql):
        block = _table_block(sql, "knowledge_documents")
        assert "source_sha TEXT NOT NULL" in block


class TestEvalCasesCriteriosCheck:
    def test_at_least_one_criterion_required(self, sql):
        block = _table_block(sql, "eval_cases")
        assert "jsonb_array_length(criterios -> 'deve')" in block
        assert "jsonb_array_length(criterios -> 'nao_deve')" in block
        assert ">= 1" in block


class TestEvalRunsOneActivePerVersion:
    def test_partial_unique_index_exists(self, sql):
        assert re.search(
            r"CREATE UNIQUE INDEX eval_runs_one_active_per_version_idx\s+"
            r"ON agents\.eval_runs \(version_id\) WHERE status IN \('pendente', 'executando'\)",
            sql,
        )

    def test_status_check(self, sql):
        block = _table_block(sql, "eval_runs")
        assert (
            "CHECK (status IN ('pendente', 'executando', 'concluida', 'falhou', 'cancelada'))"
            in block
        )


class TestEvalResults:
    def test_unique_per_run_and_case(self, sql):
        block = _table_block(sql, "eval_results")
        assert "UNIQUE (run_id, case_id)" in block

    def test_status_check(self, sql):
        block = _table_block(sql, "eval_results")
        assert "CHECK (status IN ('pendente', 'aprovado', 'reprovado', 'erro'))" in block


class TestAgentVersionsEvalRunFk:
    def test_fk_added(self, sql):
        assert (
            "ALTER TABLE agents.agent_versions\n"
            "    ADD CONSTRAINT agent_versions_eval_run_fk FOREIGN KEY (eval_run_id) REFERENCES agents.eval_runs(id);"
            in sql
        )


class TestSecurityDefinerExecuteGrants:
    """Every SECURITY DEFINER function in 013 must lock EXECUTE down to
    service_role only — same generic walker as
    `tests/stores/test_migration_006_shape.py`."""

    @staticmethod
    def _security_definer_function_names(sql: str) -> list[str]:
        names: list[str] = []
        for match in re.finditer(r"CREATE OR REPLACE FUNCTION\s+(agents\.\w+)\s*\(", sql):
            name = match.group(1)
            body_start = match.end()
            next_fn = sql.find("CREATE OR REPLACE FUNCTION", body_start)
            body_end = next_fn if next_fn != -1 else len(sql)
            body = sql[body_start:body_end]
            if "SECURITY DEFINER" in body:
                names.append(name)
        return names

    def test_at_least_one_security_definer_function_exists(self, sql):
        assert self._security_definer_function_names(sql), (
            "expected at least one SECURITY DEFINER function in 013 (search_knowledge)"
        )

    def test_every_security_definer_function_revokes_from_public_anon_authenticated(self, sql):
        for fname in self._security_definer_function_names(sql):
            match = re.search(
                rf"REVOKE ALL ON FUNCTION {re.escape(fname)}\([^)]*\)\s+FROM([^;]*);",
                sql,
            )
            assert match, f"{fname} is SECURITY DEFINER but has no matching REVOKE statement"
            revoked_from = match.group(1).upper()
            for required_role in ("PUBLIC", "ANON", "AUTHENTICATED"):
                assert required_role in revoked_from, (
                    f"{fname}'s REVOKE must name {required_role} — got: FROM{match.group(1)}"
                )

    def test_every_security_definer_function_grants_execute_to_service_role_only(self, sql):
        for fname in self._security_definer_function_names(sql):
            match = re.search(
                rf"GRANT EXECUTE ON FUNCTION {re.escape(fname)}\([^)]*\)\s+TO([^;]*);",
                sql,
            )
            assert match, f"{fname} is SECURITY DEFINER but has no matching GRANT statement"
            granted_to = [role.strip() for role in match.group(1).split(",")]
            assert granted_to == ["service_role"], (
                f"{fname}'s GRANT must name ONLY service_role — got {granted_to}"
            )


class TestSearchKnowledgeFunction:
    def test_returns_the_ranked_shape(self, sql):
        assert "CREATE OR REPLACE FUNCTION agents.search_knowledge(" in sql
        assert "RETURNS TABLE" in sql
        assert "trecho" in sql and "rank" in sql

    def test_uses_ts_headline_and_websearch_to_tsquery(self, sql):
        assert "ts_headline(" in sql
        assert "websearch_to_tsquery('portuguese', p_query)" in sql

    def test_org_and_agent_scoped(self, sql):
        fn_start = sql.index("CREATE OR REPLACE FUNCTION agents.search_knowledge(")
        fn_body = sql[fn_start:]
        assert "d.org_id = p_org_id" in fn_body
        assert "d.agent_id = p_agent_id" in fn_body
