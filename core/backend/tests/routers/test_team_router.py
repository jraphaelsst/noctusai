"""
Tests for Team Router.

GET    /api/team
POST   /api/team/invite              (requires team:manage)
DELETE /api/team/{user_id}           (requires team:manage)
PATCH  /api/team/{user_id}/role      (requires team:manage)
GET    /api/team/invitations         (requires team:read)
DELETE /api/team/invitations/{id}    (requires team:manage)
POST   /api/team/accept-invite
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/team
# ---------------------------------------------------------------------------

class TestListMembers:
    def test_list_members_success(self, client):
        mock_sb = client.mock_supabase
        # noctus_users is queried twice:
        #   1. _get_user_profile (.single) → profile dict
        #   2. list members (.execute) → list of members
        profile = {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
            "nome": "Test User",
            "email": "test@example.com",
        }
        mock_sb.set_table_responses("noctus_users", [
            profile,
            [profile],
        ])

        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_members_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/team")
        assert resp.status_code == 404

    def test_list_members_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/team")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/team/invite (requires team:manage)
# ---------------------------------------------------------------------------

class TestInviteMember:
    def test_invite_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        # noctus_users is queried multiple times:
        #   1. _get_user_profile (.single) → admin profile
        #   2. existing-member check (.eq email) → must be empty
        #   3. inviter name lookup (.single) → admin profile
        mock_sb.set_table_responses("noctus_users", [
            {"id": "admin-user-456", "org_id": "org-1", "org_role": "admin", "role": "admin", "nome": "Admin"},
            [],  # no existing member with that email
            {"id": "admin-user-456", "nome": "Admin"},  # inviter name
        ])
        # invitations is queried then inserted:
        #   1. pending-invite check → must be empty
        #   2. insert → returns the new invitation
        mock_sb.set_table_responses("invitations", [
            [],  # no pending invites
            [{"id": "inv-1", "email": "new@example.com", "role": "member", "status": "pending"}],
        ])
        mock_sb.set_table_data("roles", [{"id": "r1", "slug": "member"}])
        mock_sb.set_table_data("organizations", {"id": "org-1", "nome": "Test Org"})

        resp = admin_client.post("/api/team/invite", json={
            "email": "new@example.com",
            "role": "member",
        })
        assert resp.status_code == 200

    def test_invite_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.post("/api/team/invite", json={
            "email": "new@example.com",
            "role": "member",
        })
        assert resp.status_code == 403

    def test_invite_missing_email(self, admin_client):
        resp = admin_client.post("/api/team/invite", json={
            "role": "member",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/team/{user_id} (requires team:manage)
# ---------------------------------------------------------------------------

class TestRemoveMember:
    def test_remove_member_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })

        resp = admin_client.delete("/api/team/other-user-789")
        assert resp.status_code == 200

    def test_remove_self_rejected(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })

        resp = admin_client.delete("/api/team/admin-user-456")
        assert resp.status_code == 400

    def test_remove_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.delete("/api/team/some-user")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/team/{user_id}/role (requires team:manage)
# ---------------------------------------------------------------------------

class TestChangeMemberRole:
    def test_change_role_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        # noctus_users is queried multiple times:
        #   1. _get_user_profile (.single) → admin profile
        #   2. target member lookup (.single) → target member data
        #   3. update result (.execute) → updated member
        mock_sb.set_table_responses("noctus_users", [
            {"id": "admin-user-456", "org_id": "org-1", "org_role": "admin", "role": "admin"},
            {"id": "other-user", "org_id": "org-1", "org_role": "member"},
            [{"id": "other-user", "org_id": "org-1", "org_role": "admin"}],
        ])
        mock_sb.set_table_data("roles", [{"id": "r1", "slug": "admin"}])

        resp = admin_client.patch("/api/team/other-user/role", json={
            "role": "admin",
        })
        assert resp.status_code == 200

    def test_change_own_role_rejected(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })

        resp = admin_client.patch("/api/team/admin-user-456/role", json={
            "role": "member",
        })
        assert resp.status_code == 400

    def test_promote_to_owner_rejected(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", [{"id": "r-owner", "slug": "owner"}])

        resp = admin_client.patch("/api/team/other-user/role", json={
            "role": "owner",
        })
        assert resp.status_code == 403

    def test_change_role_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.patch("/api/team/other-user/role", json={"role": "admin"})
        assert resp.status_code == 403

    def test_change_role_missing_role_field(self, admin_client):
        resp = admin_client.patch("/api/team/other-user/role", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/team/invitations (requires team:read)
# ---------------------------------------------------------------------------

class TestListInvitations:
    def test_list_invitations_with_permission(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("invitations", [
            {"id": "inv-1", "email": "invite@example.com", "role": "member", "status": "pending"},
        ])

        resp = admin_client.get("/api/team/invitations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_invitations_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "viewer",
            "role": "user",
        })

        resp = client.get("/api/team/invitations")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/team/invitations/{id} (requires team:manage)
# ---------------------------------------------------------------------------

class TestCancelInvitation:
    def test_cancel_invitation_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("invitations", [
            {"id": "inv-1", "org_id": "org-1", "status": "pending"},
        ])

        resp = admin_client.delete("/api/team/invitations/inv-1")
        assert resp.status_code == 200

    def test_cancel_invitation_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("invitations", None)

        resp = admin_client.delete("/api/team/invitations/nonexistent")
        assert resp.status_code == 404

    def test_cancel_invitation_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.delete("/api/team/invitations/inv-1")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/team/accept-invite
# ---------------------------------------------------------------------------

class TestAcceptInvite:
    def test_accept_invite_authenticated_new_profile(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("invitations", {
            "id": "inv-1",
            "org_id": "org-1",
            "email": "test@example.com",
            "role": "member",
            "status": "pending",
            "expires_at": "2099-01-01T00:00:00Z",
        })
        mock_sb.set_table_data("noctus_users", None)

        resp = client.post("/api/team/accept-invite", json={
            "token": "valid-invite-token-abc",
            "nome": "New Member",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Convite aceito com sucesso"

    def test_accept_invite_invalid_token(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("invitations", None)

        resp = client.post("/api/team/accept-invite", json={
            "token": "invalid-token",
        })
        assert resp.status_code == 404

    def test_accept_invite_already_used(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("invitations", {
            "id": "inv-1",
            "org_id": "org-1",
            "email": "test@example.com",
            "role": "member",
            "status": "accepted",
            "expires_at": "2099-01-01T00:00:00Z",
        })

        resp = client.post("/api/team/accept-invite", json={
            "token": "used-token",
        })
        assert resp.status_code == 400

    def test_accept_invite_missing_token(self, client):
        resp = client.post("/api/team/accept-invite", json={})
        assert resp.status_code == 422
