"""Structural tests for `*_termos_clausulas_extras.sql` — parse-based like
`test_migration_114_termos_negocio.py` (the migration is a FILE; nothing here
applies it). Pins what the service and the generator rely on: both columns
exist with the declared shape, the object/positive CHECKs are named exactly as
the db-guard probes (`verify_db_guards._SW_207_PROBES`) expect (the probes
themselves are covered by mcp/noctusai/tests/test_verify_db_guards.py), the migration
is idempotent, and nothing is dropped."""
from __future__ import annotations

import re
from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest

from app.modules.card_hub.negociacao_estruturada_service import TERMOS_CAMPOS

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "termos_clausulas_extras")


@pytest.fixture(scope="module")
def flat() -> str:
    code = "\n".join(l for l in MIGRATION.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_both_service_clauses_are_columns_with_the_declared_shape(flat):
    assert {"clausulas_extras", "posse_multa_diaria"} <= set(TERMOS_CAMPOS)
    assert "ADD COLUMN IF NOT EXISTS clausulas_extras JSONB NOT NULL DEFAULT '{}'::jsonb" in flat
    assert re.search(r"ADD COLUMN IF NOT EXISTS posse_multa_diaria NUMERIC(?!\s+NOT NULL)", flat)


def test_checks_are_named_for_the_probes_and_are_rerunnable(flat):
    for nome, predicado in (
        ("atendimento_negociacao_termos_clausulas_extras_objeto", "jsonb_typeof(clausulas_extras) = 'object'"),
        ("atendimento_negociacao_termos_posse_multa_diaria_positiva", "posse_multa_diaria IS NULL OR posse_multa_diaria > 0"),
    ):
        assert f"DROP CONSTRAINT IF EXISTS {nome}" in flat
        assert f"ADD CONSTRAINT {nome} CHECK ({predicado})" in flat


def test_nothing_is_dropped_but_its_own_constraints(flat):
    assert "DROP TABLE" not in flat and "DROP COLUMN" not in flat
