"""Core ``owner_grant_and_block_rules`` (multi-org S5b, owner decisions P1-P5 2026-10-14) on the REAL
core chain on PGlite, triggers ON.

What this proves on a real Postgres (the router tests mock the RPCs):

* every registered 084 GuardProbe (``vdg._OWNER_GRANT_RULES_PROBES``) is refused with 084 and is NOT
  without it;
* P1: granting ``owner`` -- role change (4-arg and the 3-arg wrapper) and move target role -- is
  refused ``owner_grant_forbidden`` for an org owner; platform staff may;
* P2: a D5 block survives the member's removal and re-invite (unchanged behaviour, pinned);
* P3: NoctusAI staff can never be blocked (``cannot_block_staff``), even by the NoctusAI owner;
  unblocking an old row stays possible;
* P5: block/unblock only by the org's OWNER or staff -- an org ADMIN is ``forbidden``.

Same fixture and scenario harness as ``test_core_member_access_rules_on_replay.py``.
"""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_path
from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

from tests.test_core_078_probes_on_replay import _FIXTURE_SQL as _PICKER_FIXTURE_SQL
from tests.test_core_member_access_rules_on_replay import (
    _FIXTURE_SQL, _OK, _PRODUCT, _SENT, _personal, _refused, _scenario,
)

_MIGRATIONS = Path(REPO_ROOT) / "products/core/backend/migrations"
_M084 = str(migration_path(_MIGRATIONS, "owner_grant_and_block_rules").relative_to(REPO_ROOT))
_PICKER_FIXTURE = "core-084-picker-fixture"
_FIXTURE = "core-084-team-fixture"

_PROBES = {p.id: p for p in vdg._OWNER_GRANT_RULES_PROBES}

_SCENARIOS = {
    # ---- P1 ---------------------------------------------------------------------------------------
    "p1_org_owner_cannot_grant_owner_by_role_change": _refused(
        "PERFORM public.team_member_set_role(v_a, u_mem, 'owner', u_owner_a);", "owner_grant_forbidden")
        + _refused("PERFORM public.team_member_set_role(v_a, u_mem, 'owner');", "owner_grant_forbidden") + """
  -- re-stating an EXISTING owner's role is not a grant
  PERFORM public.team_member_set_role(v_a, u_owner_a, 'owner', u_owner_a);
  PERFORM public.team_member_set_role(v_a, u_mem, 'owner', u_noc_admin);
  SET CONSTRAINTS ALL IMMEDIATE;
  IF (SELECT org_role FROM public.org_memberships WHERE user_id = u_mem AND org_id = v_a) <> 'owner' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: staff could not grant owner';
  END IF;
""" + _OK,
    "p1_move_target_owner_is_staff_only": """
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status) VALUES (u_owner_a, v_b, 'owner', 'active');
""" + _refused("PERFORM public.team_member_move(u_owner_a, u_mem, v_a, v_b, 'owner', 'add');", "owner_grant_forbidden")
        + """
  PERFORM public.team_member_move(u_owner_a, u_mem, v_a, v_b, 'admin', 'add');
  PERFORM public.team_member_move(u_noc_owner, u_solo, v_c, v_b, 'owner', 'add');
  SET CONSTRAINTS ALL IMMEDIATE;
  IF (SELECT org_role FROM public.org_memberships WHERE user_id = u_solo AND org_id = v_b) <> 'owner' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: staff could not move with owner';
  END IF;
""" + _OK,
    # ---- P2 ---------------------------------------------------------------------------------------
    "p2_block_survives_removal_and_reinvite": _PRODUCT + _personal("u_mem") + """
  PERFORM public.org_member_product_access_set(u_owner_a, v_a, u_mem, v_slug, true);
  PERFORM public.team_member_remove(v_a, u_mem, u_owner_a, v_personal);
  SET CONSTRAINTS ALL IMMEDIATE;
  INSERT INTO public.invitations (org_id, email, role, invited_by, token)
  VALUES (v_a, 'mem@s4b.test', 'member', u_owner_a, 'noc-s5b-' || gen_random_uuid()::text)
  RETURNING id INTO v_inv;
  PERFORM public.team_invitation_accept(v_inv, u_mem, 'Mem');
  SET CONSTRAINTS ALL IMMEDIATE;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_mem AND org_id = v_a AND status = 'active') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: re-invite did not reactivate the membership';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_member_product_access
                  WHERE user_id = u_mem AND org_id = v_a AND product_id = v_pid AND unblocked_at IS NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: the block did not survive removal + re-invite';
  END IF;
""" + _OK,
    # ---- P3 ---------------------------------------------------------------------------------------
    "p3_staff_are_never_blocked": _PRODUCT + """
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status) VALUES (u_noc_admin, v_a, 'member', 'active');
""" + _refused("PERFORM public.org_member_product_access_set(u_noc_owner, v_a, u_noc_admin, v_slug, true);",
               "cannot_block_staff")
        + _refused("PERFORM public.org_member_product_access_set(u_owner_a, v_a, u_noc_admin, v_slug, true);",
                   "cannot_block_staff") + """
  -- an unblock is always allowed (closes any block written before 084)
  PERFORM public.org_member_product_access_set(u_owner_a, v_a, u_noc_admin, v_slug, false);
""" + _OK,
    # ---- P5 ---------------------------------------------------------------------------------------
    "p5_only_the_org_owner_or_staff_block": _PRODUCT
        + _refused("PERFORM public.org_member_product_access_set(u_admin_a, v_a, u_mem, v_slug, true);", "forbidden")
        + _refused("PERFORM public.org_member_product_access_set(u_admin_a, v_a, u_mem, v_slug, false);", "forbidden")
        + """
  v_res := public.org_member_product_access_set(u_owner_a, v_a, u_mem, v_slug, true);
  IF NOT (v_res ->> 'changed')::boolean THEN RAISE EXCEPTION 'NOC_PROBE:violation: owner could not block'; END IF;
  v_res := public.org_member_product_access_set(u_noc_admin, v_a, u_mem, v_slug, false);
  IF NOT (v_res ->> 'changed')::boolean THEN RAISE EXCEPTION 'NOC_PROBE:violation: staff could not unblock'; END IF;
""" + _OK,
}

_PASS = ("clean", "refused")


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


def test_probes_are_registered_and_declare_084():
    assert len(_PROBES) == 4
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    for pid in _PROBES:
        assert "084_owner_grant_and_block_rules.sql" in by_id[pid].migrations, pid


def test_every_scenario_and_probe_holds_with_084(pglite):
    out = _run({})
    assert set(out) == set(_PROBES) | set(_SCENARIOS)
    assert {k: v for k, v in out.items() if v not in _PASS} == {}


def test_without_084_the_probes_and_p1_p3_p5_scenarios_fail(pglite):
    out = _run({_M084: "SELECT 1;\n"})
    # P2 is unchanged behaviour (083): it holds either way -- that is the point of pinning it.
    assert out.pop("p2_block_survives_removal_and_reinvite") in _PASS
    assert {k for k, v in out.items() if v in _PASS} == set(), out
