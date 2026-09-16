"""Structural (parse-based) tests for `124_fotos_referencias_guias.sql`.

Pins the platform-scope (no org_id) exception, the archive-not-delete
semantics on the reference pool, and the at-most-one-active-guide
constraint.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "124_fotos_referencias_guias.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


def test_neither_table_carries_org_id(flat: str):
    """Platform-scope exception, documented like status_pagina /
    cliente_documento_tipos — deliberately NOT org-scoped."""
    for table in ("fotos_referencias", "fotos_guias_estilo"):
        bloco = flat.split(f"CREATE TABLE IF NOT EXISTS social_wiring.{table}")[1]
        bloco = bloco.split(");", 1)[0]
        assert "org_id" not in bloco, f"{table} must not carry org_id"


def test_both_tables_readable_by_any_authenticated_user(flat: str):
    for table in ("fotos_referencias", "fotos_guias_estilo"):
        assert f'CREATE POLICY "{table}_select_authenticated" ON social_wiring.{table}' in flat
    assert "USING (true)" in flat


def test_both_tables_have_service_role_bypass(flat: str):
    for table in ("fotos_referencias", "fotos_guias_estilo"):
        assert f'CREATE POLICY "service_role_bypass" ON social_wiring.{table}' in flat


def test_referencia_delete_is_archive_not_a_row_delete(flat: str):
    bloco = flat.split("CREATE TABLE IF NOT EXISTS social_wiring.fotos_referencias")[1]
    bloco = bloco.split(");", 1)[0]
    assert "arquivado_em TIMESTAMPTZ" in bloco


def test_referencia_room_vocabulary_is_fixed(flat: str):
    assert "comodo TEXT NOT NULL CHECK (comodo IN (" in flat
    for room in ("sala", "quarto", "cozinha", "banheiro"):
        assert f"'{room}'" in flat


def test_at_most_one_active_guide_version(flat: str):
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_fotos_guias_estilo_uma_ativa" in flat
    assert "WHERE status = 'ativa'" in flat


def test_guide_versions_are_never_updated_only_inserted(code: str):
    assert "UPDATE social_wiring.fotos_guias_estilo" not in code


def test_guia_restore_field_points_at_a_prior_version(flat: str):
    assert "gerado_de_versao INTEGER" in flat
