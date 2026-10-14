"""Core ``member_access_rules`` (multi-org S4b, owner decisions D1-D5 2026-10-14) on the REAL core
chain on PGlite, triggers ON.

What this proves on a real Postgres (the router tests mock the RPCs):

* every registered S4b GuardProbe (``vdg._ACCESS_RULES_PROBES``) is clean with 083 and fails
  without it (the helper ones are also run, with the member probes, by
  ``test_core_078_probes_on_replay.py``);
* D2: platform staff manage any org; ONLY the NoctusAI owner overrides the last-owner rule (remove,
  demote, transfer) -- a NoctusAI admin and an org owner are refused;
* D3: an org admin of A only cannot move a user into B; an admin of both can, in both modes
  (``transfer`` ends the source and moves the profile, ``add`` keeps it); the target role is never
  above the actor's role there; staff move anyone;
* D4: removing a sole-org member keeps the profile, owner of a personal org (validated: owned by
  the user, ``is_personal``, empty); a first-time invitee gets profile + linked membership;
* D5: block / unblock is append-only history, needs a manager, ends a live selection of the org.

Each scenario fires the deferred invariant IMMEDIATE (``SET CONSTRAINTS ALL IMMEDIATE``) -- the
judgement COMMIT makes -- and is rolled back.
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path
from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

from tests.test_core_078_probes_on_replay import _FIXTURE_SQL as _PICKER_FIXTURE_SQL

_MIGRATIONS = Path(REPO_ROOT) / "products/core/backend/migrations"
_M083 = str(migration_path(_MIGRATIONS, "member_access_rules").relative_to(REPO_ROOT))
_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PICKER_FIXTURE = "core-083-picker-fixture"
_FIXTURE = "core-083-team-fixture"
_PASS = ("clean", "refused")

#: Registry probes that are not current_org_id_for helper probes (those run in the 078 test).
_PROBES = {p.id: p for p in vdg._ACCESS_RULES_PROBES if not p.id.startswith("current_org_id_for.")}

# Orgs: P (the picker fixture's platform org), A, B, C. Users: noc_owner (NoctusAI owner), noc_admin (NoctusAI admin),
# owner_a (only owner of A), admin_ab (admin of A and of B), admin_a (admin of A only),
# mem (member of A, profile A), solo (member of C only), newbie (auth user, no profile).
_FIXTURE_SQL = """
DO $$
DECLARE
  -- the platform org of the picker fixture (a NEW is_platform org would fan licences out to every
  -- product by the core 068 trigger, which this chain cannot satisfy)
  v_p uuid := (SELECT o.id FROM public.organizations o WHERE o.slug = 'noc-probe-plat');
  v_a uuid := '00000000-0000-0000-0000-0000000000fa';
  v_b uuid := '00000000-0000-0000-0000-0000000000fb';
  v_c uuid := '00000000-0000-0000-0000-0000000000fc';
BEGIN
  INSERT INTO public.organizations (id, nome, slug, is_platform) VALUES
    (v_a, 'A', 'noc-s4b-a', false),
    (v_b, 'B', 'noc-s4b-b', false), (v_c, 'C', 'noc-s4b-c', false);
  INSERT INTO auth.users (id, email) VALUES
    ('00000000-0000-0000-0000-0000000000e1', 'noc_owner@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e2', 'noc_admin@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e3', 'owner_a@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e4', 'admin_ab@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e5', 'admin_a@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e6', 'mem@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e7', 'solo@s4b.test'),
    ('00000000-0000-0000-0000-0000000000e8', 'newbie@s4b.test');
  INSERT INTO public.noctus_users (id, email, nome, org_id, org_role, role) VALUES
    ('00000000-0000-0000-0000-0000000000e1', 'noc_owner@s4b.test', 'Noc Owner', v_p, 'owner', 'admin'),
    ('00000000-0000-0000-0000-0000000000e2', 'noc_admin@s4b.test', 'Noc Admin', v_p, 'admin', 'admin'),
    ('00000000-0000-0000-0000-0000000000e3', 'owner_a@s4b.test', 'Owner A', v_a, 'owner', 'user'),
    ('00000000-0000-0000-0000-0000000000e4', 'admin_ab@s4b.test', 'Admin AB', v_a, 'admin', 'user'),
    ('00000000-0000-0000-0000-0000000000e5', 'admin_a@s4b.test', 'Admin A', v_a, 'admin', 'user'),
    ('00000000-0000-0000-0000-0000000000e6', 'mem@s4b.test', 'Mem', v_a, 'member', 'user'),
    ('00000000-0000-0000-0000-0000000000e7', 'solo@s4b.test', 'Solo', v_c, 'member', 'user');
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES ('00000000-0000-0000-0000-0000000000e4', v_b, 'admin', 'active');
END $$;
"""

_DECLARE = """
DECLARE
  -- the platform org of the picker fixture (a NEW is_platform org would fan licences out to every
  -- product by the core 068 trigger, which this chain cannot satisfy)
  v_p uuid := (SELECT o.id FROM public.organizations o WHERE o.slug = 'noc-probe-plat');
  v_a uuid := '00000000-0000-0000-0000-0000000000fa';
  v_b uuid := '00000000-0000-0000-0000-0000000000fb';
  v_c uuid := '00000000-0000-0000-0000-0000000000fc';
  u_noc_owner uuid := '00000000-0000-0000-0000-0000000000e1';
  u_noc_admin uuid := '00000000-0000-0000-0000-0000000000e2';
  u_owner_a   uuid := '00000000-0000-0000-0000-0000000000e3';
  u_admin_ab  uuid := '00000000-0000-0000-0000-0000000000e4';
  u_admin_a   uuid := '00000000-0000-0000-0000-0000000000e5';
  u_mem       uuid := '00000000-0000-0000-0000-0000000000e6';
  u_solo      uuid := '00000000-0000-0000-0000-0000000000e7';
  u_newbie    uuid := '00000000-0000-0000-0000-0000000000e8';
  v_org uuid; v_role text; v_n integer; v_inv uuid; v_res jsonb; v_pid uuid; v_slug text; v_personal uuid;
"""

_OK = "  RAISE EXCEPTION 'NOC_PROBE:clean: ok';\n"


def _scenario(name: str, body: str) -> dict:
    sql = vdg._do_block(_DECLARE + "BEGIN\n" + body + "\nEND;\n")
    return {"product": "core", "file": name, "sql": vdg.wrap_rollback_only(sql), "mode": "file", "twice": False}


def _refused(call: str, code: str) -> str:
    return f"""
  BEGIN
    {call}
    RAISE EXCEPTION 'NOC_PROBE:violation: succeeded, expected team_membership:{code}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:violation:%' THEN RAISE; END IF;
    IF SQLERRM NOT LIKE 'team_membership:{code}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:violation: expected team_membership:{code}, got: %', SQLERRM;
    END IF;
  END;
"""


def _personal(user: str) -> str:
    return f"""
  INSERT INTO public.organizations (nome, slug, owner_id, is_personal)
  VALUES ('Pessoal', 'indv_s4b-' || gen_random_uuid()::text, {user}, true) RETURNING id INTO v_personal;
"""


_PRODUCT = """
  SELECT p.id, p.slug INTO v_pid, v_slug FROM public.products p WHERE p.db_schema IS NOT NULL ORDER BY p.slug LIMIT 1;
  INSERT INTO public.licenses (org_id, product_id, status) VALUES (v_a, v_pid, 'active');
"""

_SCENARIOS = {
    # ---- D2 ---------------------------------------------------------------------------------------
    "d2_last_owner_override_is_the_noctusai_owner_only_remove": """
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status) VALUES (u_owner_a, v_b, 'member', 'active');
""" + _refused("PERFORM public.team_member_remove(v_a, u_owner_a, u_noc_admin, NULL::uuid);", "last_owner")
        + _refused("PERFORM public.team_member_remove(v_a, u_owner_a, u_admin_ab, NULL::uuid);", "last_owner")
        + _refused("PERFORM public.team_member_remove(v_a, u_owner_a);", "last_owner") + """
  PERFORM public.team_member_remove(v_a, u_owner_a, u_noc_owner, NULL::uuid);
  SET CONSTRAINTS ALL IMMEDIATE;
  IF (SELECT org_id FROM public.noctus_users WHERE id = u_owner_a) IS DISTINCT FROM v_b THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile did not move to B';
  END IF;
""" + _OK,
    "d2_last_owner_override_is_the_noctusai_owner_only_demote": _refused(
        "PERFORM public.team_member_set_role(v_a, u_owner_a, 'member', u_noc_admin);", "last_owner") + """
  PERFORM public.team_member_set_role(v_a, u_owner_a, 'member', u_noc_owner);
  SET CONSTRAINTS ALL IMMEDIATE;
  IF (SELECT org_role FROM public.org_memberships WHERE user_id = u_owner_a AND org_id = v_a) <> 'member' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: not demoted';
  END IF;
""" + _OK,
    "d2_staff_role_helpers": """
  IF public.platform_staff_role(u_noc_owner) IS DISTINCT FROM 'owner'
     OR public.platform_staff_role(u_noc_admin) IS DISTINCT FROM 'admin'
     OR public.platform_staff_role(u_owner_a) IS NOT NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: platform_staff_role wrong';
  END IF;
  IF public.org_manager_role(u_noc_admin, v_c) IS DISTINCT FROM 'owner'
     OR public.org_manager_role(u_admin_ab, v_b) IS DISTINCT FROM 'admin'
     OR public.org_manager_role(u_admin_a, v_b) IS NOT NULL
     OR public.org_manager_role(u_mem, v_a) IS NOT NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: org_manager_role wrong';
  END IF;
  -- the superadmin FLAG outside the platform org is not staff
  UPDATE public.organizations SET is_platform = false WHERE id = v_p;
  IF public.platform_staff_role(u_noc_owner) IS NOT NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: staff without an is_platform home';
  END IF;
""" + _OK,
    # ---- D3 ---------------------------------------------------------------------------------------
    "d3_org_admin_of_a_only_cannot_move_into_b": _refused(
        "PERFORM public.team_member_move(u_admin_a, u_mem, v_a, v_b, 'member', 'add');", "forbidden")
        + _refused("PERFORM public.team_member_move(u_mem, u_mem, v_a, v_b, 'member', 'add');", "forbidden") + _OK,
    "d3_admin_of_both_moves_with_transfer": """
  v_res := public.team_member_move(u_admin_ab, u_mem, v_a, v_b, 'viewer', 'transfer');
  SET CONSTRAINTS ALL IMMEDIATE;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_mem AND org_id = v_a AND status = 'removed')
     OR NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_mem AND org_id = v_b
                     AND status = 'active' AND org_role = 'viewer' AND invited_by = u_admin_ab) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: memberships wrong after transfer %', v_res;
  END IF;
  SELECT org_id, org_role INTO v_org, v_role FROM public.noctus_users WHERE id = u_mem;
  IF v_org IS DISTINCT FROM v_b OR v_role IS DISTINCT FROM 'viewer' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile is %/% not B/viewer', v_org, v_role;
  END IF;
""" + _OK,
    "d3_admin_of_both_moves_with_add": """
  PERFORM public.team_member_move(u_admin_ab, u_mem, v_a, v_b, 'member', 'add');
  SET CONSTRAINTS ALL IMMEDIATE;
  SELECT count(*) INTO v_n FROM public.org_memberships WHERE user_id = u_mem AND status = 'active' AND org_id IN (v_a, v_b);
  IF v_n <> 2 OR (SELECT org_id FROM public.noctus_users WHERE id = u_mem) <> v_a THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: add ended the source or moved the profile';
  END IF;
""" + _refused("PERFORM public.team_member_move(u_admin_ab, u_mem, v_a, v_b, 'member', 'add');", "already_member") + _OK,
    "d3_role_never_above_the_actor_in_the_target": _refused(
        "PERFORM public.team_member_move(u_admin_ab, u_mem, v_a, v_b, 'owner', 'add');", "role_above_actor") + """
  -- staff act as owner anywhere: an owner role is allowed for them
  PERFORM public.team_member_move(u_noc_admin, u_mem, v_a, v_c, 'owner', 'add');
""" + _OK,
    "d3_transfer_of_the_last_owner_needs_the_noctusai_owner": """
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status) VALUES (u_admin_ab, v_c, 'owner', 'active');
""" + _refused("PERFORM public.team_member_move(u_noc_admin, u_owner_a, v_a, v_c, 'member', 'transfer');", "last_owner") + """
  PERFORM public.team_member_move(u_noc_owner, u_owner_a, v_a, v_c, 'member', 'transfer');
  SET CONSTRAINTS ALL IMMEDIATE;
""" + _OK,
    "d3_mode_and_orgs_are_validated": _refused(
        "PERFORM public.team_member_move(u_noc_owner, u_mem, v_a, v_b, 'member', 'copy');", "invalid_mode")
        + _refused("PERFORM public.team_member_move(u_noc_owner, u_mem, v_a, v_a, 'member', 'add');", "same_org")
        + _refused("PERFORM public.team_member_move(u_noc_owner, u_mem, v_c, v_b, 'member', 'add');", "not_a_member") + _OK,
    # ---- D4 ---------------------------------------------------------------------------------------
    "d4_sole_member_removal_keeps_the_profile_in_a_personal_org": _personal("u_solo") + """
  v_res := public.team_member_remove(v_c, u_solo, u_noc_admin, v_personal);
  SET CONSTRAINTS ALL IMMEDIATE;
  SELECT org_id, org_role INTO v_org, v_role FROM public.noctus_users WHERE id = u_solo;
  IF v_org IS DISTINCT FROM v_personal OR v_role IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile is %/%', v_org, v_role;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_solo AND org_id = v_personal
                  AND status = 'active' AND org_role = 'owner')
     OR NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_solo AND org_id = v_c AND status = 'removed') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: memberships wrong';
  END IF;
  IF (v_res ->> 'personal_org_id')::uuid IS DISTINCT FROM v_personal OR (v_res ->> 'profile_deleted')::boolean THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: bad result %', v_res;
  END IF;
""" + _OK,
    "d4_profile_with_audit_rows_is_kept": _personal("u_solo") + """
  INSERT INTO public.invitations (org_id, email, role, invited_by, token)
  VALUES (v_c, 'x@s4b.test', 'member', u_solo, 'noc-s4b-' || gen_random_uuid()::text);
  PERFORM public.team_member_remove(v_c, u_solo, NULL::uuid, v_personal);
  SET CONSTRAINTS ALL IMMEDIATE;
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users WHERE id = u_solo) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile gone';
  END IF;
""" + _OK,
    "d4_personal_org_is_validated": """
  INSERT INTO public.organizations (nome, slug, owner_id, is_personal)
  VALUES ('Nope', 'noc-s4b-' || gen_random_uuid()::text, u_mem, true) RETURNING id INTO v_personal;
""" + _refused("PERFORM public.team_member_remove(v_c, u_solo, NULL::uuid, v_personal);", "personal_org_invalid")
        + _refused("PERFORM public.team_member_remove(v_c, u_solo, NULL::uuid, v_a);", "personal_org_invalid")
        + _refused("PERFORM public.team_member_remove(v_c, u_solo, NULL::uuid, NULL::uuid);", "personal_org_required")
        + _OK,
    "d4_first_time_invitee_gets_profile_and_linked_membership": """
  INSERT INTO public.invitations (org_id, email, role, invited_by, token)
  VALUES (v_a, 'newbie@s4b.test', 'manager', u_owner_a, 'noc-s4b-' || gen_random_uuid()::text)
  RETURNING id INTO v_inv;
  v_res := public.team_invitation_accept(v_inv, u_newbie, 'Newbie');
  SET CONSTRAINTS ALL IMMEDIATE;
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users WHERE id = u_newbie AND org_id = v_a AND org_role = 'manager' AND nome = 'Newbie') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_newbie AND org_id = v_a AND status = 'active'
                  AND invited_by = u_owner_a AND invitation_id = v_inv) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: membership not linked';
  END IF;
  IF (SELECT status FROM public.invitations WHERE id = v_inv) <> 'accepted' OR NOT (v_res ->> 'new_user')::boolean THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: invitation/result wrong %', v_res;
  END IF;
""" + _OK,
    # ---- D5 ---------------------------------------------------------------------------------------
    "d5_block_unblock_history_and_authority": _PRODUCT + _refused(
        "PERFORM public.org_member_product_access_set(u_mem, v_a, u_admin_a, v_slug, true);", "forbidden")
        + _refused("PERFORM public.org_member_product_access_set(u_admin_ab, v_b, u_mem, v_slug, true);", "not_a_member")
        + _refused("PERFORM public.org_member_product_access_set(u_admin_a, v_a, u_mem, 'no-such-product', true);",
                   "product_not_found") + """
  INSERT INTO auth.sessions (id, user_id) VALUES ('00000000-0000-0000-0000-00000000d5d5', u_mem)
  ON CONFLICT (id) DO NOTHING;
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (u_mem, v_pid, v_a, v_a, '00000000-0000-0000-0000-00000000d5d5');
  v_res := public.org_member_product_access_set(u_admin_a, v_a, u_mem, v_slug, true);
  IF NOT (v_res ->> 'changed')::boolean THEN RAISE EXCEPTION 'NOC_PROBE:violation: block not applied'; END IF;
  v_res := public.org_member_product_access_set(u_admin_a, v_a, u_mem, v_slug, true);
  IF (v_res ->> 'changed')::boolean THEN RAISE EXCEPTION 'NOC_PROBE:violation: block not idempotent'; END IF;
  IF EXISTS (SELECT 1 FROM public.platform_org_selections WHERE user_id = u_mem AND ended_at IS NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: live selection of the blocked org survived';
  END IF;
  PERFORM public.org_member_product_access_set(u_noc_admin, v_a, u_mem, v_slug, false);
  PERFORM public.org_member_product_access_set(u_admin_a, v_a, u_mem, v_slug, true);
  SELECT count(*) INTO v_n FROM public.org_member_product_access WHERE user_id = u_mem AND org_id = v_a;
  IF v_n <> 2 OR (SELECT count(*) FROM public.org_member_product_access
                   WHERE user_id = u_mem AND unblocked_at IS NULL) <> 1
     OR NOT EXISTS (SELECT 1 FROM public.org_member_product_access WHERE user_id = u_mem
                     AND unblocked_by = u_noc_admin AND unblocked_at IS NOT NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: history wrong (% rows)', v_n;
  END IF;
""" + _OK,
    "d5_block_needs_a_license": _refused(
        "PERFORM public.org_member_product_access_set(u_admin_ab, v_b, u_admin_ab, "
        "(SELECT p.slug FROM public.products p WHERE p.db_schema IS NOT NULL ORDER BY p.slug LIMIT 1), true);",
        "not_licensed") + _OK,
    "new_functions_are_service_role_only": """
  SELECT count(*) INTO v_n FROM information_schema.routine_privileges
   WHERE routine_schema = 'public'
     AND routine_name IN ('platform_staff_role', 'org_manager_role', 'org_member_product_access_set',
                          'team_member_move', 'team_member_remove', 'team_member_set_role', 'team_invitation_accept')
     AND grantee IN ('PUBLIC', 'anon', 'authenticated');
  IF v_n <> 0 THEN RAISE EXCEPTION 'NOC_PROBE:violation: % grant(s) to PUBLIC/anon/authenticated', v_n; END IF;
  SELECT count(DISTINCT routine_name) INTO v_n FROM information_schema.routine_privileges
   WHERE routine_schema = 'public' AND grantee = 'service_role'
     AND routine_name IN ('platform_staff_role', 'org_manager_role', 'org_member_product_access_set', 'team_member_move');
  IF v_n <> 4 THEN RAISE EXCEPTION 'NOC_PROBE:violation: service_role can execute % of the 4 new functions', v_n; END IF;
""" + _OK,
}


def _run(overrides: dict[str, str]) -> dict[str, str]:
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", overrides)
    steps.append({"product": "core", "file": _PICKER_FIXTURE, "sql": _PICKER_FIXTURE_SQL, "mode": "file", "twice": False})
    steps.append({"product": "core", "file": _FIXTURE, "sql": _FIXTURE_SQL, "mode": "file", "twice": False})
    names = set()
    for pid, probe in _PROBES.items():
        steps.append({"product": "core", "file": pid, "sql": vdg.wrap_rollback_only(probe.sql),
                      "mode": "file", "twice": False})
        names.add(pid)
    for name, body in _SCENARIOS.items():
        steps.append(_scenario(name, body))
        names.add(name)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] in (_FIXTURE, _PICKER_FIXTURE):
            assert not st["failures"], st["failures"]
        elif st["file"] in names:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    return out


def test_probes_are_registered_and_declare_083():
    assert len(_PROBES) >= 6
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    for pid in _PROBES:
        assert "083_member_access_rules.sql" in by_id[pid].migrations, pid


def test_every_scenario_and_probe_holds_with_083(pglite):
    out = _run({})
    assert set(out) == set(_PROBES) | set(_SCENARIOS)
    assert {k: v for k, v in out.items() if v not in _PASS} == {}


def test_without_083_the_probes_and_scenarios_fail(pglite):
    out = _run({_M083: "SELECT 1;\n"})
    assert {k for k, v in out.items() if v in _PASS} == set(), out
