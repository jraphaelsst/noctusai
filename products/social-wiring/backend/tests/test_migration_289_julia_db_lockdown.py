"""Structural tests for ``*_julia_db_lockdown.sql`` (security audit 2026-10-19 H1). Behaviour is proven on a real
Postgres chain by mcp/noctusai/tests/test_sw_julia_lockdown_probes_on_replay.py."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "julia_db_lockdown")


@pytest.fixture(scope="module")
def sql():
    return " ".join(re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).split())


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_forward_only_no_secdef_no_ddl_on_data(sql):
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "SECURITY DEFINER", "CREATE TABLE"):
        assert forbidden not in upper
    assert "SET search_path = social_wiring, public;" in sql


def test_covers_julia_tables_and_lais_compat_views_dynamically(sql):
    assert "LIKE 'julia\\_%'" in sql and "LIKE 'lais\\_%'" in sql
    assert "c.relkind IN ('r', 'p', 'v', 'm')" in sql
    assert "REVOKE ALL ON TABLE social_wiring.%I FROM PUBLIC, anon, authenticated" in sql


def test_drops_caller_policies_and_keeps_rls_enabled(sql):
    assert "DROP POLICY IF EXISTS" in sql and "p.roles && ARRAY['public', 'anon', 'authenticated']::name[]" in sql
    assert "DISABLE ROW LEVEL SECURITY" not in sql.upper()


def test_in_migration_assertion_with_empty_allowlist(sql):
    assert "v_allow text[] := ARRAY[]::text[]" in sql
    assert sql.count("RAISE EXCEPTION 'migration 289:") == 2
