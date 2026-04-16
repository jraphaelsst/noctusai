"""
End-to-end integration tests for the Therapy Platform invitation flows.

Tests the full invitation lifecycle across all 4 roles:
- platform_admin (admin_client)
- clinic_admin (clinic_admin_client)
- therapist (client)
- patient (patient_client)

Uses the mock fixtures from conftest.py with set_table_data and
set_sequential_responses to simulate multi-step flows.
"""
import pytest
from unittest.mock import MagicMock, patch

from noctusai_lib.testing import MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INVITE_RECORD = {
    "id": "inv-001",
    "email": "newuser@example.com",
    "role": "therapist",
    "invite_type": "platform_to_therapist",
    "clinic_id": None,
    "bound_to": None,
    "invited_by": "test-user-123",
    "token": "mock-token-abc",
    "status": "pending",
    "expires_at": "2099-12-31T23:59:59+00:00",
    "created_at": "2026-04-13T10:00:00+00:00",
}


def _clinic_invite(overrides=None):
    """Build a clinic-scoped invitation record."""
    base = {
        "id": "inv-002",
        "email": "therapist@clinic.com",
        "role": "therapist",
        "invite_type": "clinic_to_therapist",
        "clinic_id": "test-clinic-123",
        "bound_to": None,
        "invited_by": "clinic-admin-user",
        "token": "mock-token-clinic",
        "status": "pending",
        "expires_at": "2099-12-31T23:59:59+00:00",
        "created_at": "2026-04-13T10:00:00+00:00",
    }
    if overrides:
        base.update(overrides)
    return base


def _patient_invite(overrides=None):
    """Build a therapist-to-patient invitation record."""
    base = {
        "id": "inv-003",
        "email": "patient@example.com",
        "role": "patient",
        "invite_type": "therapist_to_patient",
        "clinic_id": None,
        "bound_to": "test-user-123",
        "invited_by": "test-user-123",
        "token": "mock-token-patient",
        "status": "pending",
        "expires_at": "2099-12-31T23:59:59+00:00",
        "created_at": "2026-04-13T10:00:00+00:00",
    }
    if overrides:
        base.update(overrides)
    return base


# ===================================================================
# 1. Admin invites clinic
# ===================================================================

class TestAdminInvitesClinic:
    """POST /api/invitations with type=platform_to_clinic by platform_admin."""

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_admin_invites_clinic_success(self, mock_log, mock_email, admin_client):
        invite = {
            **INVITE_RECORD,
            "invite_type": "platform_to_clinic",
            "role": "clinic_admin",
        }
        # 1st call: check pending → empty; 2nd call: insert → record
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),       # pending check
            MockSupabaseResponse(data=[invite]), # insert
        ])

        resp = admin_client.post("/api/invitations", json={
            "email": "clinic@example.com",
            "invite_type": "platform_to_clinic",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["invite_type"] == "platform_to_clinic"
        assert body["data"]["role"] == "clinic_admin"
        mock_log.assert_called_once()


# ===================================================================
# 2. Admin invites user (platform_to_therapist)
# ===================================================================

class TestAdminInvitesUser:
    """POST /api/invitations with type=platform_to_therapist by platform_admin."""

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_admin_invites_therapist_success(self, mock_log, mock_email, admin_client):
        invite = {**INVITE_RECORD, "invite_type": "platform_to_therapist"}
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),       # no pending
            MockSupabaseResponse(data=[invite]), # insert
        ])

        resp = admin_client.post("/api/invitations", json={
            "email": "newtherapist@example.com",
            "invite_type": "platform_to_therapist",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["invite_type"] == "platform_to_therapist"
        assert data["role"] == "therapist"

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_admin_invite_duplicate_email_409(self, mock_log, mock_email, admin_client):
        """If the email already has a pending invite, return 409."""
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[{"id": "existing"}]),  # pending exists
        ])

        resp = admin_client.post("/api/invitations", json={
            "email": "dup@example.com",
            "invite_type": "platform_to_therapist",
        })

        assert resp.status_code == 409
        assert "pendente" in resp.json()["error"]["message"]


# ===================================================================
# 3. Clinic admin invites therapist
# ===================================================================

class TestClinicAdminInvitesTherapist:
    """POST /api/invitations with type=clinic_to_therapist by clinic_admin."""

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_clinic_admin_invites_therapist_success(
        self, mock_log, mock_email, clinic_admin_client
    ):
        invite = _clinic_invite()
        clinic_admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),        # no pending
            MockSupabaseResponse(data=[invite]),  # insert
        ])
        # For email — clinics table lookup
        clinic_admin_client.mock_supabase.set_table_data("clinics", [
            {"nome": "Clinica Modelo"},
        ])

        resp = clinic_admin_client.post("/api/invitations", json={
            "email": "therapist@clinic.com",
            "invite_type": "clinic_to_therapist",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["invite_type"] == "clinic_to_therapist"
        assert data["clinic_id"] == "test-clinic-123"

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_clinic_admin_cannot_use_platform_invite_type(
        self, mock_log, mock_email, clinic_admin_client
    ):
        """clinic_admin cannot send platform_to_clinic invites."""
        resp = clinic_admin_client.post("/api/invitations", json={
            "email": "someone@example.com",
            "invite_type": "platform_to_clinic",
        })

        assert resp.status_code == 403


# ===================================================================
# 4. Therapist invites patient (bound)
# ===================================================================

class TestTherapistInvitesPatient:
    """POST /api/invitations with type=therapist_to_patient by therapist."""

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_therapist_invites_patient_with_binding(
        self, mock_log, mock_email, client
    ):
        invite = _patient_invite()
        client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),        # no pending
            MockSupabaseResponse(data=[invite]),  # insert
        ])

        resp = client.post("/api/invitations", json={
            "email": "patient@example.com",
            "invite_type": "therapist_to_patient",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["invite_type"] == "therapist_to_patient"
        assert data["role"] == "patient"
        # bound_to is set to the inviting therapist's user_id
        assert data["bound_to"] == "test-user-123"

    @patch("app.routers.invitations.send_product_invitation_email")
    @patch("app.routers.invitations.log_action")
    def test_therapist_cannot_invite_clinic(self, mock_log, mock_email, client):
        """Therapists cannot use platform_to_clinic or clinic_to_therapist types."""
        resp = client.post("/api/invitations", json={
            "email": "someone@example.com",
            "invite_type": "platform_to_clinic",
        })
        assert resp.status_code == 403

        resp2 = client.post("/api/invitations", json={
            "email": "someone@example.com",
            "invite_type": "clinic_to_therapist",
        })
        assert resp2.status_code == 403


# ===================================================================
# 5. Patient cannot invite
# ===================================================================

class TestPatientCannotInvite:
    """Patients should get 403 for all invite types."""

    def test_patient_invite_platform_to_clinic_403(self, patient_client):
        resp = patient_client.post("/api/invitations", json={
            "email": "someone@example.com",
            "invite_type": "platform_to_clinic",
        })
        assert resp.status_code == 403

    def test_patient_invite_therapist_to_patient_403(self, patient_client):
        resp = patient_client.post("/api/invitations", json={
            "email": "someone@example.com",
            "invite_type": "therapist_to_patient",
        })
        assert resp.status_code == 403

    def test_patient_invite_clinic_to_therapist_403(self, patient_client):
        resp = patient_client.post("/api/invitations", json={
            "email": "someone@example.com",
            "invite_type": "clinic_to_therapist",
        })
        assert resp.status_code == 403


# ===================================================================
# 6. Validate invitation token
# ===================================================================

class TestValidateInvitation:
    """GET /api/invitations/accept/validate?token=x — public endpoint."""

    def test_validate_returns_email_and_role(self, admin_client):
        invite = {**INVITE_RECORD, "role": "therapist", "status": "pending"}
        admin_client.mock_supabase.set_table_data("invitations", invite)

        resp = admin_client.raw().get(
            "/api/invitations/accept/validate",
            params={"token": "mock-token-abc"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == invite["email"]
        assert data["role"] == "Terapeuta"  # mapped via ROLE_LABELS

    def test_validate_invalid_token_404(self, admin_client):
        # .single() with empty data returns None
        admin_client.mock_supabase.set_table_data("invitations", [])

        resp = admin_client.raw().get(
            "/api/invitations/accept/validate",
            params={"token": "nonexistent"},
        )

        assert resp.status_code == 404

    def test_validate_already_accepted_400(self, admin_client):
        invite = {**INVITE_RECORD, "status": "accepted"}
        admin_client.mock_supabase.set_table_data("invitations", invite)

        resp = admin_client.raw().get(
            "/api/invitations/accept/validate",
            params={"token": "mock-token-abc"},
        )

        assert resp.status_code == 400


# ===================================================================
# 7. List invitations by role
# ===================================================================

class TestListInvitationsByRole:
    """GET /api/invitations — role-based filtering."""

    def test_admin_sees_all_invitations(self, admin_client):
        invites = [
            INVITE_RECORD,
            _clinic_invite(),
            _patient_invite(),
        ]
        admin_client.mock_supabase.set_table_data("invitations", invites)

        resp = admin_client.get("/api/invitations")

        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 3
        assert len(body["data"]) == 3

    def test_therapist_sees_own_invitations(self, client):
        invites = [_patient_invite()]
        client.mock_supabase.set_table_data("invitations", invites)

        resp = client.get("/api/invitations")

        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 1

    def test_patient_cannot_list_invitations(self, patient_client):
        resp = patient_client.get("/api/invitations")
        assert resp.status_code == 403

    def test_clinic_admin_sees_clinic_invitations(self, clinic_admin_client):
        invites = [_clinic_invite()]
        clinic_admin_client.mock_supabase.set_table_data("invitations", invites)

        resp = clinic_admin_client.get("/api/invitations")

        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 1


# ===================================================================
# 8. Cancel invitation
# ===================================================================

class TestCancelInvitation:
    """DELETE /api/invitations/{id} — cancellation with permission checks."""

    @patch("app.routers.invitations.log_action")
    def test_admin_cancels_any_invitation(self, mock_log, admin_client):
        invite = {**INVITE_RECORD, "status": "pending", "invited_by": "someone-else"}
        # 1st call: fetch by id → found; 2nd call: update status
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[invite]),  # pre-check
            MockSupabaseResponse(data=[{**invite, "status": "canceled"}]),  # update
        ])

        resp = admin_client.delete(f"/api/invitations/{invite['id']}")

        assert resp.status_code == 200
        assert "cancelado" in resp.json()["message"].lower()
        mock_log.assert_called_once()

    def test_cancel_nonexistent_invitation_404(self, admin_client):
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[]),  # not found
        ])

        resp = admin_client.delete("/api/invitations/nonexistent-id")
        assert resp.status_code == 404

    @patch("app.routers.invitations.log_action")
    def test_cancel_already_accepted_400(self, mock_log, admin_client):
        invite = {**INVITE_RECORD, "status": "accepted"}
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[invite]),  # found but not pending
        ])

        resp = admin_client.delete(f"/api/invitations/{invite['id']}")
        assert resp.status_code == 400
        assert "pendentes" in resp.json()["error"]["message"].lower()

    def test_therapist_can_only_cancel_own_invitations(self, client):
        # Invitation created by someone else
        invite = {**INVITE_RECORD, "invited_by": "other-therapist-id", "status": "pending"}
        client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[invite]),
        ])

        resp = client.delete(f"/api/invitations/{invite['id']}")
        assert resp.status_code == 403

    def test_patient_cannot_cancel(self, patient_client):
        invite = {**INVITE_RECORD, "status": "pending"}
        patient_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=[invite]),
        ])

        resp = patient_client.delete(f"/api/invitations/{invite['id']}")
        assert resp.status_code == 403


# ===================================================================
# 9. Accept creates correct profile type
# ===================================================================

class TestAcceptCreatesProfile:
    """POST /api/invitations/accept — creates auth user + profile."""

    def test_accept_therapist_creates_therapist_profile(self, admin_client):
        invite = {
            **INVITE_RECORD,
            "invite_type": "platform_to_therapist",
            "role": "therapist",
            "clinic_id": None,
            "bound_to": None,
        }
        # Sequential: validate (single), insert profile, mark accepted
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=invite),    # validate_invitation (single)
            MockSupabaseResponse(data=[{**invite, "status": "accepted"}]),  # accept
        ])
        admin_client.mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "new-user-456", "nome": "Maria Silva", "email": "newuser@example.com"},
        ])

        # Mock auth.admin.create_user
        mock_new_user = MagicMock()
        mock_new_user.id = "new-user-456"
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_new_user
        admin_client.mock_supabase.auth.admin.create_user = MagicMock(
            return_value=mock_auth_response
        )

        resp = admin_client.raw().post("/api/invitations/accept", json={
            "token": "mock-token-abc",
            "nome": "Maria Silva",
            "password": "securepass123",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "new-user-456"
        assert data["role"] == "therapist"

    def test_accept_clinic_invite_creates_clinic_and_admin(self, admin_client):
        invite = {
            **INVITE_RECORD,
            "invite_type": "platform_to_clinic",
            "role": "clinic_admin",
            "clinic_id": None,
        }
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=invite),    # validate
            MockSupabaseResponse(data=[{**invite, "status": "accepted"}]),  # accept
        ])
        admin_client.mock_supabase.set_table_data("clinics", [
            {"id": "new-clinic-789", "nome": "Clinica de Maria Silva"},
        ])

        mock_new_user = MagicMock()
        mock_new_user.id = "new-user-456"
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_new_user
        admin_client.mock_supabase.auth.admin.create_user = MagicMock(
            return_value=mock_auth_response
        )
        admin_client.mock_supabase.auth.admin.update_user_by_id = MagicMock()

        resp = admin_client.raw().post("/api/invitations/accept", json={
            "token": "mock-token-abc",
            "nome": "Maria Silva",
            "password": "securepass123",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "clinic_admin"
        # Verify update_user_by_id was called to set clinic_id
        admin_client.mock_supabase.auth.admin.update_user_by_id.assert_called_once()


# ===================================================================
# 10. Therapist-patient binding on accept
# ===================================================================

class TestTherapistPatientBinding:
    """Accept therapist_to_patient invite creates patient profile with bound_to."""

    def test_accept_patient_invite_binds_to_therapist(self, admin_client):
        invite = _patient_invite()
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=invite),    # validate
            MockSupabaseResponse(data=[{**invite, "status": "accepted"}]),  # accept
        ])
        admin_client.mock_supabase.set_table_data("patient_profiles", [
            {
                "user_id": "new-patient-789",
                "nome": "Joao Paciente",
                "email": "patient@example.com",
                "therapist_id": "test-user-123",
            },
        ])

        mock_new_user = MagicMock()
        mock_new_user.id = "new-patient-789"
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_new_user
        admin_client.mock_supabase.auth.admin.create_user = MagicMock(
            return_value=mock_auth_response
        )

        resp = admin_client.raw().post("/api/invitations/accept", json={
            "token": "mock-token-patient",
            "nome": "Joao Paciente",
            "password": "securepass456",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "patient"
        assert data["user_id"] == "new-patient-789"

    def test_accept_patient_invite_without_binding(self, admin_client):
        """clinic_to_patient invite without bound_to still creates patient profile."""
        invite = {
            **INVITE_RECORD,
            "id": "inv-no-bind",
            "invite_type": "clinic_to_patient",
            "role": "patient",
            "clinic_id": "test-clinic-123",
            "bound_to": None,
        }
        admin_client.mock_supabase.set_sequential_responses("invitations", [
            MockSupabaseResponse(data=invite),
            MockSupabaseResponse(data=[{**invite, "status": "accepted"}]),
        ])
        admin_client.mock_supabase.set_table_data("patient_profiles", [
            {
                "user_id": "new-patient-no-bind",
                "nome": "Ana Paciente",
                "email": "newuser@example.com",
                "clinic_id": "test-clinic-123",
            },
        ])

        mock_new_user = MagicMock()
        mock_new_user.id = "new-patient-no-bind"
        mock_auth_response = MagicMock()
        mock_auth_response.user = mock_new_user
        admin_client.mock_supabase.auth.admin.create_user = MagicMock(
            return_value=mock_auth_response
        )

        resp = admin_client.raw().post("/api/invitations/accept", json={
            "token": "mock-token-abc",
            "nome": "Ana Paciente",
            "password": "securepass789",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "patient"
