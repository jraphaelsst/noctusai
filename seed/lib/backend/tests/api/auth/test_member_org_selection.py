"""Multi-org S2: a regular MEMBER of several orgs selects the org they act in through the
EXISTING platform org picker (owner decisions 2026-10-13, roadmap multi-org-membership-2026-10).

Pins the semantics the SQL half (core ``org_member_selection``) mirrors:

* the ROLE is the membership role in the EFFECTIVE org, never the home profile role
  (owner in A + viewer in B is a viewer in B -- the privilege-leak guard);
* a selection resolves only while the membership is ACTIVE, re-read every request;
* no aal2 for members (Q1); the profile follows the pick with the membership role (Q3);
* D1 (owner, 2026-10-14, replaces Q2): with >=2 ELIGIBLE orgs (active, non-customer, licensed,
  not blocked) and no valid selection every gated path answers 409 org_selection_required;
  exactly one eligible org is landed in silently; none -> the home org (license gate judges);
* D5: an org where the user is blocked from the product is never eligible, never honoured as a
  selection, never served as home (picker-ready or not);
* the pin header only narrows; a member is never "acting" (plain audit actor).
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth.effective_org import (
    ORG_SELECTION_REQUIRED_CODE,
    acting_audit_actor,
    resolve_effective_org,
)
from noctusai_lib.api.auth.org_selection import (
    FakeOrgSelectionStore,
    OrgMembership,
    OrgSelectionError,
    RealOrgSelectionStore,
)
from noctusai_lib.domain.licensing import FakeLicenseChecker
from noctusai_lib.testing import MockSupabaseClient

ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"
ORG_C = "00000000-0000-0000-0000-00000000000c"
USER = "bbbbbbbb-0000-0000-0000-000000000001"
SID = "11111111-1111-1111-1111-111111111111"
OTHER_SID = "22222222-2222-2222-2222-222222222222"
SLUG = "igig"


def _tok(sub, **claims):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, **claims})}.s"


def _core(*, org=ORG_A, org_role="owner", role="user"):
    c = MockSupabaseClient()
    c.set_table_data("noctus_users", [{"id": USER, "org_id": org, "org_role": org_role, "role": role}])
    c.set_table_data("organizations", [
        {"id": ORG_A, "nome": "A", "is_platform": False},
        {"id": ORG_B, "nome": "B", "is_platform": False},
        {"id": ORG_C, "nome": "C", "is_platform": False},
    ])
    return c


def _store(**kw):
    kw.setdefault("ready", {SLUG})
    kw.setdefault("licensed", {(ORG_A, SLUG), (ORG_B, SLUG)})
    kw.setdefault("members", {USER: {ORG_A: "owner", ORG_B: "viewer"}})
    return FakeOrgSelectionStore(**kw)


def _lic(*orgs):
    return FakeLicenseChecker(allow_all=False, licensed={(o, SLUG) for o in orgs})


def _resolve(core, store, *, aal="aal1", sid=SID, license_checker=None, **kw):
    return resolve_effective_org(
        core, USER, product_slug=SLUG, token=_tok(USER, session_id=sid, aal=aal),
        selection_store=store, license_checker=license_checker or _lic(ORG_A, ORG_B), **kw,
    )


class TestRoleComesFromTheMembershipOfTheEffectiveOrg:
    def test_owner_in_a_viewer_in_b_is_a_viewer_in_b(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        # The Q3 mirror moved the profile to B with B's role...
        assert store.last_active[USER] == (ORG_B, "viewer")
        # ...and even if a stale profile still said "owner in A", B resolves with B's role.
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.org_role) == (ORG_B, "viewer")
        assert eff.org_role != "owner"

    def test_selecting_back_to_a_restores_the_owner_role_for_a(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        store.set(USER, SLUG, ORG_A, SID)
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.org_role) == (ORG_A, "owner")

    def test_a_staff_role_in_the_profile_is_not_carried_into_the_selected_org(self):
        # A platform-admin FLAG on the profile (role=admin) in a non-platform org is not staff;
        # a selected membership resolves with the membership role, never an elevated one.
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        eff = _resolve(_core(org=ORG_A, org_role="owner", role="admin"), store)
        assert (eff.org_id, eff.org_role, eff.is_staff) == (ORG_B, "viewer", False)

    def test_the_only_eligible_org_is_landed_in_with_its_membership_role(self):
        # D1: profile says "owner in A" but only B is licensed -> B, silently, as a viewer.
        store = _store(licensed={(ORG_B, SLUG)})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store, license_checker=_lic(ORG_B))
        assert (eff.org_id, eff.org_role, eff.selection_id) == (ORG_B, "viewer", None)


class TestSelectionIsRecheckedAgainstTheMembership:
    def test_an_ended_membership_stops_the_selection_on_the_next_request(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        assert _resolve(_core(org=ORG_B, org_role="viewer"), store).org_id == ORG_B
        del store.members[USER][ORG_B]  # S4 ends the membership; nothing else changes
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store, require_selection=False)
        # Never the removed org -- the one remaining eligible org (A) is landed in (D1).
        assert (eff.org_id, eff.org_role, eff.selection_id) == (ORG_A, "owner", None)

    def test_a_removed_member_with_no_eligible_org_left_resolves_no_org(self):
        store = _store(members={USER: {ORG_B: "viewer"}})
        store.set(USER, SLUG, ORG_B, SID)
        del store.members[USER][ORG_B]
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store, require_selection=False)
        assert (eff.org_id, eff.org_role, eff.selection_id) == (None, None, None)

    def test_removed_member_with_two_other_eligible_orgs_must_choose(self):
        store = _store(members={USER: {ORG_A: "owner", ORG_B: "viewer", ORG_C: "member"}},
                       licensed={(ORG_A, SLUG), (ORG_B, SLUG), (ORG_C, SLUG)})
        store.set(USER, SLUG, ORG_B, SID)
        del store.members[USER][ORG_B]
        with pytest.raises(HTTPException) as exc:
            _resolve(_core(org=ORG_B, org_role="viewer"), store, license_checker=_lic(ORG_A, ORG_B, ORG_C))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == ORG_SELECTION_REQUIRED_CODE

    def test_removed_selection_falls_back_to_a_still_active_home(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        del store.members[USER][ORG_B]
        # profile still names A (e.g. the pick was made on another login that did not follow)
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.org_role) == (ORG_A, "owner")

    def test_an_unlicensed_selection_target_is_not_honoured(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store, license_checker=_lic(ORG_A))
        assert eff.org_id == ORG_A and eff.selection_id is None

    def test_a_selection_from_another_login_is_not_honoured(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, OTHER_SID)
        # a new login is a new entry: with two eligible orgs the choice is required again (D1)
        with pytest.raises(HTTPException) as exc:
            _resolve(_core(org=ORG_B, org_role="viewer"), store, sid=SID)
        assert exc.value.detail["code"] == ORG_SELECTION_REQUIRED_CODE
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store, sid=SID, require_selection=False)
        assert (eff.selection_id, eff.member_choice_required) == (None, True)

    def test_a_forged_selection_row_for_a_non_member_org_never_resolves(self):
        store = _store(licensed={(ORG_A, SLUG), (ORG_B, SLUG), (ORG_C, SLUG)})
        store.rows.append({"id": "forged", "user_id": USER, "slug": SLUG, "target": ORG_C,
                           "home": ORG_A, "session": SID, "ended_by": None})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store,
                       license_checker=_lic(ORG_A, ORG_B, ORG_C), require_selection=False)
        assert eff.org_id != ORG_C and eff.selection_id is None and eff.member_choice_required


class TestWhoMaySelect:
    def test_a_member_cannot_select_an_org_they_are_not_a_member_of(self):
        store = _store(licensed={(ORG_A, SLUG), (ORG_B, SLUG), (ORG_C, SLUG)})
        with pytest.raises(OrgSelectionError) as exc:
            store.set(USER, SLUG, ORG_C, SID)
        assert exc.value.code == "not_a_member"
        assert store.rows == []

    def test_a_stranger_cannot_select_anything(self):
        with pytest.raises(OrgSelectionError) as exc:
            _store().set("nobody", SLUG, ORG_A, SID)
        assert exc.value.code == "not_a_member"

    def test_a_member_still_needs_the_target_licensed_and_the_product_ready(self):
        with pytest.raises(OrgSelectionError) as e1:
            _store(licensed={(ORG_A, SLUG)}).set(USER, SLUG, ORG_B, SID)
        assert e1.value.code == "target_not_licensed"
        with pytest.raises(OrgSelectionError) as e2:
            _store(ready=set()).set(USER, SLUG, ORG_B, SID)
        assert e2.value.code == "product_not_ready"

    def test_following_a_pick_never_ends_or_changes_a_membership(self):
        store = _store()
        before = {o: r for o, r in store.members[USER].items()}
        store.set(USER, SLUG, ORG_B, SID)
        store.set(USER, SLUG, ORG_A, SID)
        assert store.members[USER] == before
        # and the mirrored role is never beyond the membership role in the target
        assert store.last_active[USER] == (ORG_A, before[ORG_A])

    def test_moving_the_last_active_org_ends_the_other_live_selections(self):
        store = _store(ready={SLUG, "other"}, licensed={(ORG_A, SLUG), (ORG_B, SLUG), (ORG_B, "other")})
        store.set(USER, SLUG, ORG_A, SID)  # profile -> (A, owner)
        store.set(USER, "other", ORG_B, SID)  # profile -> (B, viewer): revokes the first
        assert [r["ended_by"] for r in store.rows] == ["revoked", None]


class TestNoMfaForMembers:
    def test_member_resolves_a_selection_on_an_aal1_token_even_when_the_product_asks_for_2fa(self):
        store = _store()  # SLUG not in mfa_optional => requires_mfa is True
        assert store.requires_mfa(SLUG) is True
        store.set(USER, SLUG, ORG_B, SID)
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store, aal="aal1")
        assert (eff.org_id, eff.mfa_required) == (ORG_B, False)


class TestD1EveryEntryIsAChoiceWithTwoEligibleOrgs:
    def test_two_licensed_orgs_and_no_selection_is_a_required_choice_on_every_entry(self):
        # D1 replaces Q2: a licensed last-active org is NOT landed in silently any more.
        for _entry in range(2):
            with pytest.raises(HTTPException) as exc:
                _resolve(_core(org=ORG_A, org_role="owner"), _store())
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == ORG_SELECTION_REQUIRED_CODE

    def test_a_new_login_after_choosing_must_choose_again(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        assert _resolve(_core(org=ORG_B, org_role="viewer"), store).org_id == ORG_B
        with pytest.raises(HTTPException):
            _resolve(_core(org=ORG_B, org_role="viewer"), store, sid=OTHER_SID)

    def test_unlicensed_last_active_org_with_one_other_eligible_org_lands_there(self):
        store = _store(licensed={(ORG_B, SLUG)})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store, license_checker=_lic(ORG_B))
        assert (eff.org_id, eff.org_role, eff.member_choice_required) == (ORG_B, "viewer", False)

    def test_the_ungated_bootstrap_reports_the_required_choice_instead_of_raising(self):
        eff = _resolve(_core(org=ORG_A, org_role="owner"), _store(), require_selection=False)
        assert eff.member_choice_required is True and eff.member_can_select is True
        assert set(eff.eligible) == {(ORG_A, "owner"), (ORG_B, "viewer")}

    def test_unlicensed_orgs_do_not_count(self):
        store = _store(members={USER: {ORG_A: "owner", ORG_B: "viewer", ORG_C: "member"}},
                       licensed={(ORG_A, SLUG)})
        eff = _resolve(_core(org=ORG_C, org_role="member"), store, license_checker=_lic(ORG_A))
        assert (eff.org_id, eff.org_role, eff.member_can_select) == (ORG_A, "owner", False)

    def test_single_org_member_never_sees_a_choice(self):
        store = _store(members={USER: {ORG_A: "owner"}})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store, require_selection=False)
        assert (eff.org_id, eff.member_can_select, eff.member_choice_required) == (ORG_A, False, False)
        # even with an unlicensed home: nothing to choose, the license gate answers 403 downstream
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store, license_checker=_lic())
        assert (eff.org_id, eff.member_choice_required) == (ORG_A, False)

    def test_after_a_valid_choice_the_switcher_stays_available_without_requiring_a_choice(self):
        store = _store()
        store.set(USER, SLUG, ORG_A, SID)
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.member_can_select, eff.member_choice_required) == (ORG_A, True, False)

    def test_customer_memberships_do_not_count(self):
        # a customer-role membership is never eligible: B is the only eligible org -> B, no choice
        store = _store(members={USER: {ORG_A: "membro", ORG_B: "viewer"}})
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store, require_selection=False)
        assert (eff.org_id, eff.org_role, eff.member_can_select) == (ORG_B, "viewer", False)

    def test_a_customer_profile_never_picks_and_keeps_its_home_for_the_license_gate(self):
        store = _store(members={USER: {ORG_A: "membro", ORG_B: "viewer"}})
        eff = _resolve(_core(org=ORG_A, org_role="membro"), store)
        assert (eff.org_id, eff.org_role) == (ORG_A, "membro")

    def test_a_customer_only_user_resolves_their_home_for_the_license_gate(self):
        store = _store(members={USER: {ORG_A: "membro"}})
        eff = _resolve(_core(org=ORG_A, org_role="membro"), store)
        assert (eff.org_id, eff.org_role) == (ORG_A, "membro")


class TestD5BlockedProductAccess:
    def test_a_blocked_org_is_not_eligible_so_the_other_one_is_landed_in(self):
        store = _store(blocked={(USER, ORG_A, SLUG)})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.org_role, eff.member_can_select) == (ORG_B, "viewer", False)
        assert eff.eligible == ((ORG_B, "viewer"),)

    def test_a_selection_of_an_org_blocked_afterwards_is_not_honoured(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        store.blocked.add((USER, ORG_B, SLUG))
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store)
        assert (eff.org_id, eff.selection_id) == (ORG_A, None)

    def test_blocked_everywhere_resolves_no_org(self):
        store = _store(blocked={(USER, ORG_A, SLUG), (USER, ORG_B, SLUG)})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.org_role) == (None, None)

    def test_a_blocked_home_is_never_served_on_a_product_without_the_picker(self):
        store = _store(ready=set(), blocked={(USER, ORG_A, SLUG)})
        eff = _resolve(_core(org=ORG_A, org_role="owner"), store)
        assert (eff.org_id, eff.org_role, eff.home_org_id) == (None, None, ORG_A)
        # another product is untouched
        other = resolve_effective_org(_core(org=ORG_A, org_role="owner"), USER, product_slug="other",
                                      token=_tok(USER, session_id=SID), selection_store=store)
        assert other.org_id == ORG_A

    def test_a_member_cannot_select_an_org_they_are_blocked_in(self):
        store = _store(blocked={(USER, ORG_B, SLUG)})
        with pytest.raises(OrgSelectionError) as exc:
            store.set(USER, SLUG, ORG_B, SID)
        assert exc.value.code == "product_blocked"

    def test_the_real_store_reads_only_live_blocks_for_the_product(self):
        core = MockSupabaseClient()
        core.set_table_data("products", [{"id": "p1", "slug": SLUG, "org_picker_ready": True,
                                          "org_picker_requires_mfa": False, "db_schema": "igig"}])
        core.set_table_data("org_member_product_access", [
            {"id": "b1", "user_id": USER, "org_id": ORG_A, "product_id": "p1", "unblocked_at": None},
            {"id": "b2", "user_id": USER, "org_id": ORG_B, "product_id": "p1",
             "unblocked_at": "2026-10-14T00:00:00Z"},
            {"id": "b3", "user_id": USER, "org_id": ORG_C, "product_id": "p2", "unblocked_at": None},
        ])
        assert RealOrgSelectionStore(lambda: core).blocked_orgs(USER, SLUG) == {ORG_A}


class TestPinOnlyNarrows:
    def test_a_pin_for_another_org_is_refused_never_followed(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        with pytest.raises(HTTPException) as exc:
            _resolve(_core(org=ORG_B, org_role="viewer"), store, acting_header=ORG_A)
        assert exc.value.detail["code"] == "org_selection_changed"

    def test_a_pin_for_another_org_is_refused_on_a_silent_landing_too(self):
        store = _store(licensed={(ORG_B, SLUG)})
        with pytest.raises(HTTPException) as exc:
            _resolve(_core(org=ORG_A, org_role="owner"), store, license_checker=_lic(ORG_B),
                     acting_header=ORG_A)
        assert exc.value.detail["code"] == "org_selection_changed"

    def test_a_matching_pin_passes(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store, acting_header=ORG_B.upper())
        assert eff.org_id == ORG_B


class TestAudit:
    def test_a_member_in_their_selected_org_is_not_acting_and_gets_the_plain_actor(self):
        store = _store()
        store.set(USER, SLUG, ORG_B, SID)
        eff = _resolve(_core(org=ORG_B, org_role="viewer"), store)
        assert eff.selection_id is not None and eff.acting is False
        assert acting_audit_actor(USER, eff) is None  # not "platform_support"

    def test_the_selection_row_is_the_audit_record_of_the_switch(self):
        store = _store()
        sid = store.set(USER, SLUG, ORG_B, SID)
        row = next(r for r in store.rows if r["id"] == sid)
        assert (row["user_id"], row["target"], row["session"]) == (USER, ORG_B, SID)


class TestRealStoreMemberships:
    def test_reads_only_the_callers_active_rows_fresh_every_time(self):
        core = MockSupabaseClient()
        rows = [
            {"id": "m1", "user_id": USER, "org_id": ORG_A, "org_role": "owner", "status": "active"},
            {"id": "m2", "user_id": USER, "org_id": ORG_B, "org_role": "viewer", "status": "removed"},
            {"id": "m3", "user_id": "someone-else", "org_id": ORG_C, "org_role": "owner", "status": "active"},
        ]
        core.set_table_data("org_memberships", rows)
        store = RealOrgSelectionStore(lambda: core)
        assert store.memberships(USER) == [OrgMembership(ORG_A, "owner")]
        rows[1]["status"] = "active"
        core.set_table_data("org_memberships", rows)
        assert {m.org_id for m in store.memberships(USER)} == {ORG_A, ORG_B}

    def test_set_maps_the_not_a_member_rpc_error(self):
        class _Rpc:
            def rpc(self, name, params):
                class _Q:
                    def execute(self_inner):
                        raise RuntimeError("platform_org_selection:not_a_member")

                return _Q()

        with pytest.raises(OrgSelectionError) as exc:
            RealOrgSelectionStore(lambda: _Rpc()).set(USER, SLUG, ORG_C, SID)
        assert exc.value.code == "not_a_member"
