"""Eval-loop config migration (086): three runtime_settings keys with value bounds, append-only platform-tier events, one RPC
that writes the values and the `loop_config_alterada` event in one transaction, service-role only."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.studio.eval_loop_config import ALVO_PADRAO, KEYS, ORCAMENTO_MAX_USD, ORCAMENTO_PADRAO_USD, RODADAS_LIMITE, RODADAS_MAX_PADRAO

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_loop_config")


def test_the_keys_in_the_check_match_the_code_and_the_old_keys_are_kept():
    for key in KEYS.values():
        assert f"'{key}'" in SQL
    for old in ("approval_timeout_seconds", "max_turns", "messages_rate_limit", "numero_fallback_atendimento"):
        assert f"'{old}'" in SQL


def test_value_bounds_backstop_the_api_bounds():
    assert "<= 1)" in SQL and f"<= {int(ORCAMENTO_MAX_USD)})" in SQL and f"<= {RODADAS_LIMITE}" in SQL
    assert "trunc(" in SQL  # rounds are whole numbers


def test_the_code_defaults_are_the_rpc_defaults():
    assert f"{ALVO_PADRAO}" in SQL and "5.00" in SQL and f", {RODADAS_MAX_PADRAO})" in SQL
    assert ORCAMENTO_PADRAO_USD == 5.0


def test_events_are_append_only_platform_tier_and_service_role_only():
    assert "CREATE TABLE IF NOT EXISTS agents.eval_loop_config_eventos" in SQL
    assert "evento IN ('loop_config_alterada')" in SQL
    assert "BEFORE UPDATE OR DELETE ON agents.eval_loop_config_eventos" in SQL
    assert "COMMENT ON TABLE agents.eval_loop_config_eventos IS 'tier:platform'" in SQL
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON agents.eval_loop_config_eventos FROM anon, authenticated" in SQL
    assert "TO authenticated" not in SQL and "TO anon" not in SQL


def test_the_rpc_writes_values_and_event_together_and_is_not_callable_by_the_browser():
    body = SQL[SQL.index("CREATE OR REPLACE FUNCTION agents.set_eval_loop_config"):]
    assert "SECURITY DEFINER" in body and "SET search_path = agents, public" in body
    assert "INSERT INTO agents.runtime_settings" in body and "INSERT INTO agents.eval_loop_config_eventos" in body
    assert "REVOKE ALL ON FUNCTION agents.set_eval_loop_config(NUMERIC, NUMERIC, INT, UUID) FROM PUBLIC, anon, authenticated" in body
    assert "TO service_role" in body


def test_forward_only_and_idempotent():
    assert "DROP TABLE" not in SQL and "DROP COLUMN" not in SQL
    assert "IF NOT EXISTS" in SQL and "CREATE OR REPLACE FUNCTION" in SQL and "DROP TRIGGER IF EXISTS" in SQL
