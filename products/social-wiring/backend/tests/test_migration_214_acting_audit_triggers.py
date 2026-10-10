"""Static tests for ``migrations/*_acting_audit_triggers.sql`` (org picker: PostgREST audit)."""
from __future__ import annotations

import re
from pathlib import Path
from noctusai_lib.testing.migrations import migration_path, migration_sql

import pytest

pglast = pytest.importorskip("pglast")
from pglast import parse_sql  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
SQL = migration_sql(MIGRATIONS, "acting_audit_triggers")


def test_parses_with_core_072_guard():
    assert len(parse_sql(SQL)) == 3
    assert "attach_acting_audit_triggers(text, text)" in SQL.split("$guard$")[1]


def test_attaches_both_schemas_keyed_by_the_product_schema():
    calls = re.findall(r"^SELECT public\.attach_acting_audit_triggers\(([^)]*)\);", SQL, re.MULTILINE)
    assert calls == ["'social_wiring'", "'mailing', 'social_wiring'"]


def test_runs_after_the_ready_flip():
    assert migration_path(MIGRATIONS, "org_picker_ready").name < migration_path(MIGRATIONS, "acting_audit_triggers").name
