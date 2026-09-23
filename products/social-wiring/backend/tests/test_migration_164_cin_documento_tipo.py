"""Structural tests for `164_cin_documento_tipo.sql`.

Parse-based, like `test_migration_142_cnh_documento_tipo.py` (whose shape
this mirrors) — the migration is a FILE, not an applied change. These pin:
the `cin` catalogue row's policy shape (mirrors `cnh`'s from 142), the
matching platform-tier retention row, the forward-only/idempotent shape, and
the owner's "no CIN extraction" ruling — `deve_extrair('cin')` must stay
false, since no real CIN exists yet to build an extractor against.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.card_hub import identidade_extracao_service as identidade_svc

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "164_cin_documento_tipo.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — header prose must never satisfy a
    check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with whitespace runs collapsed."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only_no_schema_change(code: str):
    upper = code.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper
    assert "CREATE TABLE" not in upper
    assert "ALTER TABLE" not in upper


def test_seeds_the_cin_catalogue_row_mirroring_cnh(flat: str):
    assert "INSERT INTO social_wiring.cliente_documento_tipos" in flat
    assert "'cin', 'identidade', 1825, true, true" in flat


def test_catalogue_insert_is_idempotent(flat: str):
    assert "ON CONFLICT (tipo_documento) DO UPDATE" in flat


def test_seeds_the_platform_tier_retention_policy(flat: str):
    assert "INSERT INTO social_wiring.documento_retencao_politicas" in flat
    assert "(NULL, 'cliente', 'cin', 1825," in flat


def test_retention_insert_is_idempotent_against_the_partial_index(flat: str):
    """The unique index this must not violate on re-run is a PARTIAL one
    (`WHERE org_id IS NULL`, migration 079) — a plain
    `ON CONFLICT (superficie, tipo_documento) DO NOTHING` would not match it
    and would raise `42P10` on a second run."""
    assert (
        "ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING"
        in flat
    )


# ─── the owner's ruling: a CIN is uploaded, never extracted ────────────────


def test_cin_is_not_extractable():
    """No real CIN exists yet — its fields are validated by the operator.
    `cin` must therefore stay out of `proveniencia.fontes.FONTES`, which is
    what keeps the extraction gate closed for it."""
    assert identidade_svc.deve_extrair("cin") is False


def test_cnh_stays_extractable():
    """The sibling slot of the same checklist item keeps its extractor."""
    assert identidade_svc.deve_extrair("cnh") is True
