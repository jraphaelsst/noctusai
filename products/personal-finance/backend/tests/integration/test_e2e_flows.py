"""
End-to-end integration tests for Personal Finance team management flows.

Tests the full team invitation lifecycle: invite, validate, accept, list,
cancel, and member removal.

Uses the mock fixtures from conftest.py with set_table_data and
set_sequential_responses to simulate multi-step flows.
"""
import pytest
from unittest.mock import MagicMock, patch

from noctusai_shared.testing import MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INVITE_RECORD = {
    "id": "inv-pf-001",
    "org_id": "test-org-123",
    "email": "newmember@example.com",
    "role": "member",
    "invited_by": "test-user-123",
    "token": "mock-pf-token-abc",
    "status": "pending",
    "expires_at": "2099-12-31T23:59:59+00:00",
    "created_at": "2026-04-13T10:00:00+00:00",
}

MEMBER_RECORD = {
    "id": "member-001",
    "nome": "Ana Membro",
    "email": "ana@example.com",
    "org_role": "member",
    "avatar_url": None,
    "created_at": "2026-01-01T00:00:00+00:00",
}


def _mock_admin_check(mock_sb):
    """Set up noctus_users lookup to return admin role (via core client)."""
    # The _require_pf_admin function calls get_core_client().table("noctus_users")
    # Since the fixture patches both app.database and app.dependencies,
    # the mock_sb handles all table calls.
    mock_sb.set_table_data("noctus_users", [{"org_role": "owner"}])


# ===================================================================
# 1. Admin invites member
# ===================================================================

class TestAdminInvitesMember:
    """POST /api/team/invite — admin invites a new team member."""

    @patch("app.routers.team.send_product_invitation_email")
    @patch("app.routers.team.get_core_client")
    def test_invite_member_success(self, mock_core, mock_email, client):
        # Core client mock for admin check + org name + existing member check
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        core_mock.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),     # _require_pf_admin
            MockSupabaseResponse(data=[]),                           # existing member check
        ])
        core_mock.set_table_data("organizations", [{"name": "Minha Org"}])

        # Invitations table: check pending + insert
        client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),                # no pending
            MockSupabaseResponse(data=[INVITE_RECORD]),   # insert
        ])

        resp = client.post("/api/team/invite", json={
            "email": "newmember@example.com",
            "role": "member",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == "newmember@example.com"
        assert data["status"] == "pending"
        mock_email.assert_called_once()

    @patch("app.routers.team.send_product_invitation_email")
    @patch("app.routers.team.get_core_client")
    def test_invite_duplicate_member_409(self, mock_core, mock_email, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        core_mock.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),     # admin check
            MockSupabaseResponse(data=[{"id": "existing-user"}]),   # already a member
        ])

        resp = client.post("/api/team/invite", json={
            "email": "existing@example.com",
            "role": "member",
        })

        assert resp.status_code == 409
        assert "membro" in resp.json()["error"]["message"].lower()

    @patch("app.routers.team.get_core_client")
    def test_invite_non_admin_403(self, mock_core, client):
        """Non-admin users cannot invite."""
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        core_mock.set_table_data("noctus_users", [{"org_role": "member"}])

        resp = client.post("/api/team/invite", json={
            "email": "someone@example.com",
            "role": "member",
        })

        assert resp.status_code == 403


# ===================================================================
# 2. Accept invitation
# ===================================================================

class TestAcceptInvitation:
    """POST /api/team/accept — accept an invitation (public endpoint)."""

    @patch("app.routers.team.get_core_client")
    def test_accept_invitation_creates_user(self, mock_core, client):
        invite = {**INVITE_RECORD, "status": "pending"}

        # Invitations: validate (single) + mark accepted
        client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=invite),    # validate_invitation (single)
            MockSupabaseResponse(data=[{**invite, "status": "accepted"}]),  # accept
        ])

        # Mock auth.admin.create_user
        mock_new_user = MagicMock()
        mock_new_user.id = "new-user-pf-001"
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_new_user
        client.mock_supabase.auth.admin.create_user = MagicMock(
            return_value=mock_auth_response
        )

        # Core client for noctus_users insert
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("organizations", [{"name": "Org Test"}])

        resp = client.raw().post("/api/team/accept", json={
            "token": "mock-pf-token-abc",
            "nome": "joao silva",
            "password": "securepass123",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "new-user-pf-001"
        assert data["email"] == "newmember@example.com"
        assert data["nome"] == "Joao Silva"  # capitalized
        assert data["role"] == "member"

    @patch("app.routers.team.get_core_client")
    def test_accept_invalid_token_404(self, mock_core, client):
        """Invalid token returns 404."""
        client.mock_supabase.set_table_data("invitations", [])

        resp = client.raw().post("/api/team/accept", json={
            "token": "nonexistent-token",
            "nome": "Test User",
            "password": "password123",
        })

        assert resp.status_code == 404

    @patch("app.routers.team.get_core_client")
    def test_accept_already_used_token_400(self, mock_core, client):
        """Already accepted token returns 400."""
        invite = {**INVITE_RECORD, "status": "accepted"}
        client.mock_supabase.set_table_data("invitations", invite)

        resp = client.raw().post("/api/team/accept", json={
            "token": "mock-pf-token-abc",
            "nome": "Test User",
            "password": "password123",
        })

        assert resp.status_code == 400


# ===================================================================
# 3. List team members
# ===================================================================

class TestListTeam:
    """GET /api/team — list organization members."""

    @patch("app.routers.team.get_core_client")
    def test_list_members_success(self, mock_core, client):
        members = [
            {**MEMBER_RECORD, "id": "m1", "org_role": "owner"},
            {**MEMBER_RECORD, "id": "m2", "nome": "Carlos", "org_role": "member"},
        ]
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("noctus_users", members)

        resp = client.get("/api/team")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        # owner should be mapped to admin role
        owner = next(m for m in data if m["id"] == "m1")
        assert owner["role"] == "admin"
        # member stays member
        member = next(m for m in data if m["id"] == "m2")
        assert member["role"] == "member"

    @patch("app.routers.team.get_core_client")
    def test_list_members_empty_org(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("noctus_users", [])

        resp = client.get("/api/team")

        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ===================================================================
# 4. Cancel invitation
# ===================================================================

class TestCancelInvitation:
    """DELETE /api/team/invitations/{id} — cancel a pending invitation."""

    @patch("app.routers.team.get_core_client")
    def test_cancel_invitation_success(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        # Admin check
        core_mock.set_table_data("noctus_users", [{"org_role": "owner"}])

        # cancel_invitation: fetch (single) + update
        client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data={"id": "inv-pf-001", "status": "pending"}),  # single
            MockSupabaseResponse(data=[{"id": "inv-pf-001", "status": "canceled"}]),
        ])

        resp = client.delete("/api/team/invitations/inv-pf-001")

        assert resp.status_code == 200
        assert "cancelado" in resp.json()["message"].lower()

    @patch("app.routers.team.get_core_client")
    def test_cancel_nonexistent_invitation_404(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("noctus_users", [{"org_role": "owner"}])

        # Not found by cancel_invitation (single returns None)
        client.mock_supabase.set_table_data("invitations", [])

        resp = client.delete("/api/team/invitations/nonexistent")

        assert resp.status_code == 404

    @patch("app.routers.team.get_core_client")
    def test_cancel_non_admin_403(self, mock_core, client):
        """Non-admin cannot cancel invitations."""
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("noctus_users", [{"org_role": "member"}])

        resp = client.delete("/api/team/invitations/inv-pf-001")

        assert resp.status_code == 403


# ===================================================================
# 5. Remove member
# ===================================================================

class TestRemoveMember:
    """DELETE /api/team/{user_id} — remove a member from the organization."""

    @patch("app.routers.team.get_core_client")
    def test_remove_member_success(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        core_mock.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),  # admin check
            MockSupabaseResponse(data=[{                         # member exists
                "id": "member-to-remove",
                "nome": "Remove Me",
                "email": "remove@example.com",
                "org_id": "test-org-123",
            }]),
            MockSupabaseResponse(data=[]),  # delete result
        ])
        core_mock.set_table_data("organizations", [
            {"owner_id": "test-user-123"},  # current user is owner
        ])

        resp = client.delete("/api/team/member-to-remove")

        assert resp.status_code == 200
        assert "removido" in resp.json()["message"].lower()

    @patch("app.routers.team.get_core_client")
    def test_cannot_remove_self(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("noctus_users", [{"org_role": "owner"}])

        # Try to remove self (test-user-123 is the fixture's user ID)
        resp = client.delete("/api/team/test-user-123")

        assert resp.status_code == 400
        assert "si mesmo" in resp.json()["error"]["message"].lower()

    @patch("app.routers.team.get_core_client")
    def test_remove_nonexistent_member_404(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        core_mock.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),  # admin check
            MockSupabaseResponse(data=[]),                        # member not found
        ])

        resp = client.delete("/api/team/nonexistent-user")

        assert resp.status_code == 404

    @patch("app.routers.team.get_core_client")
    def test_cannot_remove_org_owner(self, mock_core, client):
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock

        core_mock.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"org_role": "owner"}]),  # admin check
            MockSupabaseResponse(data=[{                         # member exists
                "id": "owner-user-id",
                "nome": "Owner",
                "email": "owner@example.com",
                "org_id": "test-org-123",
            }]),
            MockSupabaseResponse(data=[]),  # won't reach delete
        ])
        core_mock.set_table_data("organizations", [
            {"owner_id": "owner-user-id"},  # target IS the owner
        ])

        resp = client.delete("/api/team/owner-user-id")

        assert resp.status_code == 400
        assert "proprietario" in resp.json()["error"]["message"].lower()

    @patch("app.routers.team.get_core_client")
    def test_remove_non_admin_403(self, mock_core, client):
        """Non-admin cannot remove members."""
        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("noctus_users", [{"org_role": "member"}])

        resp = client.delete("/api/team/some-user-id")

        assert resp.status_code == 403


# ===================================================================
# 6. Validate invitation endpoint
# ===================================================================

class TestValidateEndpoint:
    """GET /api/team/accept/validate?token=x — public endpoint."""

    @patch("app.routers.team.get_core_client")
    def test_validate_returns_info(self, mock_core, client):
        invite = {**INVITE_RECORD, "status": "pending"}
        client.mock_supabase.set_table_data("invitations", invite)

        core_mock = client.mock_supabase
        mock_core.return_value = core_mock
        core_mock.set_table_data("organizations", [{"name": "Financas Corp"}])

        resp = client.raw().get(
            "/api/team/accept/validate",
            params={"token": "mock-pf-token-abc"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == "newmember@example.com"
        assert data["role"] == "Membro"  # mapped via PF_ROLE_LABELS
        assert data["org_name"] == "Financas Corp"

    @patch("app.routers.team.get_core_client")
    def test_validate_invalid_token_404(self, mock_core, client):
        client.mock_supabase.set_table_data("invitations", [])

        resp = client.raw().get(
            "/api/team/accept/validate",
            params={"token": "nonexistent"},
        )

        assert resp.status_code == 404

    @patch("app.routers.team.get_core_client")
    def test_validate_expired_token_400(self, mock_core, client):
        invite = {
            **INVITE_RECORD,
            "status": "pending",
            "expires_at": "2020-01-01T00:00:00+00:00",
        }
        # validate_invitation auto-expires + sequential: single → update
        client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=invite),    # single
            MockSupabaseResponse(data=[{**invite, "status": "expired"}]),  # auto-expire update
        ])

        resp = client.raw().get(
            "/api/team/accept/validate",
            params={"token": "mock-pf-token-abc"},
        )

        assert resp.status_code == 400
