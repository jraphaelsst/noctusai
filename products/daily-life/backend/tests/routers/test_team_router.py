"""Tests for the team management router."""
from unittest.mock import patch, MagicMock

from noctusai_shared.testing import MockUser


MOCK_USER_ID = "user-abc-123"
MOCK_OTHER_USER_ID = "user-def-456"
MOCK_ORG_ID = "test-org-123"

MOCK_MEMBERS = [
    {
        "id": MOCK_USER_ID,
        "nome": "Alice Admin",
        "email": "alice@example.com",
        "org_role": "owner",
        "avatar_url": None,
        "created_at": "2026-01-01T00:00:00Z",
    },
    {
        "id": MOCK_OTHER_USER_ID,
        "nome": "Bob Member",
        "email": "bob@example.com",
        "org_role": "member",
        "avatar_url": None,
        "created_at": "2026-01-02T00:00:00Z",
    },
]

MOCK_INVITATION = {
    "id": "invite-001",
    "org_id": MOCK_ORG_ID,
    "email": "new@example.com",
    "role": "member",
    "token": "secure-token-xyz",
    "status": "pending",
    "invited_by": MOCK_USER_ID,
}


class TestListMembers:
    """GET /api/team"""

    def test_list_members(self, client):
        client.mock_supabase.set_table_data("noctus_users", MOCK_MEMBERS)
        resp = client.get("/api/team")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] is not None
        members = body["data"]
        assert len(members) == 2
        # owner -> admin role mapping
        assert members[0]["role"] == "admin"
        # member stays member
        assert members[1]["role"] == "member"

    def test_list_members_no_auth(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401


class TestInviteMember:
    """POST /api/team/invite"""

    @patch("app.routers.team.send_product_invitation_email")
    @patch("app.routers.team.create_invitation")
    def test_invite_success(self, mock_create, mock_email, client):
        # _require_daily_life_admin checks noctus_users for org_role,
        # then existing member check (also noctus_users), then org name.
        # Use sequential responses: first = admin check, second = no existing member, third not needed
        from noctusai_shared.testing import MockSupabaseResponse
        client.mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),  # _require_daily_life_admin
            MockSupabaseResponse(data=[]),  # existing member check (empty = no duplicate)
        ])
        client.mock_supabase.set_table_data("organizations", [{"name": "Test Org"}])

        mock_create.return_value = MOCK_INVITATION

        resp = client.post("/api/team/invite", json={
            "email": "new@example.com",
            "role": "member",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["email"] == "new@example.com"
        mock_create.assert_called_once()
        mock_email.assert_called_once()

    def test_invite_no_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={
            "email": "new@example.com",
            "role": "member",
        })
        assert resp.status_code == 401

    @patch("app.routers.team.send_product_invitation_email")
    @patch("app.routers.team.create_invitation")
    def test_invite_duplicate_member(self, mock_create, mock_email, client):
        """Inviting someone who is already a member returns 409."""
        from noctusai_shared.testing import MockSupabaseResponse
        client.mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),  # _require_daily_life_admin
            MockSupabaseResponse(data=[{"id": "existing-user"}]),  # existing member found -> 409
        ])

        resp = client.post("/api/team/invite", json={
            "email": "existing@example.com",
            "role": "member",
        })
        assert resp.status_code == 409


class TestAcceptInvite:
    """POST /api/team/accept"""

    @patch("app.routers.team.accept_invitation")
    @patch("app.routers.team.validate_invitation")
    def test_accept_success(self, mock_validate, mock_accept, client):
        mock_validate.return_value = {
            "id": "invite-001",
            "org_id": MOCK_ORG_ID,
            "email": "new@example.com",
            "role": "member",
        }
        # Mock auth.admin.create_user
        mock_auth_result = MagicMock()
        mock_auth_result.user.id = "new-user-id-999"
        client.mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_auth_result)
        # noctus_users insert
        client.mock_supabase.set_table_data("noctus_users", [{"id": "new-user-id-999"}])

        resp = client.raw().post("/api/team/accept", json={
            "token": "secure-token-xyz",
            "nome": "carlos silva",
            "password": "secret123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["user_id"] == "new-user-id-999"
        assert body["data"]["nome"] == "Carlos Silva"  # capitalized
        assert body["data"]["role"] == "member"
        mock_accept.assert_called_once()

    @patch("app.routers.team.validate_invitation")
    def test_accept_invalid_token(self, mock_validate, client):
        from fastapi import HTTPException
        mock_validate.side_effect = HTTPException(status_code=404, detail="Convite nao encontrado")

        resp = client.raw().post("/api/team/accept", json={
            "token": "bad-token",
            "nome": "Test User",
            "password": "secret123",
        })
        assert resp.status_code == 404


class TestValidateToken:
    """GET /api/team/accept/validate"""

    @patch("app.routers.team.validate_invitation")
    def test_validate_token(self, mock_validate, client):
        mock_validate.return_value = {
            "id": "invite-001",
            "org_id": MOCK_ORG_ID,
            "email": "new@example.com",
            "role": "member",
        }
        # _get_org_name
        client.mock_supabase.set_table_data("organizations", [{"name": "Test Org"}])

        resp = client.raw().get("/api/team/accept/validate", params={"token": "secure-token-xyz"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["email"] == "new@example.com"
        assert body["data"]["org_name"] == "Test Org"
        assert body["data"]["role"] == "Membro"  # label, not raw role


class TestCancelInvitation:
    """DELETE /api/team/invitations/{invitation_id}"""

    @patch("app.routers.team.cancel_invitation")
    def test_cancel_invitation(self, mock_cancel, client):
        # _require_daily_life_admin -> noctus_users org_role
        client.mock_supabase.set_table_data("noctus_users", [{"org_role": "admin"}])

        resp = client.delete("/api/team/invitations/invite-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "cancelado" in body["message"].lower()
        mock_cancel.assert_called_once()


class TestRemoveMember:
    """DELETE /api/team/{user_id}"""

    def test_remove_member(self, client):
        from noctusai_shared.testing import MockSupabaseResponse
        # Sequential responses for noctus_users:
        # 1. _require_daily_life_admin -> org_role check
        # 2. member lookup
        # 3. delete (no response needed, MockFilterBuilder returns default)
        client.mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),
            MockSupabaseResponse(data=[{
                "id": MOCK_OTHER_USER_ID,
                "nome": "Bob",
                "email": "bob@example.com",
                "org_id": MOCK_ORG_ID,
            }]),
            MockSupabaseResponse(data=[]),  # delete result
        ])
        # organizations owner check -> current user is owner, not the removed user
        default_user_id = str(MockUser(org_id="test-org-123").id)
        client.mock_supabase.set_table_data("organizations", [{"owner_id": default_user_id}])

        resp = client.delete(f"/api/team/{MOCK_OTHER_USER_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert "removido" in body["message"].lower()

    def test_remove_self_forbidden(self, client):
        """A user cannot remove themselves."""
        # _require_daily_life_admin
        client.mock_supabase.set_table_data("noctus_users", [{"org_role": "owner"}])

        default_id = str(MockUser(org_id="test-org-123").id)

        resp = client.delete(f"/api/team/{default_id}")
        assert resp.status_code == 400
        body = resp.json()
        # Shared exception handler wraps in error.message
        message = body.get("detail") or body.get("error", {}).get("message", "")
        assert "si mesmo" in message
