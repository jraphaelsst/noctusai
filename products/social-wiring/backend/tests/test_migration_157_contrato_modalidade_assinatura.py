"""Structural tests for `157_contrato_modalidade_assinatura.sql`.

Parse-based, like the sibling contract migrations (106/120/134) — the
migration is a FILE, not an applied change. These pin: the contract-level
`modalidade_assinatura` column is NOT NULL, defaults to 'digital' (so every
existing contract keeps its behaviour) and is CHECK-pinned to
('digital','fisica'); the version-level column is nullable with the same
vocabulary; the file is forward-only/idempotent and reloads PostgREST.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "157_contrato_modalidade_assinatura.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(flat: str):
    upper = flat.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE", "UPDATE "):
        assert forbidden not in upper


def test_contract_column_defaults_to_digital_and_is_pinned(flat: str):
    assert (
        "ALTER TABLE social_wiring.atendimento_contratos "
        "ADD COLUMN IF NOT EXISTS modalidade_assinatura TEXT NOT NULL DEFAULT 'digital' "
        "CHECK (modalidade_assinatura IN ('digital', 'fisica'));"
    ) in flat


def test_version_column_is_nullable_with_the_same_vocabulary(flat: str):
    assert (
        "ALTER TABLE social_wiring.atendimento_contrato_versoes "
        "ADD COLUMN IF NOT EXISTS modalidade_assinatura TEXT "
        "CHECK (modalidade_assinatura IS NULL OR modalidade_assinatura IN ('digital', 'fisica'));"
    ) in flat


def test_reloads_the_postgrest_schema_cache(flat: str):
    assert flat.rstrip().endswith("NOTIFY pgrst, 'reload schema';")
