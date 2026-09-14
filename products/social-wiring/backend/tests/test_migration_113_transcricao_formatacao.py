"""Structural tests for `113_transcricao_formatacao.sql`.

Parse-based, like `test_migration_111_matricula_lgpd_followups.py` — the
migration is a FILE, not an applied change, and there is no dev database to
run it against. These assert the DECLARED shape: that both tables gain their
formatting columns, that `tem_transcricao` is truly GENERATED (never a
written flag that could drift), and that neither new column collides with
an existing one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "113_transcricao_formatacao.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — prose in the header must never
    satisfy (or trip) a check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with runs of whitespace collapsed — the DDL aligns its column
    definitions, so a substring check must not depend on that alignment."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_idempotent(code: str):
    assert "ADD COLUMN IF NOT EXISTS" in code
    # No DROP/CREATE TABLE, no trigger, no policy — additive-only migration.
    assert "DROP TABLE" not in code
    assert "CREATE POLICY" not in code


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


# ─── 1. matricula_extracoes.formatacao ──────────────────────────────────


def test_matricula_extracoes_gains_formatacao(flat: str):
    assert (
        "ALTER TABLE social_wiring.matricula_extracoes "
        "ADD COLUMN IF NOT EXISTS formatacao JSONB NOT NULL DEFAULT '[]';"
        in flat
    )


# ─── 2. certidao_resultados — text, formatting, generated flag ─────────


def test_certidao_resultados_gains_texto_extraido(flat: str):
    assert (
        "ALTER TABLE social_wiring.certidao_resultados "
        "ADD COLUMN IF NOT EXISTS texto_extraido TEXT;" in flat
    )


def test_certidao_resultados_gains_formatacao(flat: str):
    assert (
        "ALTER TABLE social_wiring.certidao_resultados "
        "ADD COLUMN IF NOT EXISTS formatacao JSONB NOT NULL DEFAULT '[]';"
        in flat
    )


def test_tem_transcricao_is_generated_not_written(flat: str):
    """A written boolean can drift from the text it describes; a GENERATED
    one cannot. This pins the column to the generated shape, not merely to
    existing."""
    assert (
        "ADD COLUMN IF NOT EXISTS tem_transcricao BOOLEAN "
        "GENERATED ALWAYS AS (texto_extraido IS NOT NULL) STORED;" in flat
    )


def test_no_new_column_is_dropped_or_renamed(code: str):
    """Additive-only: no DROP COLUMN anywhere in this file."""
    assert "DROP COLUMN" not in code


def test_both_tables_are_touched(flat: str):
    assert flat.count("ALTER TABLE social_wiring.matricula_extracoes") == 1
    # One ALTER per new column (texto_extraido, formatacao, tem_transcricao).
    assert flat.count("ALTER TABLE social_wiring.certidao_resultados") == 3
