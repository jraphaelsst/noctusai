"""
Tests for Invitations router — /api/invitations

Covers: create invitation (admin, therapist, patient-forbidden),
accept invitation, list invitations (admin vs therapist filtering),
validate token, and cancel invitation.
"""
import pytest
from unittest.mock import MagicMock, patch
from noctusai_shared.testing import MockSupabaseResponse

# Default MockUser id
USER_ID = "test-user-123"


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_INVITATION = {
    "id": "inv-1",
    "email": "newuser@test.com",
    "role": "therapist",
    "invite_type": "platform_to_therapist",
    "clinic_id": None,
    "bound_to": None,
    "invited_by": USER_ID,
    "token": "tok-abc123",
    "status": "pending",
    "created_at": "2026-01-01T00:00:00",
}

SAMPLE_PATIENT_INVITE = {
    "id": "inv-2",
    "email": "patient@test.com",
    "role": "patient",
    "invite_type": "therapist_to_patient",
    "clinic_id": None,
    "bound_to": USER_ID,
    "invited_by": USER_ID,
    "token": "tok-def456",
    "status": "pending",
    "created_at": "2026-01-01T00:00:00",
}


def _mock_email():
    return patch("app.routers.invitations.send_product_invitation_email", MagicMock())


# ---------------------------------------------------------------------------
# POST /api/invitations — Create invitation
# ---------------------------------------------------------------------------


class TestCreateInvitationAdmin:
    def test_create_invitation_admin(self, admin_client):
        """platform_admin can create any invitation type."""
        admin_client._mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),                       # pending check
            MockSupabaseResponse(data=[SAMPLE_INVITATION]),      # insert
        ])

        with _mock_email(), \
             patch("app.routers.invitations.generate_invite_token", return_value="tok-abc123"):
            resp = admin_client.post("/api/invitations", json={
                "email": "newuser@test.com",
                "invite_type": "platform_to_therapist",
            })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == "newuser@test.com"


class TestCreateInvitationTherapist:
    def test_create_invitation_therapist(self, client):
        """Therapist can invite a patient (therapist_to_patient)."""
        client._mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),
            MockSupabaseResponse(data=[SAMPLE_PATIENT_INVITE]),
        ])

        with _mock_email(), \
             patch("app.routers.invitations.generate_invite_token", return_value="tok-def456"):
            resp = client.post("/api/invitations", json={
                "email": "patient@test.com",
                "invite_type": "therapist_to_patient",
            })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "patient"


class TestCreateInvitationPatientForbidden:
    def test_create_invitation_patient_forbidden(self, patient_client):
        """Patients cannot create invitations."""
        resp = patient_client.post("/api/invitations", json={
            "email": "someone@test.com",
            "invite_type": "therapist_to_patient",
        })
        assert resp.status_code == 403


class TestCreateInvitationDuplicate:
    def test_create_invitation_duplicate(self, admin_client):
        """409 when a pending invite already exists for that email."""
        admin_client._mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[{"id": "existing-inv"}]),
        ])

        resp = admin_client.post("/api/invitations", json={
            "email": "existing@test.com",
            "invite_type": "platform_to_therapist",
        })
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/invitations/accept/validate — Validate token (public)
# ---------------------------------------------------------------------------


class TestValidateToken:
    def test_validate_token(self, client):
        """Public endpoint returns invitation info."""
        with patch("app.routers.invitations.validate_invitation", return_value=SAMPLE_INVITATION):
            resp = client.raw().get("/api/invitations/accept/validate?token=tok-abc123")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == "newuser@test.com"


# ---------------------------------------------------------------------------
# POST /api/invitations/accept — Accept invitation
# ---------------------------------------------------------------------------


class TestAcceptInvitation:
    def test_accept_invitation(self, client):
        """Accepting a valid invitation creates a user and profile."""
        invitation_data = {
            **SAMPLE_INVITATION,
            "invite_type": "platform_to_therapist",
            "role": "therapist",
        }

        mock_auth_user = MagicMock()
        mock_auth_user.user = MagicMock()
        mock_auth_user.user.id = "new-user-789"
        client._mock_supabase.auth.admin = MagicMock()
        client._mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_auth_user)

        client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "new-user-789", "nome": "Novo Terapeuta"},
        ])

        with patch("app.routers.invitations.validate_invitation", return_value=invitation_data), \
             patch("app.routers.invitations.accept_invitation") as mock_accept:
            resp = client.raw().post("/api/invitations/accept", json={
                "token": "tok-abc123",
                "nome": "Novo Terapeuta",
                "password": "senha123456",
            })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "new-user-789"
        assert data["role"] == "therapist"
        mock_accept.assert_called_once()

    def test_accept_invalid_token(self, client):
        """404 when token is invalid."""
        from fastapi import HTTPException

        with patch(
            "app.routers.invitations.validate_invitation",
            side_effect=HTTPException(status_code=404, detail="Convite nao encontrado"),
        ):
            resp = client.raw().post("/api/invitations/accept", json={
                "token": "bad-token",
                "nome": "Test",
                "password": "senha123456",
            })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/invitations — List invitations
# ---------------------------------------------------------------------------


class TestListInvitationsAdmin:
    def test_list_invitations_admin(self, admin_client):
        """platform_admin sees all invitations."""
        admin_client._mock_supabase.set_table_data("invitations", [
            SAMPLE_INVITATION,
            SAMPLE_PATIENT_INVITE,
        ])

        resp = admin_client.get("/api/invitations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)


class TestListInvitationsTherapist:
    def test_list_invitations_therapist(self, client):
        """Therapist sees only invitations they sent (filtered by invited_by)."""
        client._mock_supabase.set_table_data("invitations", [SAMPLE_PATIENT_INVITE])

        resp = client.get("/api/invitations")
        assert resp.status_code == 200


class TestListInvitationsPatientForbidden:
    def test_list_invitations_patient_forbidden(self, patient_client):
        """Patients cannot list invitations."""
        resp = patient_client.get("/api/invitations")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/invitations/{id} — Cancel invitation
# ---------------------------------------------------------------------------


class TestCancelInvitation:
    def test_cancel_invitation_admin(self, admin_client):
        """platform_admin can cancel any pending invitation."""
        admin_client._mock_supabase.set_table_data("invitations", [
            {"id": "inv-1", "status": "pending", "clinic_id": None, "invited_by": "other"},
        ])

        resp = admin_client.delete("/api/invitations/inv-1")
        assert resp.status_code == 200

    def test_cancel_invitation_therapist_own(self, client):
        """Therapist can cancel invitations they sent."""
        client._mock_supabase.set_table_data("invitations", [
            {"id": "inv-2", "status": "pending", "clinic_id": None, "invited_by": USER_ID},
        ])

        resp = client.delete("/api/invitations/inv-2")
        assert resp.status_code == 200

    def test_cancel_invitation_therapist_others_forbidden(self, client):
        """Therapist cannot cancel invitations sent by someone else."""
        client._mock_supabase.set_table_data("invitations", [
            {"id": "inv-3", "status": "pending", "clinic_id": None, "invited_by": "other-user"},
        ])

        resp = client.delete("/api/invitations/inv-3")
        assert resp.status_code == 403

    def test_cancel_not_found(self, admin_client):
        """404 when invitation does not exist."""
        admin_client._mock_supabase.set_table_data("invitations", [])

        resp = admin_client.delete("/api/invitations/nonexistent")
        assert resp.status_code == 404

    def test_cancel_already_accepted(self, admin_client):
        """400 when invitation is no longer pending."""
        admin_client._mock_supabase.set_table_data("invitations", [
            {"id": "inv-4", "status": "accepted", "clinic_id": None, "invited_by": USER_ID},
        ])

        resp = admin_client.delete("/api/invitations/inv-4")
        assert resp.status_code == 400
