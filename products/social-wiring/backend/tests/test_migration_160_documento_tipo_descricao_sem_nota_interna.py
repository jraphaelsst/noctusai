"""Structural tests for `160_documento_tipo_descricao_sem_nota_interna.sql`.

Parse-based, like `test_migration_119_cliente_identidade_ativacao.py` — the
migration is a FILE, not an applied change, and there is no dev database to
run it against. These pin: the flip is an UPDATE (no schema change), it
targets exactly `rg`/`cpf`, it is forward-only, and the resulting label no
longer carries 119's intake-tracking sentence — only a plain document name,
matching the shape every other row in the catalogue already uses.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "160_documento_tipo_descricao_sem_nota_interna.sql"
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
    """A data flip, nothing else — no schema change."""
    upper = code.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper
    assert "CREATE TABLE" not in upper
    assert "ALTER TABLE" not in upper
    assert "ADD CONSTRAINT" not in upper


def test_updates_exactly_the_cliente_documento_tipos_table(flat: str):
    assert "UPDATE social_wiring.cliente_documento_tipos" in flat


def test_touches_only_rg_and_cpf(flat: str):
    assert "WHERE tipo_documento IN ('rg', 'cpf')" in flat


def test_does_not_touch_ativo_retencao_or_categoria_columns(flat: str):
    """119 already flipped `ativo = true`; 057 already seeded
    `retencao_dias`/`categoria_lgpd`/`identidade` — this migration only
    rewrites `descricao`, nothing else on the row."""
    assert "ativo" not in flat
    assert "retencao_dias" not in flat
    assert "categoria_lgpd" not in flat


def test_descricao_no_longer_carries_the_intake_note(flat: str):
    """The user-facing picker label must read as a plain document name —
    not the compliance sentence 119 put there. That sentence stays in
    migration history (119's own header) and the LGPD register; it does
    not get a second, API-visible home on this column."""
    assert "intake LGPD" not in flat
    assert "concluído" not in flat
    assert "pendente" not in flat


def test_descricao_becomes_a_plain_label_for_each_type(flat: str):
    assert "'RG (documento de identidade)'" in flat
    assert "'CPF (documento de identidade)'" in flat
