"""Static tests for ``the org_id_default_acting_aware migration``.

Acting-as incident 2026-11-06: a column ``org_id DEFAULT public.current_org_id()``
(HOME-ONLY) under a picker-aware WITH CHECK (``current_org_id_for``) refuses the
INSERT of a platform admin acting as another org. this migration swaps every such default;
this pins its shape and that no later migration re-introduces a home-only default.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path, migration_sql

pglast = pytest.importorskip("pglast")
from pglast import parse_sql  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
SQL = migration_sql(MIGRATIONS, "org_id_default_acting_aware")


def test_parses_and_guards_on_the_helper():
    assert len(parse_sql(SQL)) == 2
    assert "current_org_id_for(text)" in SQL.split("$guard$")[1]


def test_swaps_home_only_defaults_to_the_picker_aware_helper():
    assert "SET DEFAULT public.current_org_id_for(%L)" in SQL
    assert "'social_wiring'" in SQL and "'mailing'" in SQL
    assert re.search(r"current_\(user_\)\?org_id\\\(\\\)", SQL)


def test_no_later_migration_adds_a_home_only_org_id_default():
    bad = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name <= migration_path(MIGRATIONS, "org_id_default_acting_aware").name:
            continue
        body = re.sub(r"--[^\n]*", "", f.read_text())
        if re.search(r"org_id[^,;]*DEFAULT[^,;]*current_(user_)?org_id\(\)", body, re.I):
            bad.append(f.name)
    assert bad == []
