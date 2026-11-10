"""Eval-loop gate migration (076): Platform-IP tables (service-role only, tier-tagged), one active loop per (agent, suite),
the stop reason constraint, the round uniqueness, and the nullable loop_id on BOTH run tables."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.studio.eval_loop import MOTIVOS_PARADA

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_loops")
TABELAS = ("eval_loops", "eval_loop_rodadas")


def test_every_new_table_is_service_role_only_and_tier_tagged():
    for t in TABELAS:
        assert f"CREATE TABLE IF NOT EXISTS agents.{t}" in SQL
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in SQL
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated" in SQL
        assert f'CREATE POLICY "service_role_bypass" ON agents.{t} FOR ALL TO service_role USING (true) WITH CHECK (true)' in SQL
        assert f"COMMENT ON TABLE agents.{t} IS 'tier:platform'" in SQL
    assert all(t.startswith("eval_") for t in TABELAS)  # `agents.eval_*` is declared Platform-IP by the access-tier registry
    assert "TO authenticated" not in SQL and "TO anon" not in SQL


def test_one_active_loop_per_agent_and_suite_and_one_round_per_seq_and_run():
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_eval_loops_ativo_por_suite" in SQL
    assert "ON agents.eval_loops (agent_id, suite) WHERE status = 'ativo'" in SQL
    assert "UNIQUE (loop_id, seq)" in SQL and "UNIQUE (run_id, run_tipo)" in SQL


def test_the_stop_reasons_in_the_check_match_the_code_and_an_active_loop_has_none():
    body = SQL[SQL.index("motivo_parada TEXT NULL CHECK"):SQL.index("detalhe_parada JSONB")]
    assert {m for m in MOTIVOS_PARADA} == {t.strip().strip("'") for t in body.split("IN (")[1].split(")")[0].replace("\n", "").split(",")}
    assert "status = 'ativo' AND motivo_parada IS NULL AND stopped_at IS NULL" in SQL


def test_both_run_tables_carry_a_nullable_loop_id_so_loopless_runs_are_unchanged():
    assert "ALTER TABLE agents.eval_runs\n    ADD COLUMN IF NOT EXISTS loop_id UUID NULL" in SQL
    assert "ALTER TABLE agents.eval_mecanismo_runs\n    ADD COLUMN IF NOT EXISTS loop_id UUID NULL" in SQL
    assert SQL.count("ON DELETE SET NULL") == 2


def test_forward_only_and_idempotent():
    assert "DROP TABLE" not in SQL and "DROP COLUMN" not in SQL
    assert SQL.count("CREATE TABLE IF NOT EXISTS") == 2 and "ADD COLUMN IF NOT EXISTS" in SQL
    assert "DROP POLICY IF EXISTS" in SQL and "DROP TRIGGER IF EXISTS" in SQL
