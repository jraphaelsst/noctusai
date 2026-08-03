"""Structural (parse-based) tests for
``migrations/041_leads_meta_lead_id.sql`` — mirrors ``test_migrations.py``'s
approach for 001/011 (read the file as text, assert the expected
structural elements are declared; no DB required).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_041_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "041_leads_meta_lead_id.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_041_PATH.is_file(), f"Migration file missing at {MIGRATION_041_PATH}"
    return MIGRATION_041_PATH.read_text(encoding="utf-8")


def test_adds_meta_lead_id_column_as_its_own_alter_table(sql: str) -> None:
    """One column, its own ``ALTER TABLE ... ADD COLUMN`` statement — the
    convention migration 028 established for
    ``noctusai_lib.testing.migration_parser`` (one ADD COLUMN match per
    ALTER TABLE occurrence)."""
    assert re.search(
        r"ALTER\s+TABLE\s+social_wiring\.leads\s+"
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+meta_lead_id\s+TEXT\s*;",
        sql,
        re.IGNORECASE,
    ), "Missing `ALTER TABLE social_wiring.leads ADD COLUMN IF NOT EXISTS meta_lead_id TEXT;`"


def test_unique_index_is_partial_and_org_scoped(sql: str) -> None:
    """Mirrors `uq_sw_leads_org_sheet_row`'s shape exactly: unique on
    (org_id, meta_lead_id), WHERE meta_lead_id IS NOT NULL."""
    assert re.search(
        r"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+uq_sw_leads_org_meta_lead_id\s+"
        r"ON\s+social_wiring\.leads\s*\(\s*org_id\s*,\s*meta_lead_id\s*\)\s+"
        r"WHERE\s+meta_lead_id\s+IS\s+NOT\s+NULL",
        sql,
        re.IGNORECASE | re.DOTALL,
    ), "Missing the partial UNIQUE index on (org_id, meta_lead_id) WHERE meta_lead_id IS NOT NULL"


def test_declares_no_new_table(sql: str) -> None:
    """This migration only adds a column + index to the EXISTING `leads`
    table — no new table, no new RLS policy (the tech-lead's correction:
    table-level policies from migration 025 already cover any new
    column)."""
    assert "CREATE TABLE" not in sql.upper(), (
        "041 should not create a new table — it only adds a column to the "
        "existing social_wiring.leads table"
    )
    assert "CREATE POLICY" not in sql.upper(), (
        "041 should not create a new RLS policy — leads_select_own_org / "
        "leads_service_role (migration 025) already cover every column"
    )


def test_carries_the_file_only_banner(sql: str) -> None:
    assert "MIGRATION FILE ONLY" in sql


def test_notifies_postgrest_to_reload_schema(sql: str) -> None:
    assert re.search(r"NOTIFY\s+pgrst\s*,\s*'reload schema'", sql, re.IGNORECASE)
