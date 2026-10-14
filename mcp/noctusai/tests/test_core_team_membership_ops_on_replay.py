"""Core ``team_membership_ops`` (multi-org S4) on the REAL core chain on PGlite, triggers ON.

The three functions are the transactional half of the team router: remove-member, change-role and
accept-invitation as MEMBERSHIP operations. What this proves on a real Postgres (the router tests
mock the RPC):

* the registered ``team_*`` GuardProbes are clean with 082 applied and fail without it;
* remove from the profile org MOVES the profile to the most recently updated other ACTIVE membership
  (org_id + that membership's role), a sole membership DELETES the profile, a non-profile org leaves
  the profile alone -- and the 081 deferred invariant trigger is fired IMMEDIATE after each, so it is
  the same judgement COMMIT makes;
* the last owner can be neither removed nor demoted; the profile mirror takes a role change only for
  its own org;
* an EXISTING user accepting an invitation gets an ACTIVE membership (invited_by/invitation_id
  linked, invitation accepted) while the profile stays put; replay, active member, suspended and
  email-mismatch are refused; a removed membership is re-activated (ended_at cleared).
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path
from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_MIGRATIONS = Path(REPO_ROOT) / "products/core/backend/migrations"
_M082 = str(migration_path(_MIGRATIONS, "team_membership_ops").relative_to(REPO_ROOT))
#: Core 083 (S4b) re-declares the three functions (the 082 signatures become wrappers): the
#: "without 082" run drops it too.
_M083 = str(migration_path(_MIGRATIONS, "member_access_rules").relative_to(REPO_ROOT))
_SENT = re.compile(r"NOC_PROBE:(\w+):")
_FIXTURE = "core-082-team-fixture"

_PROBES = {p.id: p for p in vdg._TEAM_OPS_PROBES}
_PASS = ("clean", "refused")

# Three orgs; owner_a is the only owner of A; multi has profile A (member) + membership B (viewer);
# solo has profile C only. Triggers are ON: the 079 sync trigger creates each profile's membership.
_FIXTURE_SQL = """
CREATE TABLE IF NOT EXISTS auth.sessions (id uuid PRIMARY KEY, user_id uuid);
DO $$
DECLARE
  v_a uuid := '00000000-0000-0000-0000-00000000000a';
  v_b uuid := '00000000-0000-0000-0000-00000000000b';
  v_c uuid := '00000000-0000-0000-0000-00000000000c';
BEGIN
  INSERT INTO public.organizations (id, nome, slug, is_platform) VALUES
    (v_a, 'A', 'noc-t-a', false), (v_b, 'B', 'noc-t-b', false), (v_c, 'C', 'noc-t-c', false);
  INSERT INTO auth.users (id, email) VALUES
    ('00000000-0000-0000-0000-0000000000a1', 'owner_a@t.test'),
    ('00000000-0000-0000-0000-0000000000a2', 'multi@t.test'),
    ('00000000-0000-0000-0000-0000000000a3', 'solo@t.test'),
    ('00000000-0000-0000-0000-0000000000a4', 'second_owner_b@t.test');
  INSERT INTO public.noctus_users (id, email, nome, org_id, org_role, role) VALUES
    ('00000000-0000-0000-0000-0000000000a1', 'owner_a@t.test', 'Owner A', v_a, 'owner', 'user'),
    ('00000000-0000-0000-0000-0000000000a2', 'multi@t.test', 'Multi', v_a, 'member', 'user'),
    ('00000000-0000-0000-0000-0000000000a3', 'solo@t.test', 'Solo', v_c, 'member', 'user'),
    ('00000000-0000-0000-0000-0000000000a4', 'second_owner_b@t.test', 'Owner B', v_b, 'owner', 'user');
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES ('00000000-0000-0000-0000-0000000000a2', v_b, 'viewer', 'active');
END $$;
"""

_DECLARE = """
DECLARE
  v_a uuid := '00000000-0000-0000-0000-00000000000a';
  v_b uuid := '00000000-0000-0000-0000-00000000000b';
  v_c uuid := '00000000-0000-0000-0000-00000000000c';
  u_owner_a uuid := '00000000-0000-0000-0000-0000000000a1';
  u_multi   uuid := '00000000-0000-0000-0000-0000000000a2';
  u_solo    uuid := '00000000-0000-0000-0000-0000000000a3';
  u_owner_b uuid := '00000000-0000-0000-0000-0000000000a4';
  v_org uuid; v_role text; v_n integer; v_inv uuid; v_res jsonb; v_msg text; v_st text;
"""


def _scenario(name: str, body: str) -> dict:
    sql = vdg._do_block(_DECLARE + "BEGIN\n" + body + "\nEND;\n")
    return {"product": "core", "file": name, "sql": vdg.wrap_rollback_only(sql), "mode": "file", "twice": False}


def _expect_refusal(call: str, code: str) -> str:
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


def _invite(inv_var_email: str, org: str, role: str, by: str = "u_owner_a") -> str:
    return f"""
  INSERT INTO public.invitations (org_id, email, role, invited_by, token)
  VALUES ({org}, '{inv_var_email}', '{role}', {by}, 'noc-t-' || gen_random_uuid()::text)
  RETURNING id INTO v_inv;
"""


_OK = "  RAISE EXCEPTION 'NOC_PROBE:clean: ok';\n"

_SCENARIOS = {
    "remove_profile_org_moves_the_profile": """
  v_res := public.team_member_remove(v_a, u_multi);
  SET CONSTRAINTS ALL IMMEDIATE;
  SELECT n.org_id, n.org_role INTO v_org, v_role FROM public.noctus_users n WHERE n.id = u_multi;
  IF v_org IS DISTINCT FROM v_b OR v_role IS DISTINCT FROM 'viewer' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile is %/% not B/viewer', v_org, v_role;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_a
                  AND status = 'removed' AND ended_at IS NOT NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: membership A not ended';
  END IF;
  IF (v_res ->> 'profile_moved_to')::uuid IS DISTINCT FROM v_b OR (v_res ->> 'profile_deleted')::boolean THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: bad result %', v_res;
  END IF;
""" + _OK,
    "remove_other_org_leaves_the_profile": """
  PERFORM public.team_member_remove(v_b, u_multi);
  SET CONSTRAINTS ALL IMMEDIATE;
  SELECT n.org_id, n.org_role INTO v_org, v_role FROM public.noctus_users n WHERE n.id = u_multi;
  IF v_org IS DISTINCT FROM v_a OR v_role IS DISTINCT FROM 'member' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile moved to %/%', v_org, v_role;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_b AND status = 'removed') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: membership B not ended';
  END IF;
""" + _OK,
    # Core 083 (owner D4, 2026-10-14) superseded "delete the profile": the 082 signature now refuses
    # a sole membership (no personal org given) and the profile stays -- see the 083 replay test.
    "remove_sole_membership_never_deletes_the_profile": _expect_refusal(
        "PERFORM public.team_member_remove(v_c, u_solo);", "personal_org_required") + """
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users WHERE id = u_solo AND org_id = v_c) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile gone or moved';
  END IF;
""" + _OK,
    "remove_ends_live_org_selections_for_the_org": """
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  SELECT u_multi, p.id, v_b, v_a, gen_random_uuid() FROM public.products p LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'NOC_PROBE:no_fixture: no product row'; END IF;
  PERFORM public.team_member_remove(v_b, u_multi);
  SELECT count(*) INTO v_n FROM public.platform_org_selections WHERE user_id = u_multi AND ended_at IS NULL;
  IF v_n <> 0 THEN RAISE EXCEPTION 'NOC_PROBE:violation: % live selection(s) survive', v_n; END IF;
""" + _OK,
    "remove_non_member_is_refused": _expect_refusal("PERFORM public.team_member_remove(v_c, u_multi);", "not_a_member") + _OK,
    "remove_last_owner_is_refused": _expect_refusal("PERFORM public.team_member_remove(v_a, u_owner_a);", "last_owner") + _OK,
    "remove_an_owner_is_allowed_when_another_owner_remains": """
  UPDATE public.org_memberships SET org_role = 'owner' WHERE user_id = u_multi AND org_id = v_a;
  -- owner_a also belongs to B, so the profile moves there (a sole membership needs a personal org, D4)
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status) VALUES (u_owner_a, v_b, 'member', 'active');
  PERFORM public.team_member_remove(v_a, u_owner_a);
  SET CONSTRAINTS ALL IMMEDIATE;
""" + _OK,
    "set_role_updates_membership_and_the_profile_mirror_for_the_profile_org": """
  PERFORM public.team_member_set_role(v_a, u_multi, 'manager');
  SET CONSTRAINTS ALL IMMEDIATE;
  IF (SELECT org_role FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_a) <> 'manager'
     OR (SELECT org_role FROM public.noctus_users WHERE id = u_multi) <> 'manager' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: membership/profile role not manager';
  END IF;
""" + _OK,
    "set_role_in_another_org_never_leaks_into_the_profile": """
  PERFORM public.team_member_set_role(v_b, u_multi, 'manager');
  IF (SELECT org_role FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_b) <> 'manager' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: membership B role not manager';
  END IF;
  IF (SELECT org_role FROM public.noctus_users WHERE id = u_multi) <> 'member' OR
     (SELECT org_id FROM public.noctus_users WHERE id = u_multi) <> v_a THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile was touched';
  END IF;
""" + _OK,
    "set_role_demoting_the_last_owner_is_refused": _expect_refusal(
        "PERFORM public.team_member_set_role(v_a, u_owner_a, 'member');", "last_owner") + _OK,
    "accept_adds_a_membership_and_leaves_the_profile_alone": _invite("multi@t.test", "v_c", "manager") + """
  v_res := public.team_invitation_accept(v_inv, u_multi);
  SET CONSTRAINTS ALL IMMEDIATE;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_c
                  AND status = 'active' AND org_role = 'manager' AND invited_by = u_owner_a AND invitation_id = v_inv) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: membership C missing/not linked';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_a AND status = 'active')
     OR NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_b AND status = 'active') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: an existing membership was disturbed';
  END IF;
  IF (SELECT org_id FROM public.noctus_users WHERE id = u_multi) <> v_a THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: profile moved';
  END IF;
  IF (SELECT status FROM public.invitations WHERE id = v_inv) <> 'accepted' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: invitation not accepted';
  END IF;
""" + _expect_refusal("PERFORM public.team_invitation_accept(v_inv, u_multi);", "invitation_not_pending") + _OK,
    "accept_into_an_org_already_active_is_refused": _invite("multi@t.test", "v_b", "admin") + _expect_refusal(
        "PERFORM public.team_invitation_accept(v_inv, u_multi);", "already_member") + """
  IF (SELECT org_role FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_b) <> 'viewer' THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: the active membership was re-roled';
  END IF;
""" + _OK,
    "accept_reactivates_a_removed_membership": """
  PERFORM public.team_member_remove(v_b, u_multi);
""" + _invite("multi@t.test", "v_b", "admin") + """
  PERFORM public.team_invitation_accept(v_inv, u_multi);
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships WHERE user_id = u_multi AND org_id = v_b
                  AND status = 'active' AND ended_at IS NULL AND org_role = 'admin' AND invitation_id = v_inv) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: removed membership not re-activated cleanly';
  END IF;
""" + _OK,
    "accept_does_not_lift_a_suspension": """
  UPDATE public.org_memberships SET status = 'suspended' WHERE user_id = u_multi AND org_id = v_b;
""" + _invite("multi@t.test", "v_b", "admin") + _expect_refusal(
        "PERFORM public.team_invitation_accept(v_inv, u_multi);", "membership_suspended") + _OK,
    "accept_by_another_email_is_refused": _invite("someone_else@t.test", "v_c", "member") + _expect_refusal(
        "PERFORM public.team_invitation_accept(v_inv, u_multi);", "email_mismatch") + _OK,
    "accept_expired_invitation_is_refused": _invite("multi@t.test", "v_c", "member") + """
  UPDATE public.invitations SET expires_at = now() - interval '1 day' WHERE id = v_inv;
""" + _expect_refusal("PERFORM public.team_invitation_accept(v_inv, u_multi);", "invitation_expired") + _OK,
    "the_three_functions_are_service_role_only": """
  SELECT count(*) INTO v_n FROM information_schema.routine_privileges
   WHERE routine_schema = 'public'
     AND routine_name IN ('team_member_remove', 'team_member_set_role', 'team_invitation_accept')
     AND grantee IN ('PUBLIC', 'anon', 'authenticated');
  IF v_n <> 0 THEN RAISE EXCEPTION 'NOC_PROBE:violation: % grant(s) to PUBLIC/anon/authenticated', v_n; END IF;
  SELECT count(DISTINCT routine_name) INTO v_n FROM information_schema.routine_privileges
   WHERE routine_schema = 'public' AND grantee = 'service_role'
     AND routine_name IN ('team_member_remove', 'team_member_set_role', 'team_invitation_accept');
  IF v_n <> 3 THEN RAISE EXCEPTION 'NOC_PROBE:violation: service_role can execute % of 3', v_n; END IF;
""" + _OK,
}


def _run(overrides: dict[str, str]) -> dict[str, str]:
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", overrides)
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
        if st["file"] == _FIXTURE:
            assert not st["failures"], st["failures"]
        elif st["file"] in names:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    return out


def test_probes_are_registered_and_declare_082():
    assert len(_PROBES) == 4
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    for pid in _PROBES:
        assert "082_team_membership_ops.sql" in by_id[pid].migrations, pid


def test_every_scenario_and_probe_holds_with_082(pglite):
    out = _run({})
    assert set(out) == set(_PROBES) | set(_SCENARIOS)
    assert {k: v for k, v in out.items() if v not in _PASS} == {}


def test_without_082_the_probes_and_scenarios_fail(pglite):
    out = _run({_M082: "SELECT 1;\n", _M083: "SELECT 1;\n"})
    assert {k for k, v in out.items() if v in _PASS} == set(), out
