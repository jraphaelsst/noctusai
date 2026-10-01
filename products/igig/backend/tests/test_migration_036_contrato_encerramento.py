"""Migration 036 — contrato encerramento columns (structural)."""
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
PG = (MIGRATIONS / "036_igig_contrato_encerramento.sql").read_text(encoding="utf-8")
LITE = (MIGRATIONS / "sqlite" / "036_contrato_encerramento.sql").read_text(encoding="utf-8")


def test_adds_both_columns_idempotently():
    for coluna, tipo in (("data_encerramento", "DATE"), ("motivo_encerramento", "TEXT")):
        assert f"ADD COLUMN IF NOT EXISTS {coluna} {tipo}" in PG


def test_is_forward_only():
    upper = PG.upper()
    assert "DROP " not in upper and "DELETE " not in upper


def test_status_check_already_allows_encerrado():
    base = (MIGRATIONS / "006_igig_dominio.sql").read_text(encoding="utf-8")
    assert "'encerrado'" in base


def test_sqlite_mirror_has_same_columns():
    assert "ADD COLUMN data_encerramento TEXT" in LITE
    assert "ADD COLUMN motivo_encerramento TEXT" in LITE
