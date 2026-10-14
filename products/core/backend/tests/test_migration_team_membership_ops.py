"""Static checks for core ``*_team_membership_ops`` -- multi-org S4 (roadmap P2.3).

Behaviour is proven on a real Postgres by ``mcp/noctusai/tests/test_core_team_membership_ops_on_replay.py``
and by the ``team_*`` GuardProbes; this file pins the SQL's shape: three service-role-only SECURITY
DEFINER functions, expand-only, no table/column change, refusals under the ``team_membership:`` prefix
the router maps (every code the SQL raises has a status in the router's ERROR_MAP).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "products/core/backend/migrations"
SQL = migration_path(MIGRATIONS, "team_membership_ops").read_text(encoding="utf-8")
FLAT = " ".join(SQL.split())

_FUNCS = {
    "team_member_remove": "uuid, uuid",
    "team_member_set_role": "uuid, uuid, text",
    "team_invitation_accept": "uuid, uuid",
}


def test_three_security_definer_functions_with_a_pinned_search_path():
    for name in _FUNCS:
        m = re.search(rf"CREATE OR REPLACE FUNCTION public\.{name}\(.*?\$f\$;", SQL, re.S)
        assert m, name
        body = " ".join(m.group(0).split())
        assert "SECURITY DEFINER" in body and "SET search_path = public" in body, name


def test_execute_is_revoked_from_every_api_role_and_granted_to_service_role_only():
    for name, args in _FUNCS.items():
        assert f"REVOKE EXECUTE ON FUNCTION public.{name}({args}) FROM PUBLIC, anon, authenticated;" in FLAT
        assert f"GRANT EXECUTE ON FUNCTION public.{name}({args}) TO service_role;" in FLAT
        assert re.search(rf"GRANT\s+EXECUTE ON FUNCTION public\.{name}\([^)]*\) TO (?!service_role)", FLAT) is None


def test_expand_only_no_table_or_column_change_and_no_drop():
    code = " ".join(re.sub(r"--[^\n]*", "", SQL).split())  # comments may NAME the rollback
    for banned in ("CREATE TABLE", "ALTER TABLE", "DROP TABLE", "DROP COLUMN", "DROP FUNCTION", "DROP TRIGGER"):
        assert banned not in code, banned


def test_does_not_redeclare_the_picker_functions_081_owns():
    assert "FUNCTION public.current_org_id_for" not in SQL
    assert "FUNCTION public.platform_org_selection_set" not in SQL


def test_every_refusal_code_the_sql_raises_is_mapped_by_the_router():
    sys.path.insert(0, str(ROOT / "products/core/backend"))
    from app.services.team_memberships import ERROR_MAP

    raised = set(re.findall(r"team_membership:(\w+)", SQL))
    assert raised, "no refusal codes found"
    assert raised <= set(ERROR_MAP), raised - set(ERROR_MAP)
