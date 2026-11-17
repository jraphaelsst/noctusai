"""Migration 088: the new run / round statuses, the `erro` stop reason, the driver mode and the append-only loop events."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.studio_evals import RUN_STATUSES
from app.studio.eval_loop import MOTIVOS_PARADA

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_erro_e_loop_driver")


def _lista(trecho: str) -> set[str]:
    return {t.strip().strip("'") for t in trecho.split("IN (")[1].split(")")[0].replace("\n", "").split(",")}


def test_the_run_status_check_matches_the_code_and_a_run_can_be_erro_or_partial():
    corpo = SQL[SQL.index("ADD CONSTRAINT eval_runs_status_check"):SQL.index("ALTER TABLE agents.eval_loop_rodadas DROP CONSTRAINT")]
    assert _lista(corpo) == set(RUN_STATUSES) and {"erro", "parcial_com_erros"} <= set(RUN_STATUSES)


def test_the_round_status_check_accepts_the_error_statuses():
    corpo = SQL[SQL.index("ADD CONSTRAINT eval_loop_rodadas_status_check"):SQL.index("ALTER TABLE agents.eval_runs ADD COLUMN IF NOT EXISTS erro_codigo")]
    assert {"erro", "parcial_com_erros"} <= _lista(corpo)


def test_the_stop_reasons_in_the_widened_check_are_exactly_the_codes():
    corpo = SQL[SQL.index("ADD CONSTRAINT eval_loops_motivo_parada_check"):SQL.index("ADD COLUMN IF NOT EXISTS modo")]
    assert _lista(corpo) == set(MOTIVOS_PARADA)


def test_the_loop_carries_the_driver_mode_and_the_idle_notice_with_a_safe_default():
    assert "ADD COLUMN IF NOT EXISTS modo TEXT NOT NULL DEFAULT 'manual'" in SQL
    assert "ADD COLUMN IF NOT EXISTS aviso JSONB NULL" in SQL


def test_the_events_table_is_platform_only_and_append_only():
    assert "CREATE TABLE IF NOT EXISTS agents.eval_loop_eventos" in SQL
    assert "COMMENT ON TABLE agents.eval_loop_eventos IS 'tier:platform'" in SQL
    assert "REVOKE ALL ON agents.eval_loop_eventos FROM anon, authenticated" in SQL
    assert "BEFORE UPDATE OR DELETE ON agents.eval_loop_eventos" in SQL and "TO authenticated" not in SQL
