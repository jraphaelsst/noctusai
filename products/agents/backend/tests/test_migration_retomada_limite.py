"""Follow-up cap migration (080): an append-only event table (service-role only, tier-tagged), a closed outcome enum, the
bounded `max_retomadas_seguidas` column and the clone RPC that copies it. Forward-only and idempotent."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.threads import RETOMADA_RESULTADOS

SQL = migration_sql(Path(__file__).resolve().parents[1], "retomada_limite")


def test_the_event_table_is_service_role_only_tier_tagged_and_append_only():
    assert "CREATE TABLE IF NOT EXISTS agents.thread_retomada_eventos" in SQL
    assert "ALTER TABLE agents.thread_retomada_eventos ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON agents.thread_retomada_eventos FROM anon, authenticated" in SQL
    assert "COMMENT ON TABLE agents.thread_retomada_eventos IS 'tier:org'" in SQL
    assert "TO authenticated" not in SQL and "TO anon" not in SQL
    assert "BEFORE UPDATE ON agents.thread_retomada_eventos" in SQL and "is append-only" in SQL


def test_the_outcomes_in_the_check_match_the_code():
    body = SQL[SQL.index("resultado TEXT NOT NULL CHECK"):SQL.index("created_at TIMESTAMPTZ")]
    assert {t.strip().strip("'") for t in body.split("IN (")[1].split(")")[0].split(",")} == set(RETOMADA_RESULTADOS)


def test_the_cap_is_a_bounded_column_with_default_two_and_the_clone_rpc_copies_it():
    assert "ADD COLUMN IF NOT EXISTS max_retomadas_seguidas INT NOT NULL DEFAULT 2" in SQL
    assert "BETWEEN 0 AND 10" in SQL
    assert SQL.count("max_retomadas_seguidas") >= 5 and "criar_rascunho_qualificacao" in SQL
    assert "pedir_identificacao_quando, max_retomadas_seguidas" in SQL
    assert "REVOKE ALL ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated" in SQL


def test_forward_only_and_idempotent():
    assert "DROP TABLE" not in SQL and "DROP COLUMN" not in SQL
    assert "DROP POLICY IF EXISTS" in SQL and "DROP TRIGGER IF EXISTS" in SQL and "CREATE OR REPLACE FUNCTION" in SQL
