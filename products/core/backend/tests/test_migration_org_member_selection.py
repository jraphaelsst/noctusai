"""Static checks for core ``*_org_member_selection`` -- multi-org S2+S3 (owner decisions 2026-10-13).

Members switch orgs through the EXISTING platform org picker: the selection RPC widens WHO may
select from "staff" to "staff OR an ACTIVE member", and ``current_org_id_for`` honours a member's
selection only while the membership is ACTIVE (re-checked every call, nothing in the JWT). The live
behaviour is proven by ``noctus.dev.verify_db_guards`` probes (rolled back) and by the PGlite replay
test ``mcp/noctusai/tests/test_core_078_probes_on_replay.py``; this file pins the SQL's shape.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "products/core/backend/migrations"
THIS = migration_path(MIGRATIONS, "org_member_selection")
SQL = THIS.read_text(encoding="utf-8")
FLAT = " ".join(SQL.split())
#: The helper declaration this migration supersedes.
SQL_PREV = migration_path(MIGRATIONS, "org_picker_postgrest_entry").read_text(encoding="utf-8")


def _canon() -> str:
    tpl = ROOT / "seed/lib/backend/noctusai_lib/domain/sql_templates.py"
    spec = importlib.util.spec_from_file_location("_t_member_sel_sql_templates", tpl)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return " ".join(mod.org_identity_function_sql("current_org_id_for", customer_roles=["membro"]).split())


def _fn(sql: str, name: str) -> str:
    m = re.search(rf"CREATE OR REPLACE FUNCTION public\.{name}\(.*?\n(?:\$\$|\$f\$);", sql, re.S)
    assert m is not None, name
    return " ".join(m.group(0).split())


def test_helper_is_the_canonical_rendering():
    assert _canon() in FLAT


def test_is_the_last_core_declaration_of_both_functions():
    for pattern in (r"FUNCTION\s+public\.current_org_id_for\s*\(", r"FUNCTION\s+public\.platform_org_selection_set\s*\("):
        declaring = [
            p.name for p in sorted(MIGRATIONS.glob("[0-9]*.sql"))
            if re.search(pattern, p.read_text(encoding="utf-8"))
        ]
        assert declaring[-1] == THIS.name, pattern


def test_expand_only_function_replacement_no_table_or_column_change():
    assert "DROP TABLE" not in FLAT and "DROP COLUMN" not in FLAT
    assert "ALTER TABLE" not in FLAT and "CREATE TABLE" not in FLAT


def test_execute_stays_with_the_rls_helper_marker_and_the_rpc_stays_service_only():
    assert re.search(r"-- secdef-execute-ok: rls-helper[^\n]*\nCREATE OR REPLACE FUNCTION public\.current_org_id_for", SQL)
    assert "REVOKE EXECUTE ON FUNCTION public.current_org_id_for" not in SQL
    assert "REVOKE EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) FROM PUBLIC, anon, authenticated;" in FLAT
    assert "GRANT EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) TO service_role;" in FLAT


class TestSelectionRpc:
    BODY = " ".join(_fn(SQL, "platform_org_selection_set").split())

    def test_a_non_staff_caller_must_hold_an_active_membership_in_the_target(self):
        assert "FROM public.org_memberships m WHERE m.user_id = p_user_id AND m.org_id = p_target_org_id AND m.status = 'active'" in self.BODY
        assert "RAISE EXCEPTION 'platform_org_selection:not_a_member';" in self.BODY

    def test_the_membership_is_locked_so_a_concurrent_removal_waits(self):
        assert "FOR SHARE" in self.BODY

    def test_staff_path_is_unchanged_and_never_touches_the_profile(self):
        # the profile UPDATE only runs for the member path
        assert re.search(r"IF NOT v_staff THEN -- Q3.*?UPDATE public\.noctus_users", self.BODY)
        assert self.BODY.count("UPDATE public.noctus_users") == 1

    def test_the_profile_follows_with_the_membership_role_never_a_promotion(self):
        assert "SET org_id = p_target_org_id, org_role = v_mrole" in self.BODY
        assert "v_mrole" in self.BODY.split("SELECT m.org_role INTO v_mrole")[1]

    def test_the_profile_moves_before_the_selection_is_written(self):
        # the 070 revocation trigger ends the user's live selections on a profile change, so the
        # INSERT of the new selection must come AFTER the UPDATE or it would be revoked at once.
        assert self.BODY.index("UPDATE public.noctus_users") < self.BODY.index("INSERT INTO public.platform_org_selections")

    def test_it_never_ends_or_deletes_a_membership(self):
        assert "org_memberships" in self.BODY
        assert "UPDATE public.org_memberships" not in self.BODY
        assert "DELETE" not in self.BODY and "'removed'" not in self.BODY

    def test_license_and_ready_refusals_are_kept_for_everyone(self):
        assert "RAISE EXCEPTION 'platform_org_selection:product_not_ready';" in self.BODY
        assert "RAISE EXCEPTION 'platform_org_selection:target_not_licensed';" in self.BODY


class TestHelper:
    BODY = _canon()

    def test_member_selection_requires_an_active_membership_checked_on_every_call(self):
        assert "JOIN public.org_memberships m ON m.user_id = v_uid AND m.org_id = s.target_org_id AND m.status = 'active'" in self.BODY

    def test_members_need_no_aal2(self):
        member = self.BODY.split("ELSIF p_schema IS NOT NULL THEN")[1].split("RETURN v_home;")[0]
        assert "aal" not in member and "org_picker_requires_mfa" not in member

    def test_the_pin_header_only_narrows_for_members(self):
        member = self.BODY.split("ELSIF p_schema IS NOT NULL THEN")[1].split("RETURN v_home;")[0]
        assert "IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN RETURN v_target; END IF; RETURN NULL;" in member

    def test_the_home_fallback_requires_an_active_membership_so_a_removed_org_is_never_served(self):
        assert (
            "IF NOT EXISTS (SELECT 1 FROM public.org_memberships m WHERE m.user_id = v_uid "
            "AND m.org_id = v_home AND m.status = 'active') THEN RETURN NULL; END IF; RETURN v_home;"
        ) in self.BODY

    def test_customer_roles_resolve_null_for_a_selected_membership_too(self):
        assert "IF COALESCE(v_mrole, '') = ANY (ARRAY['membro']) THEN RETURN NULL;" in self.BODY

    def test_only_the_member_branch_and_the_home_check_are_new_relative_to_078(self):
        prev = _fn(SQL_PREV, "current_org_id_for")
        new = _canon()
        for staff_line in (
            "IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN RETURN v_target; END IF; RETURN NULL; END IF;",
            "AND (NOT p.org_picker_requires_mfa OR v_claims ->> 'aal' = 'aal2')",
            "AND EXISTS (SELECT 1 FROM auth.sessions se WHERE se.id = s.auth_session_id)",
        ):
            assert staff_line in prev and staff_line in new


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 4


def test_profile_org_must_stay_an_active_membership():
    """Revocation-safety for every reader that trusts noctus_users.org_id: ending the membership a
    profile points at is refused at COMMIT unless the profile moves in the same transaction."""
    assert "CREATE CONSTRAINT TRIGGER org_memberships_profile_org_active" in FLAT
    assert "AFTER UPDATE OR DELETE ON public.org_memberships DEFERRABLE INITIALLY DEFERRED" in FLAT
    assert "RAISE EXCEPTION 'org_memberships_profile_org_active:" in FLAT
    fn = _fn(SQL, "org_memberships_profile_org_active")
    assert "m.status = 'active'" in fn
    assert "REVOKE EXECUTE ON FUNCTION public.org_memberships_profile_org_active() FROM PUBLIC, anon, authenticated" in FLAT
    # the migration refuses to install over data that already breaks the invariant
    assert "profile(s) point at an org without an ACTIVE membership" in FLAT
