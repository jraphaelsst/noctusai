"""Turn metrics migration (066): service-role only, one row per turn, no FK that could block a delete, eval-taggable."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "turn_metrics")


def test_service_role_only():
    assert "ALTER TABLE agents.turn_metrics ENABLE ROW LEVEL SECURITY" in SQL
    assert "REVOKE ALL ON agents.turn_metrics FROM anon, authenticated" in SQL
    assert "TO service_role USING (true) WITH CHECK (true)" in SQL


def test_no_foreign_key_and_origem_check():
    body = SQL[SQL.index("CREATE TABLE IF NOT EXISTS agents.turn_metrics"):]
    body = body[: body.index(");")]
    assert "REFERENCES" not in body
    assert "origem IN ('canal', 'eval')" in body and "status IN ('ok', 'erro')" in body
    assert "media_bytes         INTEGER NULL" in body  # NULL = not measured
