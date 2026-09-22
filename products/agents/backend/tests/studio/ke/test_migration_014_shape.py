"""Structural tests for `014_agent_studio_cost.sql` (contract §L) —
parse-based, no database needed. Mirrors the style of
`test_migration_013_shape.py`."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "migrations" / "014_agent_studio_cost.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestIdempotency:
    def test_every_add_column_is_if_not_exists(self, sql):
        # Every `ADD COLUMN` line in an `ALTER TABLE ... ADD COLUMN` block
        # in this migration must be guarded (013's documented convention).
        add_columns = re.findall(r"ADD COLUMN\s+(?:IF NOT EXISTS\s+)?(\w+)", sql)
        assert add_columns  # sanity: the migration does add columns
        unguarded = re.findall(r"ADD COLUMN(?!\s+IF NOT EXISTS)\s+\w+", sql)
        assert unguarded == [], f"unguarded ADD COLUMN: {unguarded}"

    def test_every_add_constraint_is_preceded_by_a_drop_if_exists(self, sql):
        for name in re.findall(r"ADD CONSTRAINT (\w+)", sql):
            assert f"DROP CONSTRAINT IF EXISTS {name}" in sql, name

    def test_create_eval_run_signature_change_drops_the_old_overload_first(self, sql):
        drop_idx = sql.index(
            "DROP FUNCTION IF EXISTS agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID);"
        )
        create_idx = sql.index("CREATE OR REPLACE FUNCTION agents.create_eval_run(")
        assert drop_idx < create_idx


class TestColumns:
    def test_eval_results_cost_columns(self, sql):
        for col in ("custo_usd", "tokens_entrada", "tokens_saida", "tokens_cache_leitura"):
            assert re.search(rf"ADD COLUMN IF NOT EXISTS {col}\b", sql), col

    def test_eval_runs_cost_columns(self, sql):
        for col in ("modelo_geracao", "limite_usd", "custo_usd"):
            assert re.search(rf"ADD COLUMN IF NOT EXISTS {col}\b", sql), col

    def test_messages_cost_columns(self, sql):
        for col in ("custo_usd", "tokens_entrada", "tokens_saida"):
            assert re.search(rf"ADD COLUMN IF NOT EXISTS {col}\b", sql), col

    def test_eval_results_status_check_gains_pulado(self, sql):
        block = sql[sql.index("ADD CONSTRAINT eval_results_status_check") :]
        block = block[: block.index(";") + 1]
        assert "'pulado'" in block
        for existing in ("pendente", "aprovado", "reprovado", "erro"):
            assert f"'{existing}'" in block

    def test_modelo_geracao_allowlist_is_narrower_than_agent_versions_model(self, sql):
        block = sql[sql.index("ADD CONSTRAINT eval_runs_modelo_geracao_check") :]
        block = block[: block.index(";") + 1]
        assert "'claude-sonnet-5'" in block and "'claude-haiku-4-5'" in block
        assert "'claude-opus-5'" not in block  # deliberately narrower (§L)

    def test_limite_usd_check_bounds(self, sql):
        block = sql[sql.index("ADD CONSTRAINT eval_runs_limite_usd_check") :]
        block = block[: block.index(";") + 1]
        assert "> 0" in block and "<= 50" in block


class TestCreateEvalRunFunction:
    def test_new_params_have_null_defaults(self, sql):
        fn = sql[
            sql.index("CREATE OR REPLACE FUNCTION agents.create_eval_run(") :
            sql.index("$$;", sql.index("CREATE OR REPLACE FUNCTION agents.create_eval_run(")) + 3
        ]
        assert "p_modelo_geracao TEXT DEFAULT NULL" in fn
        assert "p_limite_usd NUMERIC DEFAULT NULL" in fn
        assert "modelo_geracao, limite_usd" in fn
        assert "p_modelo_geracao, p_limite_usd" in fn

    def test_revoke_and_grant_use_the_new_nine_argument_signature(self, sql):
        sig = "(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID, TEXT, NUMERIC)"
        assert f"REVOKE ALL ON FUNCTION agents.create_eval_run{sig} FROM PUBLIC, anon, authenticated;" in sql
        assert f"GRANT EXECUTE ON FUNCTION agents.create_eval_run{sig} TO service_role;" in sql

    def test_plpgsql_body_parses(self, sql):
        parser = pytest.importorskip("pglast.parser")
        for fn in re.findall(r"CREATE OR REPLACE FUNCTION.*?\$\$;", sql, re.S):
            parser.parse_plpgsql_json(fn)


class TestSearchPath:
    def test_search_path_set_at_top(self, sql):
        assert re.search(r"^SET search_path = agents, public;$", sql, re.M)
