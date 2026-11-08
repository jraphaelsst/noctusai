"""Structural tests for core `decouple_erp_public_fns` (no database needed).

The behavioural proof (a new auth.users insert writes nothing to `erp`) runs on the real core
chain in PGlite: mcp/noctusai/tests/test_core_decouple_erp_public_fns_on_replay.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1] / "migrations", "decouple_erp_public_fns")


@pytest.fixture(scope="module")
def code() -> str:
    sql = MIGRATION.read_text(encoding="utf-8")
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return " ".join(code.split())


def test_migration_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_no_executable_statement_references_the_erp_schema(code: str):
    # string/comment-free enough: the executable text never names the erp schema
    assert not re.search(r"\berp\.", code), "migration code must not reference erp.*"


def test_drops_are_idempotent_and_ordered(flat: str):
    trig = flat.index("DROP TRIGGER IF EXISTS on_auth_user_created_assign_role ON auth.users")
    fn = flat.index("DROP FUNCTION IF EXISTS public.assign_default_corretor_role()")
    assert trig < fn, "trigger must go before its function"
    # on_license_change (the only caller) is redefined BEFORE provision_erp is dropped
    redef = flat.index("CREATE OR REPLACE FUNCTION public.on_license_change()")
    drop = flat.index("DROP FUNCTION IF EXISTS public.provision_erp(uuid)")
    assert redef < drop


def test_has_role_is_left_alone(flat: str):
    assert "has_role" not in flat


def test_redefined_definer_functions_stay_pinned_and_service_only(flat: str):
    for fn in ("handle_new_user", "on_license_change", "snapshot_product_usage"):
        assert f"REVOKE ALL ON FUNCTION public.{fn}() FROM PUBLIC, anon, authenticated" in flat
    assert flat.count("SECURITY DEFINER SET search_path TO 'public'") == 3
