"""Structural tests for `119_cliente_identidade_ativacao.sql`.

Parse-based, like `test_migration_114_termos_negocio.py` — the migration is a
FILE, not an applied change, and there is no dev database to run it against.
These pin: the flip is an UPDATE (no schema change, no CHECK touched), it
targets exactly `rg`/`cpf`, it is forward-only, and the service module that
was ALREADY WIRED to extract identity fields off these two types needs no
matching change — `deve_extrair('rg'/'cpf')` was true before this migration
too; only the upload-time `ativo` gate blocked them from ever reaching it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.modules.card_hub import identidade_extracao_service as identidade_svc

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "119_cliente_identidade_ativacao.sql"
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


def test_is_forward_only_and_schema_free(code: str):
    """No DROP/DELETE/TRUNCATE and — unlike every other numbered migration in
    this product — no CREATE TABLE / ALTER TABLE ADD COLUMN / CREATE
    CONSTRAINT either. This migration is a data flip, nothing else."""
    upper = code.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper
    assert "CREATE TABLE" not in upper
    assert "ALTER TABLE" not in upper
    assert "ADD CONSTRAINT" not in upper


def test_updates_exactly_the_cliente_documento_tipos_table(flat: str):
    assert "UPDATE social_wiring.cliente_documento_tipos" in flat


def test_flips_ativo_true_for_rg_and_cpf_only(flat: str):
    assert "ativo = true" in flat
    assert "WHERE tipo_documento IN ('rg', 'cpf')" in flat


def test_does_not_touch_retencao_or_categoria_columns(flat: str):
    """057 already seeded `retencao_dias=1825`, `categoria_lgpd='identidade'`,
    `identidade=true` for both rows — this migration must not re-declare
    them, only flip the gate."""
    assert "retencao_dias" not in flat
    assert "categoria_lgpd" not in flat
    assert re.search(r"\bidentidade\s*=", flat) is None


def test_header_names_the_lgpd_intake_and_decision_date(sql: str):
    assert "lgpd_flag" in sql
    assert "2026-09-16" in sql


def test_descricao_no_longer_reads_as_withheld(flat: str):
    assert "retenção pendente de intake LGPD" not in flat
    assert "intake LGPD concluído" in flat


# ─── the pipeline this unblocks was already wired ──────────────────────────


def test_identity_extraction_already_lists_rg_and_cpf_as_extractable():
    """The migration's header claims no code change is needed for extraction
    to start running off rg/cpf uploads once `ativo` flips — this is the
    fact that claim rests on."""
    assert identidade_svc.deve_extrair("rg") is True
    assert identidade_svc.deve_extrair("cpf") is True
