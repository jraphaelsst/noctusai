"""Multi-org membership S4 (roadmap P2.3): the team router acts on ``org_memberships``.

* accept-invite for an EXISTING user joins the inviting org (no 409), profile untouched;
* remove-member ends the membership through ONE transactional RPC (the DB moves/deletes the
  profile in the same transaction -- proven on a real Postgres in
  ``mcp/noctusai/tests/test_core_team_membership_ops_on_replay.py``);
* the team list / seat count / SSO admission read memberships, never ``noctus_users.org_id``.

Refusals from the RPCs arrive as ``team_membership:<code>`` and map to strict statuses.
"""
from __future__ import annotations

import pytest
from postgrest.exceptions import APIError

ADMIN = "admin-user-456"   # admin_client's user; profile org = org-1


class _RaisingRpc:
    """An RPC whose execute() raises the PostgREST error a refusing function produces."""

    def __init__(self, code: str):
        self._err = APIError({"message": f"team_membership:{code}", "code": "P0001", "details": None, "hint": None})

    def execute(self):
        raise self._err


def _refuse(mock_sb, code: str) -> None:
    """The refusing function is the external boundary (a DB function); the router is what we test."""
    mock_sb.rpc = lambda name, params=None: _RaisingRpc(code)


def _team(mock_sb, *, target_org_role="member", target_profile_org="org-9", extra_memberships=()):
    mock_sb.set_table_data("noctus_users", [
        {"id": ADMIN, "org_id": "org-1", "org_role": "admin", "role": "admin", "email": "a@example.com"},
        {"id": "u-target", "org_id": target_profile_org, "org_role": "viewer", "email": "t@example.com",
         "nome": "Target", "created_at": "2026-01-02"},
    ])
    mock_sb.set_table_data("org_memberships", [
        {"user_id": ADMIN, "org_id": "org-1", "org_role": "admin", "status": "active", "created_at": "2026-01-01"},
        {"user_id": "u-target", "org_id": "org-1", "org_role": target_org_role, "status": "active",
         "created_at": "2026-01-02"},
        *extra_memberships,
    ])


class TestTeamListReadsMemberships:
    def test_member_whose_profile_points_elsewhere_is_listed_with_the_role_in_this_org(self, admin_client):
        _team(admin_client.mock_supabase, target_org_role="manager", target_profile_org="org-9")
        resp = admin_client.get("/api/team")
        assert resp.status_code == 200, resp.text
        rows = {r["id"]: r for r in resp.json()["data"]}
        assert set(rows) == {ADMIN, "u-target"}
        # the role shown is the MEMBERSHIP role here ('manager'), not the profile's last-active-org role ('viewer')
        assert rows["u-target"]["org_role"] == "manager"
        assert rows["u-target"]["email"] == "t@example.com"

    def test_ended_and_other_org_memberships_are_not_listed(self, admin_client):
        _team(admin_client.mock_supabase, extra_memberships=[
            {"user_id": "u-gone", "org_id": "org-1", "org_role": "member", "status": "removed"},
            {"user_id": "u-else", "org_id": "org-2", "org_role": "member", "status": "active"},
        ])
        ids = {r["id"] for r in admin_client.get("/api/team").json()["data"]}
        assert ids == {ADMIN, "u-target"}


class TestRemoveMemberIsAMembershipOperation:
    def test_removes_through_the_transactional_rpc_and_audits_where_the_profile_went(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb, target_profile_org="org-1", extra_memberships=[  # org-1 IS the profile org
            {"user_id": "u-target", "org_id": "org-2", "org_role": "member", "status": "active"}])
        mock_sb.set_rpc_data("team_member_remove", {"profile_moved_to": "org-2", "personal_org_id": None})
        resp = admin_client.delete("/api/team/u-target")
        assert resp.status_code == 200, resp.text
        # another membership exists -> no personal org; the actor rides along (D2 override is SQL's)
        assert mock_sb.rpc_calls == [("team_member_remove", {
            "p_org_id": "org-1", "p_user_id": "u-target", "p_actor_id": ADMIN, "p_personal_org_id": None})]
        assert mock_sb.table("organizations").inserted_payloads == []
        # never the old PostgREST-sequence shape: the router does not write the profile itself
        assert mock_sb.table("noctus_users").updated_payloads == []

    def test_removal_of_a_member_whose_profile_is_elsewhere_leaves_the_profile_to_the_db(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb, target_profile_org="org-9")
        mock_sb.set_rpc_data("team_member_remove", {"profile_moved_to": None, "profile_deleted": False})
        assert admin_client.delete("/api/team/u-target").status_code == 200
        assert mock_sb.table("noctus_users").updated_payloads == []

    def test_target_without_an_active_membership_here_is_404_and_nothing_runs(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb)
        mock_sb.set_table_data("org_memberships", [
            {"user_id": "u-target", "org_id": "org-1", "org_role": "member", "status": "removed"},
            {"user_id": "u-target", "org_id": "org-2", "org_role": "member", "status": "active"},
        ])
        assert admin_client.delete("/api/team/u-target").status_code == 404
        assert mock_sb.rpc_calls == []

    def test_last_owner_refusal_from_the_db_is_a_409(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb)
        _refuse(mock_sb, "last_owner")
        resp = admin_client.delete("/api/team/u-target")
        assert resp.status_code == 409, resp.text

    def test_an_unmapped_rpc_error_is_not_swallowed(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb)
        mock_sb.rpc = lambda name, params=None: type("R", (), {"execute": staticmethod(
            lambda: (_ for _ in ()).throw(RuntimeError("boom")))})()
        with pytest.raises(RuntimeError):
            admin_client.delete("/api/team/u-target")

    @pytest.mark.parametrize("caller_org_role,target_role", [("owner", "owner"), ("admin", "owner"), ("manager", "admin")])
    def test_authz_is_unchanged_owner_untouchable_and_admin_needs_owner_or_admin(
        self, admin_client, caller_org_role, target_role
    ):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb, target_org_role=target_role)
        mock_sb.set_table_data("noctus_users", [
            {"id": ADMIN, "org_id": "org-1", "org_role": caller_org_role, "role": "user"},
            {"id": "u-target", "org_id": "org-1", "org_role": target_role, "email": "t@example.com"},
        ])
        assert admin_client.delete("/api/team/u-target").status_code == 403
        assert mock_sb.rpc_calls == []

    def test_a_caller_without_team_manage_is_403(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123", "org_id": "org-1", "org_role": "member", "role": "user"})
        assert client.delete("/api/team/u-target").status_code == 403
        assert mock_sb.rpc_calls == []

    def test_unauthenticated_is_401(self, unauth_client):
        assert unauth_client.delete("/api/team/u-target").status_code == 401


class TestRoleChangeIsAMembershipOperation:
    def test_updates_via_rpc_and_never_writes_the_profile_directly(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb, target_profile_org="org-9")
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "manager"}])
        mock_sb.set_rpc_data("team_member_set_role", {"org_id": "org-1", "org_role": "manager"})
        resp = admin_client.patch("/api/team/u-target/role", json={"role": "manager"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["org_role"] == "manager"
        assert mock_sb.rpc_calls == [("team_member_set_role", {
            "p_org_id": "org-1", "p_user_id": "u-target", "p_role": "manager", "p_actor_id": ADMIN})]
        assert mock_sb.table("noctus_users").updated_payloads == []

    def test_target_not_a_member_here_is_404(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb)
        mock_sb.set_table_data("org_memberships", [])
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "manager"}])
        assert admin_client.patch("/api/team/u-target/role", json={"role": "manager"}).status_code == 404
        assert mock_sb.rpc_calls == []


class TestInviteChecksMembershipNotProfileOrg:
    def _invite_tables(self, mock_sb):
        mock_sb.set_table_data("roles", [{"id": "r1", "slug": "member"}])
        mock_sb.set_table_data("organizations", {"id": "org-1", "nome": "Org"})
        mock_sb.set_table_responses("invitations", [
            [],
            [{"id": "inv-1", "email": "t@example.com", "role": "member", "status": "pending", "token": "t"}],
        ])

    def test_a_user_whose_profile_is_in_another_org_can_be_invited(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", [
            {"id": ADMIN, "org_id": "org-1", "org_role": "admin", "role": "admin"},
            {"id": "u-target", "org_id": "org-9", "org_role": "member", "email": "t@example.com"},
        ])
        mock_sb.set_table_data("org_memberships", [
            {"user_id": "u-target", "org_id": "org-9", "org_role": "member", "status": "active"}])
        self._invite_tables(mock_sb)
        resp = admin_client.post("/api/team/invite", json={"email": "t@example.com", "role": "member"})
        assert resp.status_code == 200, resp.text

    def test_an_active_member_with_a_profile_elsewhere_is_still_refused(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _team(mock_sb, target_profile_org="org-9")
        self._invite_tables(mock_sb)
        resp = admin_client.post("/api/team/invite", json={"email": "t@example.com", "role": "member"})
        assert resp.status_code == 409


def _invite(mock_sb, email="test@example.com", role="manager", org="org-2"):
    mock_sb.set_table_data("invitations", {
        "id": "inv-1", "org_id": org, "email": email, "role": role,
        "status": "pending", "expires_at": "2099-01-01T00:00:00Z", "token": "tok",
    })


class TestAcceptInviteForAnExistingUser:
    """The caller (test-user-123) already has a profile in org-1."""

    def _existing(self, mock_sb, memberships):
        mock_sb.strict_single = True
        _invite(mock_sb)
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123", "org_id": "org-1", "org_role": "owner", "role": "user"})
        mock_sb.set_table_data("org_memberships", memberships)
        mock_sb.set_rpc_data("team_invitation_accept", {"org_id": "org-2", "org_role": "manager"})

    def test_joins_the_second_org_without_touching_the_profile(self, client):
        mock_sb = client.mock_supabase
        self._existing(mock_sb, [
            {"user_id": "test-user-123", "org_id": "org-1", "org_role": "owner", "status": "active"}])
        resp = client.post("/api/team/accept-invite", json={"token": "tok"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"org_id": "org-2", "role": "manager"}
        assert mock_sb.rpc_calls == [("team_invitation_accept", {
            "p_invitation_id": "inv-1", "p_user_id": "test-user-123", "p_nome": "test@example.com"})]
        # last-active org stays: the profile is neither updated nor re-inserted
        assert mock_sb.table("noctus_users").updated_payloads == []
        assert mock_sb.table("noctus_users").inserted_payloads == []

    def test_a_removed_membership_is_reactivated_through_the_same_rpc(self, client):
        mock_sb = client.mock_supabase
        self._existing(mock_sb, [
            {"user_id": "test-user-123", "org_id": "org-1", "org_role": "owner", "status": "active"},
            {"user_id": "test-user-123", "org_id": "org-2", "org_role": "member", "status": "removed"}])
        assert client.post("/api/team/accept-invite", json={"token": "tok"}).status_code == 200
        assert [c[0] for c in mock_sb.rpc_calls] == ["team_invitation_accept"]

    def test_already_an_active_member_is_refused_409(self, client):
        mock_sb = client.mock_supabase
        self._existing(mock_sb, [
            {"user_id": "test-user-123", "org_id": "org-1", "org_role": "owner", "status": "active"},
            {"user_id": "test-user-123", "org_id": "org-2", "org_role": "member", "status": "active"}])
        assert client.post("/api/team/accept-invite", json={"token": "tok"}).status_code == 409
        assert mock_sb.rpc_calls == []

    def test_a_suspended_membership_is_refused_403_an_invitation_cannot_lift_a_suspension(self, client):
        mock_sb = client.mock_supabase
        self._existing(mock_sb, [
            {"user_id": "test-user-123", "org_id": "org-1", "org_role": "owner", "status": "active"},
            {"user_id": "test-user-123", "org_id": "org-2", "org_role": "member", "status": "suspended"}])
        assert client.post("/api/team/accept-invite", json={"token": "tok"}).status_code == 403
        assert mock_sb.rpc_calls == []

    def test_a_replay_lost_to_a_race_is_refused_409_by_the_db(self, client):
        mock_sb = client.mock_supabase
        self._existing(mock_sb, [
            {"user_id": "test-user-123", "org_id": "org-1", "org_role": "owner", "status": "active"}])
        _refuse(mock_sb, "already_member")
        assert client.post("/api/team/accept-invite", json={"token": "tok"}).status_code == 409

    def test_first_time_invitee_gets_profile_and_linked_membership_in_one_rpc(self, client):
        # D4: the profile insert + the invited_by/invitation_id link + accepted are ONE transaction
        mock_sb = client.mock_supabase
        mock_sb.strict_single = True
        _invite(mock_sb)
        mock_sb.set_table_data("noctus_users", [])
        mock_sb.set_rpc_data("team_invitation_accept", {"org_id": "org-2", "new_user": True})
        resp = client.post("/api/team/accept-invite", json={"token": "tok", "nome": "Nova"})
        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls == [("team_invitation_accept", {
            "p_invitation_id": "inv-1", "p_user_id": "test-user-123", "p_nome": "Nova"})]
        # never the old two-step PostgREST sequence (profile insert, then mark accepted)
        assert mock_sb.table("noctus_users").inserted_payloads == []


@pytest.mark.asyncio
async def test_seat_count_is_active_memberships_not_the_profile_column():
    from unittest.mock import patch
    from noctusai_lib.testing import MockSupabaseClient

    db = MockSupabaseClient()
    db.set_table_data("organizations", {"id": "org-1", "category": "customer"})
    db.set_table_data("subscriptions", [{"org_id": "org-1", "status": "active", "plans": {"max_users": 5}}])
    db.set_table_data("org_memberships", [
        {"user_id": "a", "org_id": "org-1", "status": "active"},
        {"user_id": "b", "org_id": "org-1", "status": "active"},   # profile points at another org
        {"user_id": "c", "org_id": "org-1", "status": "removed"},  # ended: not a seat
    ])
    db.set_table_data("noctus_users", [{"id": "a", "org_id": "org-1"}])  # would count 1 if it read the profile
    with patch("app.services.entitlements.get_admin_client", return_value=db):
        from app.services.entitlements import check_user_limit
        out = await check_user_limit("org-1")
    assert out["current"] == 2
    assert out["remaining"] == 3
