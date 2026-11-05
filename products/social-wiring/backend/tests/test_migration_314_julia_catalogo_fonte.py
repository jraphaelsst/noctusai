"""Structural tests for ``*_julia_catalogo_fonte.sql`` (julia-v3, CONTRACT 12.7). Behaviour on a real Postgres is the
chain replay (`noctus.dev.migration_replay`)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "julia_catalogo_fonte")


@pytest.fixture(scope="module")
def sql():
    return " ".join(re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).split())


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_number_and_forward_only(sql):
    assert MIGRATION.name.startswith("314_")
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "SECURITY DEFINER"):
        assert forbidden not in upper
    assert "SET search_path = social_wiring, public;" in sql


def test_table_shape_default_and_check(sql):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.julia_catalogo_config" in sql
    assert "org_id uuid PRIMARY KEY" in sql
    assert "fonte text NOT NULL DEFAULT 'espelho' CHECK (fonte IN ('vista', 'espelho'))" in sql


def test_backend_only_like_every_julia_table(sql):
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "TO service_role" in sql
    assert "REVOKE ALL ON social_wiring.julia_catalogo_config FROM PUBLIC, anon, authenticated" in sql
