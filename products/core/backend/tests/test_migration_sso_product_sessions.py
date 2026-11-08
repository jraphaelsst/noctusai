"""Structural tests for the core product-session registry migration: service-only tier, no client path."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "sso_product_sessions")
CODE = "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--"))


def test_table_is_service_only():
    assert "ENABLE ROW LEVEL SECURITY" in CODE
    assert not re.search(r"CREATE\s+POLICY", CODE, re.I), "no client policies: service role only"
    assert re.search(r"REVOKE ALL ON public\.sso_product_sessions FROM PUBLIC, anon, authenticated", CODE)
    assert not re.search(r"GRANT\s+(?!EXECUTE)[^;]*sso_product_sessions", CODE, re.I)
    assert "COMMENT ON TABLE public.sso_product_sessions IS 'tier:service'" in CODE


def test_shape_matches_the_design_record():
    for col in ("session_id   uuid        PRIMARY KEY", "user_id      uuid        NOT NULL",
                "product_slug text        NOT NULL", "jti          text,",
                "minted_at    timestamptz NOT NULL DEFAULT now()"):
        assert col in CODE


def test_no_fk_into_the_auth_schema_sessions_table():
    # GoTrue-owned and not stubbed by the replay harness; the decision is documented in the header.
    assert not re.search(r"REFERENCES\s+auth\.sessions", CODE, re.I)
    assert "FK to auth.sessions? DECIDED: NO FK" in SQL


def test_purge_function_is_locked_down():
    assert "SECURITY DEFINER" in CODE and "SET search_path" in CODE
    assert "REVOKE EXECUTE ON FUNCTION public.sso_product_sessions_purge() FROM PUBLIC, anon, authenticated" in CODE
    assert "GRANT EXECUTE ON FUNCTION public.sso_product_sessions_purge() TO service_role" in CODE
