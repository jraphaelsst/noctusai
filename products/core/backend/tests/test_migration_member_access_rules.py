"""Static checks for core ``*_member_access_rules`` -- multi-org S4b (owner decisions D1-D5, 2026-10-14).

Behaviour is proven on a real Postgres by ``mcp/noctusai/tests/test_core_member_access_rules_on_replay.py``
and by the ``verify_db_guards`` probes; this file pins the SQL's shape.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "products/core/backend/migrations"
THIS = migration_path(MIGRATIONS, "member_access_rules")
SQL = THIS.read_text(encoding="utf-8")
FLAT = " ".join(SQL.split())
CODE = " ".join(re.sub(r"--[^\n]*", "", SQL).split())  # comments may NAME the rollback

_SERVICE_ONLY = {
    "platform_staff_role": "uuid",
    "org_manager_role": "uuid, uuid",
    "org_member_product_access_set": "uuid, uuid, uuid, text, boolean",
    "team_member_remove": "uuid, uuid, uuid, uuid",
    "team_member_set_role": "uuid, uuid, text, uuid",
    "team_member_move": "uuid, uuid, uuid, uuid, text, text",
    "team_invitation_accept": "uuid, uuid, text",
    "platform_org_selection_set": "uuid, text, uuid, uuid",
}


def _canon() -> str:
    tpl = ROOT / "seed/lib/backend/noctusai_lib/domain/sql_templates.py"
    spec = importlib.util.spec_from_file_location("_t_access_rules_sql_templates", tpl)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return " ".join(mod.org_identity_function_sql("current_org_id_for", customer_roles=["membro"]).split())


def test_helper_is_the_canonical_rendering_and_the_last_core_declaration():
    assert _canon() in FLAT
    for pattern in (r"FUNCTION\s+public\.current_org_id_for\s*\(", r"FUNCTION\s+public\.platform_org_selection_set\s*\("):
        declaring = [p.name for p in sorted(MIGRATIONS.glob("[0-9]*.sql"))
                     if re.search(pattern, p.read_text(encoding="utf-8"))]
        assert declaring[-1] == THIS.name, pattern


def test_expand_only_no_drop():
    for banned in ("DROP TABLE", "DROP COLUMN", "DROP FUNCTION"):
        assert banned not in CODE, banned
    assert "ADD COLUMN IF NOT EXISTS is_personal boolean NOT NULL DEFAULT false" in FLAT
    assert "CREATE TABLE IF NOT EXISTS public.org_member_product_access" in FLAT


def test_every_new_or_replaced_function_is_service_role_only():
    for name, args in _SERVICE_ONLY.items():
        assert f"REVOKE EXECUTE ON FUNCTION public.{name}({args}) FROM PUBLIC, anon, authenticated;" in FLAT, name
        assert f"GRANT EXECUTE ON FUNCTION public.{name}({args}) TO service_role;" in FLAT, name
    assert re.search(r"GRANT\s+EXECUTE ON FUNCTION public\.\w+\([^)]*\) TO (?!service_role)", FLAT) is None


def test_the_082_signatures_stay_as_wrappers_without_override_or_personal_org():
    assert "SELECT public.team_member_remove(p_org_id, p_user_id, NULL::uuid, NULL::uuid);" in FLAT
    assert "SELECT public.team_member_set_role(p_org_id, p_user_id, p_role, NULL::uuid);" in FLAT
    assert "SELECT public.team_invitation_accept(p_invitation_id, p_user_id, NULL::text);" in FLAT


def test_the_last_owner_override_is_the_noctusai_owner_only_decided_from_the_actor():
    # D2: never a caller-supplied boolean -- the actor's platform role is read in SQL
    assert FLAT.count("public.platform_staff_role(p_actor_id) IS DISTINCT FROM 'owner'") == 3
    assert "p_override" not in FLAT


def test_the_sole_membership_profile_is_never_deleted_any_more():
    remove = re.search(r"CREATE OR REPLACE FUNCTION public\.team_member_remove\(\s*p_org_id uuid, p_user_id uuid, p_actor_id.*?\$f\$;",
                       SQL, re.S).group(0)
    assert "DELETE FROM public.noctus_users" not in remove
    assert "team_membership:personal_org_required" in remove
    assert "o.owner_id = p_user_id AND o.is_personal" in " ".join(remove.split())


def test_block_table_rls_self_read_and_service_writes():
    assert "ALTER TABLE public.org_member_product_access ENABLE ROW LEVEL SECURITY;" in FLAT
    assert "REVOKE ALL ON public.org_member_product_access FROM PUBLIC, anon, authenticated;" in FLAT
    assert "GRANT SELECT ON public.org_member_product_access TO authenticated;" in FLAT
    assert "USING (user_id = (SELECT auth.uid()))" in FLAT
    assert "ON public.org_member_product_access (user_id, org_id, product_id) WHERE unblocked_at IS NULL" in FLAT


def test_the_selection_rpc_refuses_a_blocked_member_and_keeps_the_staff_path():
    assert "RAISE EXCEPTION 'platform_org_selection:product_blocked';" in FLAT
    assert "IF NOT v_staff AND EXISTS ( SELECT 1 FROM public.org_member_product_access a" in FLAT


def test_every_refusal_code_is_mapped_by_the_router():
    sys.path.insert(0, str(ROOT / "products/core/backend"))
    from app.services.team_memberships import ERROR_MAP

    raised = set(re.findall(r"team_membership:(\w+)", CODE))
    assert raised and raised <= set(ERROR_MAP), raised - set(ERROR_MAP)


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 20
