"""
Tests for Team Management router — /api/team (Seed Product)

Covers: invite flow, accept flow, list invitations, list members,
cancel invitation, and remove member.
"""
from unittest.mock import MagicMock, patch
from noctusai_shared.testing import MockSupabaseResponse

# Default MockUser id
USER_ID = "test-user-123"


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_INVITE = {
    "id": "inv-1",
    "email": "new@test.com",
    "role": "member",
    "token": "tok-abc123",
    "status": "pending",
    "org_id": "test-org-123",
    "invited_by": USER_ID,
}

SAMPLE_MEMBER = {
    "id": "m1",
    "nome": "Membro Seed",
    "email": "membro@test.com",
    "org_role": "member",
    "avatar_url": None,
    "created_at": "2026-01-01T00:00:00",
}


def _mock_email():
    return patch("app.routers.team.send_product_invitation_email", MagicMock())


def _mock_core_client(mock_sb):
    """Patch get_core_client at the router module level."""
    return patch("app.routers.team.get_core_client", return_value=mock_sb)


# ---------------------------------------------------------------------------
# POST /api/team/invite
# ---------------------------------------------------------------------------


class TestInvite:
    def test_invite_success(self, client):
        """Admin can invite a new member."""
        client._mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"id": USER_ID, "org_role": "owner"}]),  # admin check
            MockSupabaseResponse(data=[]),  # existing member check — no match
        ])
        client._mock_supabase.set_table_data("organizations", [{"name": "Test Org"}])

        with _mock_email(), \
             _mock_core_client(client._mock_supabase), \
             patch("app.routers.team.create_invitation", return_value=SAMPLE_INVITE):
            resp = client.post("/api/team/invite", json={
                "email": "new@test.com",
                "role": "member",
            })
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "new@test.com"

    def test_invite_no_auth(self, client):
        """401 when no authorization header is sent."""
        resp = client.raw().post("/api/team/invite", json={
            "email": "test@test.com",
            "role": "member",
        })
        assert resp.status_code == 401

    def test_invite_duplicate_email(self, client):
        """409 when email is already a member."""
        client._mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"id": USER_ID, "org_role": "owner"}]),  # admin check
            MockSupabaseResponse(data=[{"id": "existing-1", "email": "dup@test.com"}]),  # exists
        ])

        with _mock_core_client(client._mock_supabase):
            resp = client.post("/api/team/invite", json={
                "email": "dup@test.com",
                "role": "member",
            })
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/team/accept
# ---------------------------------------------------------------------------


class TestAccept:
    def test_accept_success(self, client):
        """Creates auth user + noctus_users record when valid token is accepted."""
        mock_auth_user = MagicMock()
        mock_auth_user.user = MagicMock()
        mock_auth_user.user.id = "new-user-456"
        client._mock_supabase.auth.admin = MagicMock()
        client._mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_auth_user)

        with patch("app.routers.team.validate_invitation", return_value=SAMPLE_INVITE), \
             patch("app.routers.team.accept_invitation") as mock_accept, \
             _mock_core_client(client._mock_supabase):
            resp = client.raw().post("/api/team/accept", json={
                "token": "tok-abc123",
                "nome": "maria souza",
                "password": "senha123456",
            })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "new-user-456"
        assert data["nome"] == "Maria Souza"
        assert data["role"] == "member"
        mock_accept.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/team — List members
# ---------------------------------------------------------------------------


class TestListMembers:
    def test_list_members(self, client):
        client._mock_supabase.set_table_data("noctus_users", [SAMPLE_MEMBER])

        with _mock_core_client(client._mock_supabase):
            resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# DELETE /api/team/invitations/{id} — Cancel invitation
# ---------------------------------------------------------------------------


class TestCancelInvitation:
    def test_cancel_invitation(self, client):
        client._mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"id": USER_ID, "org_role": "owner"}]),
        ])

        with _mock_core_client(client._mock_supabase), \
             patch("app.routers.team.cancel_invitation") as mock_cancel:
            resp = client.delete("/api/team/invitations/inv-1")
        assert resp.status_code == 200
        mock_cancel.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE /api/team/{user_id} — Remove member
# ---------------------------------------------------------------------------


class TestRemoveMember:
    def test_remove_member(self, client):
        """Admin can remove another member."""
        client._mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"id": USER_ID, "org_role": "owner"}]),  # admin check
            MockSupabaseResponse(data=[  # member check
                {"id": "other-user", "nome": "To Remove", "email": "rm@test.com", "org_id": "test-org-123"},
            ]),
            MockSupabaseResponse(data=[]),  # delete response
        ])
        client._mock_supabase.set_table_data(
            "organizations", [{"owner_id": "someone-else"}]
        )

        with _mock_core_client(client._mock_supabase):
            resp = client.delete("/api/team/other-user")
        assert resp.status_code == 200

    def test_remove_self_forbidden(self, client):
        """Cannot remove yourself from the organization."""
        client._mock_supabase.set_sequential_responses("noctus_users", [
            MockSupabaseResponse(data=[{"id": USER_ID, "org_role": "owner"}]),  # admin check
        ])
        with _mock_core_client(client._mock_supabase):
            resp = client.delete(f"/api/team/{USER_ID}")
        assert resp.status_code == 400
