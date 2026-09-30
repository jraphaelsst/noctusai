"""Structural tests for `164_cin_documento_tipo.sql`.

Parse-based, like `test_migration_142_cnh_documento_tipo.py` (whose shape
this mirrors) — the migration is a FILE, not an applied change. These pin:
the `cin` catalogue row's policy shape (mirrors `cnh`'s from 142), the
matching platform-tier retention row, and the forward-only/idempotent shape.

🔴 The migration's ORIGINAL "no CIN extraction" ruling — `deve_extrair('cin')`
must stay false, since no real CIN exists yet to build an extractor against —
is SUPERSEDED (found on prod 2026-09-30, live test; see the migration file's
own header and `proveniencia.fontes.FONTES["cin"]`). `cin` is extractable now,
mirroring `cnh`; the tests below pin the reversal instead of the original
ruling.
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


# ─── the reversal: a CIN is now extracted, like its sibling CNH slot ───────


def test_identity_extraction_now_lists_cin_as_extractable():
    """A real CIN corpus arrived (P2, 2026-09-28) and `proveniencia.fontes.
    FONTES` grew a matching `cin` entry — `deve_extrair` is derived from
    that registry, so this needed no extra wiring here, same as `cnh`'s own
    `test_migration_142_cnh_documento_tipo.py::
    test_identity_extraction_already_lists_cnh_as_extractable`."""
    assert identidade_svc.deve_extrair("cin") is True


def test_cnh_stays_extractable():
    """The sibling slot of the same checklist item keeps its extractor."""
    assert identidade_svc.deve_extrair("cnh") is True
