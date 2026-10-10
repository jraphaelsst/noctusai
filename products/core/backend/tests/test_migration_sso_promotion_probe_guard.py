"""Static tests for ``migrations/*_sso_promotion_probe_guard.sql``.

The trigger is not exercised against a real Postgres here (no engine in the
unit suite); these pin its parse + the shape that carries the invariant.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

pglast = pytest.importorskip("pglast")
from pglast import parse_sql  # noqa: E402

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "sso_promotion_probe_guard")


def test_parses():
    assert len(parse_sql(SQL)) >= 5


def test_backfills_live_rows_before_the_trigger_exists_and_is_idempotent():
    assert SQL.index("UPDATE public.products") < SQL.index("CREATE TRIGGER")
    assert "sso_callback_verified_at IS NULL" in SQL.split("CREATE OR REPLACE FUNCTION")[0]


def test_refuses_transition_into_live_and_clears_on_leaving_live():
    body = SQL.split("$$")[1]
    assert "IS DISTINCT FROM 'live'" in body
    assert "NEW.sso_callback_verified_at := NULL" in body
    assert "RAISE EXCEPTION" in body and "check_violation" in body


def test_trigger_covers_insert_and_update():
    assert "BEFORE INSERT OR UPDATE ON public.products" in SQL
