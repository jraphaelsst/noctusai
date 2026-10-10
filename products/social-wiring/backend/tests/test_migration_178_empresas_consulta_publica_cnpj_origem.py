"""Structural tests for `*_empresas_consulta_publica_cnpj_origem.sql`.

Parse-based, like the sibling small migrations (157/177) — the migration is
a FILE, not an applied change. This one is COMMENT-only (no DDL touching
rows or constraints): it pins that the `empresas.dados_origem` documentation
vocabulary now names `consulta_publica_cnpj` alongside the three migration
167 already documented, that the file is forward-only, and that it touches
no other table/column.
"""
from __future__ import annotations

from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "empresas_consulta_publica_cnpj_origem")


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


def test_is_forward_only_and_comment_only(flat: str):
    upper = flat.upper()
    for forbidden in (
        "DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE",
        "UPDATE ", "ALTER TABLE", "CREATE TABLE",
    ):
        assert forbidden not in upper
    assert upper.count("COMMENT ON COLUMN") == 1


def test_comment_targets_dados_origem_only(flat: str):
    assert "COMMENT ON COLUMN social_wiring.empresas.dados_origem IS" in flat


def test_comment_documents_the_new_origem_and_keeps_the_old_three(flat: str):
    assert "consulta_publica_cnpj" in flat
    for origem_existente in ("serasa_crednet", "cartao_cnpj", "manual", "certidao_consulta"):
        assert origem_existente in flat


def test_comment_documents_the_precedence_rule(flat: str):
    """The comment must say a Cartão CNPJ outranks the public lookup — the
    ONE place this vocabulary is documented at all (migration 167 leaves
    `dados_origem` a bare `TEXT`, no DB CHECK)."""
    assert "outranks" in flat.lower()
