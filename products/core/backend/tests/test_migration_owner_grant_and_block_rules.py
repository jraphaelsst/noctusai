"""Static checks for core ``*_owner_grant_and_block_rules`` -- multi-org S5b (owner decisions P1-P5,
2026-10-14).

Behaviour is proven on a real Postgres by
``mcp/noctusai/tests/test_core_owner_grant_and_block_rules_on_replay.py`` and by the
``verify_db_guards`` probes; this file pins the SQL's shape.
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "products/core/backend/migrations"
SQL = migration_path(MIGRATIONS, "owner_grant_and_block_rules").read_text(encoding="utf-8")
CODE = " ".join(re.sub(r"--[^\n]*", "", SQL).split())

_SERVICE_ONLY = {
    "org_member_product_access_set": "uuid, uuid, uuid, text, boolean",
    "team_member_set_role": "uuid, uuid, text, uuid",
    "team_member_move": "uuid, uuid, uuid, uuid, text, text",
}


def test_only_create_or_replace_of_the_three_functions():
    created = re.findall(r"CREATE OR REPLACE FUNCTION public\.(\w+)\(", CODE)
    assert sorted(created) == sorted(_SERVICE_ONLY)
    for forbidden in ("DROP ", "ALTER TABLE", "CREATE TABLE", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in CODE, forbidden


def test_functions_stay_service_role_only():
    for fn, args in _SERVICE_ONLY.items():
        assert f"REVOKE EXECUTE ON FUNCTION public.{fn}({args}) FROM PUBLIC, anon, authenticated;" in CODE
        assert f"GRANT EXECUTE ON FUNCTION public.{fn}({args}) TO service_role;" in CODE


def test_p1_owner_grants_are_decided_from_the_actor():
    assert CODE.count("RAISE EXCEPTION 'team_membership:owner_grant_forbidden'") == 2
    assert CODE.count("public.platform_staff_role(p_actor_id) IS NULL") == 2


def test_p3_staff_are_never_blocked_and_p5_blocks_are_owner_only():
    assert "IF p_blocked AND public.platform_staff_role(p_user_id) IS NOT NULL THEN" in CODE
    assert "RAISE EXCEPTION 'team_membership:cannot_block_staff'" in CODE
    assert "public.org_manager_role(p_actor_id, p_org_id) IS DISTINCT FROM 'owner'" in CODE
