"""Structural tests for `142_cnh_documento_tipo.sql`.

Parse-based, like `test_migration_119_cliente_identidade_ativacao.py` — the
migration is a FILE, not an applied change, and there is no dev database to
run it against. These pin: the new catalogue row's exact policy shape (mirrors
`rg`'s from migration 057), the matching retention-policy platform-tier row
(mirrors what 079 backfilled for `rg`, since `cnh` did not exist yet to be
copied), forward-only/idempotent shape, and that `identidade_extracao_service`
needed no matching code change — `deve_extrair('cnh')` was already true before
this migration; only the upload-time catalogue gate blocked it from ever
reaching that code.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.card_hub import identidade_extracao_service as identidade_svc

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "142_cnh_documento_tipo.sql"
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


def test_seeds_the_cnh_catalogue_row_mirroring_rg(flat: str):
    assert "INSERT INTO social_wiring.cliente_documento_tipos" in flat
    assert "'cnh', 'identidade', 1825, true, true" in flat


def test_catalogue_insert_is_idempotent(flat: str):
    assert "ON CONFLICT (tipo_documento) DO UPDATE" in flat


def test_seeds_the_platform_tier_retention_policy(flat: str):
    assert "INSERT INTO social_wiring.documento_retencao_politicas" in flat
    assert "(NULL, 'cliente', 'cnh', 1825," in flat


def test_retention_insert_is_idempotent_against_the_partial_index(flat: str):
    """The unique index this must not violate on re-run is a PARTIAL one
    (`WHERE org_id IS NULL`, migration 079) — a plain
    `ON CONFLICT (superficie, tipo_documento) DO NOTHING` would not match it
    and would raise `42P10` on a second run."""
    assert (
        "ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING"
        in flat
    )


# ─── the pipeline this unblocks was already wired ──────────────────────────


def test_identity_extraction_already_lists_cnh_as_extractable():
    """The migration's header claims no code change is needed for extraction
    to start running off `cnh` uploads once the catalogue row exists — this
    is the fact that claim rests on."""
    assert identidade_svc.deve_extrair("cnh") is True
