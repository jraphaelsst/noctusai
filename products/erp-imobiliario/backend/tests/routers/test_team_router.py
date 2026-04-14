"""
Tests for Team Management router — /api/team

Covers: invite flow, accept flow, list members, list invitations,
cancel invitation, remove member, and role change.
"""
import pytest
from unittest.mock import MagicMock, patch
from noctusai_shared.testing import MockSupabaseResponse

# Default MockUser id is "test-user-123"
USER_ID = "test-user-123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_INVITE = {
    "id": "inv-1",
    "email": "new@test.com",
    "role": "corretor",
    "token": "abc123",
    "status": "pending",
    "org_id": "test-org-123",
    "invited_by": USER_ID,
}

SAMPLE_PROFILE = {
    "id": "p1",
    "nome": "Membro Teste",
    "email": "membro@test.com",
    "telefone": "11999999999",
    "cargo": "Corretor",
    "avatar_url": None,
    "created_at": "2026-01-01T00:00:00",
    "org_id": "test-org-123",
}


def _mock_admin_role(client):
    """Set up mock data so _require_erp_admin passes (user_roles check)."""
    client._mock_supabase.set_table_data(
        "user_roles", [{"user_id": USER_ID, "role": "admin"}]
    )


def _mock_send_email():
    return patch("app.routers.team.send_product_invitation_email", MagicMock())


def _mock_core_client(mock_sb):
    """Patch get_core_client at the database module level (local imports)."""
    return patch("app.database.get_core_client", return_value=mock_sb)


# ---------------------------------------------------------------------------
# POST /api/team/invite
# ---------------------------------------------------------------------------


class TestInviteSuccess:
    def test_invite_success(self, client):
        _mock_admin_role(client)
        client._mock_supabase.set_table_data("profiles", [])
        client._mock_supabase.set_table_data("organizations", [{"name": "Test Org"}])

        with _mock_send_email(), \
             _mock_core_client(client._mock_supabase), \
             patch("app.routers.team.create_invitation", return_value=SAMPLE_INVITE):
            resp = client.post("/api/team/invite", json={
                "email": "new@test.com",
                "role": "corretor",
            })
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "new@test.com"


class TestInviteDuplicateEmail:
    def test_invite_duplicate_email(self, client):
        """409 when email is already an org member."""
        _mock_admin_role(client)
        client._mock_supabase.set_table_data("profiles", [
            {"id": "existing-1", "email": "dup@test.com", "org_id": "test-org-123"},
        ])

        resp = client.post("/api/team/invite", json={
            "email": "dup@test.com",
            "role": "corretor",
        })
        assert resp.status_code == 409


class TestInviteDuplicatePending:
    def test_invite_duplicate_pending(self, client):
        """409 when a pending invite already exists for that email."""
        _mock_admin_role(client)
        client._mock_supabase.set_table_data("profiles", [])

        def mock_create(*args, **kwargs):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail="Ja existe um convite pendente para este email",
            )

        with _mock_send_email(), \
             _mock_core_client(client._mock_supabase), \
             patch("app.routers.team.create_invitation", side_effect=mock_create):
            resp = client.post("/api/team/invite", json={
                "email": "dup@test.com",
                "role": "corretor",
            })
        assert resp.status_code == 409


class TestInviteNoAuth:
    def test_invite_no_auth(self, client):
        """401 when no authorization header is sent."""
        resp = client.raw().post("/api/team/invite", json={
            "email": "test@test.com",
            "role": "corretor",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/team/accept
# ---------------------------------------------------------------------------


class TestAcceptSuccess:
    def test_accept_success(self, client):
        """Creates auth user + profile + role when a valid token is accepted."""
        mock_auth_user = MagicMock()
        mock_auth_user.user = MagicMock()
        mock_auth_user.user.id = "new-user-123"
        client._mock_supabase.auth.admin = MagicMock()
        client._mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_auth_user)

        with patch("app.routers.team.validate_invitation", return_value=SAMPLE_INVITE), \
             patch("app.routers.team.accept_invitation") as mock_accept:
            resp = client.raw().post("/api/team/accept", json={
                "token": "abc123",
                "nome": "joao silva",
                "password": "senha123456",
            })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "new-user-123"
        assert data["nome"] == "Joao Silva"
        assert data["role"] == "corretor"
        mock_accept.assert_called_once()


class TestAcceptInvalidToken:
    def test_accept_invalid_token(self, client):
        """404 when token is invalid."""
        from fastapi import HTTPException

        with patch(
            "app.routers.team.validate_invitation",
            side_effect=HTTPException(status_code=404, detail="Convite nao encontrado"),
        ):
            resp = client.raw().post("/api/team/accept", json={
                "token": "bad-token",
                "nome": "Test User",
                "password": "senha123456",
            })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/team — List members
# ---------------------------------------------------------------------------


class TestListTeam:
    def test_list_team(self, client):
        client._mock_supabase.set_table_data("profiles", [SAMPLE_PROFILE])
        client._mock_supabase.set_table_data(
            "user_roles", [{"user_id": "p1", "role": "corretor"}]
        )
        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_team_empty(self, client):
        client._mock_supabase.set_table_data("profiles", [])
        resp = client.get("/api/team")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/team/invitations — List pending invitations
# ---------------------------------------------------------------------------


class TestListInvitations:
    def test_list_invitations(self, client):
        _mock_admin_role(client)

        with patch(
            "app.routers.team.list_pending_invitations",
            return_value=[SAMPLE_INVITE],
        ):
            resp = client.get("/api/team/invitations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["email"] == "new@test.com"


# ---------------------------------------------------------------------------
# DELETE /api/team/invitations/{id} — Cancel invitation
# ---------------------------------------------------------------------------


class TestCancelInvitation:
    def test_cancel_invitation(self, client):
        _mock_admin_role(client)

        with patch("app.routers.team.cancel_invitation") as mock_cancel:
            resp = client.delete("/api/team/invitations/inv-1")
        assert resp.status_code == 200
        mock_cancel.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE /api/team/{user_id} — Remove member
# ---------------------------------------------------------------------------


class TestRemoveMember:
    def test_remove_member(self, client):
        _mock_admin_role(client)
        client._mock_supabase.set_table_data("profiles", [
            {"id": "other-user", "nome": "To Remove", "email": "rm@test.com", "org_id": "test-org-123"},
        ])
        client._mock_supabase.set_table_data(
            "organizations", [{"owner_id": "someone-else"}]
        )

        with _mock_core_client(client._mock_supabase):
            resp = client.delete("/api/team/other-user")
        assert resp.status_code == 200

    def test_remove_self_forbidden(self, client):
        """Cannot remove yourself."""
        _mock_admin_role(client)
        # profiles must return data for the self-check to reach the "self" guard
        client._mock_supabase.set_table_data("profiles", [
            {"id": USER_ID, "nome": "Self", "email": "self@test.com", "org_id": "test-org-123"},
        ])
        resp = client.delete(f"/api/team/{USER_ID}")
        assert resp.status_code == 400

    def test_remove_not_found(self, client):
        """404 when member is not in the org."""
        _mock_admin_role(client)
        client._mock_supabase.set_table_data("profiles", [])
        resp = client.delete("/api/team/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/team/{user_id}/role — Change role
# ---------------------------------------------------------------------------


class TestChangeRole:
    def test_change_role(self, client):
        _mock_admin_role(client)
        client._mock_supabase.set_table_data("profiles", [
            {"id": "other-user", "nome": "Member"},
        ])
        client._mock_supabase.set_table_data("user_roles", [
            {"id": "role-1", "user_id": "other-user", "role": "corretor"},
        ])

        resp = client.patch("/api/team/other-user/role", json={"role": "coordenador"})
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "coordenador"

    def test_change_own_role_forbidden(self, client):
        _mock_admin_role(client)
        # profiles must have matching data for user check
        client._mock_supabase.set_table_data("profiles", [
            {"id": USER_ID, "nome": "Self"},
        ])
        resp = client.patch(f"/api/team/{USER_ID}/role", json={"role": "coordenador"})
        assert resp.status_code == 400
