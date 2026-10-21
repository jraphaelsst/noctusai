"""Data-only migration backfill: a lead's corretor becomes the member of
its open, unstaffed card. Static guards on the SQL (behaviour of the same rule
is exercised by `TestCorretorViraMembroDoCard` against the sweep)."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "backfill_corretor_do_lead_como_membro")


def test_is_data_only():
    upper = SQL.upper()
    for ddl in ("CREATE TABLE", "ALTER TABLE", "DROP ", "CREATE POLICY", "CREATE FUNCTION"):
        assert ddl not in upper


def test_only_touches_open_unstaffed_cards_and_is_idempotent():
    assert "INSERT INTO social_wiring.cliente_membros" in SQL
    assert "NOT EXISTS" in SQL
    assert "a.closed_at IS NULL" in SQL
    assert "COALESCE(a.arquivado, false) = false" in SQL
    assert "ON CONFLICT (cliente_id, lead_corretor_id) DO NOTHING" in SQL
