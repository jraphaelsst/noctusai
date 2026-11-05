"""Structural tests for ``*_imoveis_sync_execucoes.sql`` (Vista refresh runs). Behaviour on a real Postgres is the chain replay."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "imoveis_sync_execucoes")


@pytest.fixture(scope="module")
def sql():
    return " ".join(re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).split())


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_forward_only_and_backend_only(sql):
    assert MIGRATION.name.startswith("316_")
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "SECURITY DEFINER"):
        assert forbidden not in upper
    assert "ENABLE ROW LEVEL SECURITY" in sql and "TO service_role" in sql
    assert "REVOKE ALL ON social_wiring.imoveis_sync_execucoes FROM PUBLIC, anon, authenticated" in sql


def test_status_and_path_vocabulary(sql):
    for v in ("em_andamento", "listar_vazio", "removidos_excessivos", "sem_credencial", "ignorada"):
        assert f"'{v}'" in sql
    assert "caminho text CHECK (caminho IS NULL OR caminho IN ('listar', 'detalhes'))" in sql
