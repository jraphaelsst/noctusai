"""Structural tests for `177_contrato_revisao_juridica.sql`.

Parse-based, like the sibling contract migrations (120/134/157) — the
migration is a FILE, not an applied change. These pin: the version-level
review columns (the list defaults to '[]' so every existing row reads "no
review needed", both CHECKs), the ledger's `revisao_versao_id` FK, and that
the file is forward-only/idempotent and reloads PostgREST.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "177_contrato_revisao_juridica.sql"


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
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE", "UPDATE SOCIAL"):
        assert forbidden not in upper


def test_the_list_defaults_to_empty_so_existing_versions_need_no_review(flat: str):
    assert (
        "ALTER TABLE social_wiring.atendimento_contrato_versoes "
        "ADD COLUMN IF NOT EXISTS revisao_juridica_campos JSONB NOT NULL DEFAULT '[]'::jsonb;"
    ) in flat
    assert "CHECK (jsonb_typeof(revisao_juridica_campos) = 'array')" in flat


def test_reviewer_stamps_are_nullable_and_paired(flat: str):
    assert "ADD COLUMN IF NOT EXISTS revisado_por UUID;" in flat
    assert "ADD COLUMN IF NOT EXISTS revisado_em TIMESTAMPTZ;" in flat
    assert "CHECK (revisado_por IS NULL OR revisado_em IS NOT NULL)" in flat


def test_constraints_are_existence_guarded(flat: str):
    assert flat.count("IF NOT EXISTS ( SELECT 1 FROM pg_constraint") == 2


def test_ledger_rows_point_at_the_reviewed_version(flat: str):
    assert (
        "ALTER TABLE social_wiring.extracao_validacoes ADD COLUMN IF NOT EXISTS revisao_versao_id UUID "
        "REFERENCES social_wiring.atendimento_contrato_versoes(id) ON DELETE SET NULL;"
    ) in flat


def test_reloads_postgrest(flat: str):
    assert flat.rstrip().endswith("NOTIFY pgrst, 'reload schema';")
