"""
Tests for the Auth Router — registration, login, password recovery, /me.
"""
import pytest
from unittest.mock import MagicMock, patch
from gotrue.errors import AuthApiError

from tests.conftest import MockUser, MockUserResponse


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

PATIENT_REGISTER = {
    "nome": "Maria Silva",
    "email": "maria@example.com",
    "password": "senha123",
    "phone": "11999999999",
}

THERAPIST_REGISTER = {
    "nome": "Dr. João Santos",
    "email": "joao@example.com",
    "password": "senha123",
    "crp": "06/123456",
    "bio": "Psicólogo clínico",
    "specialties": ["ansiedade", "depressão"],
    "approaches": ["TCC", "psicanálise"],
    "photo_url": None,
    "default_session_price": 200.00,
}

CLINIC_REGISTER = {
    "nome": "Admin Clínica",
    "email": "admin@clinica.com",
    "password": "senha123",
    "clinic_name": "Clínica Bem Estar",
    "cnpj": "12345678000190",
    "responsible_person": "Dr. João",
    "contact_email": "contato@clinica.com",
    "phone": "11999999999",
}

LOGIN_PAYLOAD = {
    "email": "maria@example.com",
    "password": "senha123",
}


# ---------------------------------------------------------------------------
# Patient Registration
# ---------------------------------------------------------------------------

class TestRegisterPatient:
    def test_register_patient_success(self, client):
        # Mock admin.create_user to return a user
        mock_user = MagicMock()
        mock_user.id = "new-patient-001"
        mock_user.email = "maria@example.com"
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        client._mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_user_resp)

        resp = client.post("/api/auth/register/patient", json=PATIENT_REGISTER)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "patient"
        assert data["email"] == "maria@example.com"

    def test_register_patient_missing_fields(self, client):
        resp = client.post("/api/auth/register/patient", json={"nome": "Maria"})
        assert resp.status_code == 422

    def test_register_patient_duplicate_email(self, client):
        client._mock_supabase.auth.admin.create_user = MagicMock(
            side_effect=AuthApiError("User already registered", 400, "user_already_exists")
        )
        resp = client.post("/api/auth/register/patient", json=PATIENT_REGISTER)
        assert resp.status_code == 409

    def test_register_patient_short_password(self, client):
        payload = {**PATIENT_REGISTER, "password": "12345"}
        resp = client.post("/api/auth/register/patient", json=payload)
        assert resp.status_code == 422

    def test_register_patient_invalid_email(self, client):
        payload = {**PATIENT_REGISTER, "email": "not-an-email"}
        resp = client.post("/api/auth/register/patient", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Therapist Registration
# ---------------------------------------------------------------------------

class TestRegisterTherapist:
    def test_register_therapist_success(self, client):
        mock_user = MagicMock()
        mock_user.id = "new-therapist-001"
        mock_user.email = "joao@example.com"
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        client._mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_user_resp)

        resp = client.post("/api/auth/register/therapist", json=THERAPIST_REGISTER)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "therapist"
        assert data["is_approved"] is False

    def test_register_therapist_missing_crp(self, client):
        payload = {k: v for k, v in THERAPIST_REGISTER.items() if k != "crp"}
        resp = client.post("/api/auth/register/therapist", json=payload)
        assert resp.status_code == 422

    def test_register_therapist_missing_price(self, client):
        payload = {k: v for k, v in THERAPIST_REGISTER.items() if k != "default_session_price"}
        resp = client.post("/api/auth/register/therapist", json=payload)
        assert resp.status_code == 422

    def test_register_therapist_duplicate_email(self, client):
        client._mock_supabase.auth.admin.create_user = MagicMock(
            side_effect=AuthApiError("User already registered", 400, "user_already_exists")
        )
        resp = client.post("/api/auth/register/therapist", json=THERAPIST_REGISTER)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Clinic Registration
# ---------------------------------------------------------------------------

class TestRegisterClinic:
    def test_register_clinic_success(self, client):
        # Mock clinic insert to return an ID
        client._mock_supabase.set_table_data("clinics", [{"id": "clinic-new-001"}])

        mock_user = MagicMock()
        mock_user.id = "new-admin-001"
        mock_user.email = "admin@clinica.com"
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        client._mock_supabase.auth.admin.create_user = MagicMock(return_value=mock_user_resp)

        resp = client.post("/api/auth/register/clinic", json=CLINIC_REGISTER)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "clinic_admin"
        assert data["is_approved"] is False

    def test_register_clinic_missing_cnpj(self, client):
        payload = {k: v for k, v in CLINIC_REGISTER.items() if k != "cnpj"}
        resp = client.post("/api/auth/register/clinic", json=payload)
        assert resp.status_code == 422

    def test_register_clinic_duplicate_email(self, client):
        client._mock_supabase.set_table_data("clinics", [{"id": "clinic-new-001"}])
        client._mock_supabase.auth.admin.create_user = MagicMock(
            side_effect=AuthApiError("User already registered", 400, "user_already_exists")
        )
        resp = client.post("/api/auth/register/clinic", json=CLINIC_REGISTER)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        mock_session = MagicMock()
        mock_session.access_token = "access-token-abc"
        mock_session.refresh_token = "refresh-token-xyz"
        mock_user = MagicMock()
        mock_user.id = "user-001"
        mock_user.email = "maria@example.com"
        mock_user.user_metadata = {"role": "patient", "nome": "Maria"}
        mock_result = MagicMock()
        mock_result.session = mock_session
        mock_result.user = mock_user

        client._mock_supabase.auth.sign_in_with_password = MagicMock(return_value=mock_result)

        resp = client.post("/api/auth/login", json=LOGIN_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"] == "access-token-abc"
        assert data["role"] == "patient"

    def test_login_invalid_credentials(self, client):
        client._mock_supabase.auth.sign_in_with_password = MagicMock(
            side_effect=AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        )
        resp = client.post("/api/auth/login", json=LOGIN_PAYLOAD)
        assert resp.status_code == 401

    def test_login_missing_email(self, client):
        resp = client.post("/api/auth/login", json={"password": "senha123"})
        assert resp.status_code == 422

    def test_login_missing_password(self, client):
        resp = client.post("/api/auth/login", json={"email": "test@example.com"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

class TestForgotPassword:
    def test_forgot_password_success(self, client):
        client._mock_supabase.auth.reset_password_email = MagicMock()
        resp = client.post("/api/auth/forgot-password", json={"email": "maria@example.com"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "link" in data["message"].lower() or "enviado" in data["message"].lower()

    def test_forgot_password_nonexistent_email(self, client):
        """Should still return 200 (do not reveal if email exists)."""
        client._mock_supabase.auth.reset_password_email = MagicMock(
            side_effect=AuthApiError("User not found", 404, "user_not_found")
        )
        resp = client.post("/api/auth/forgot-password", json={"email": "nonexistent@example.com"})
        assert resp.status_code == 200

    def test_forgot_password_invalid_email(self, client):
        resp = client.post("/api/auth/forgot-password", json={"email": "not-valid"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get Me
# ---------------------------------------------------------------------------

class TestGetMe:
    def test_get_me_therapist(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "test-user-123", "crp": "06/123456", "is_approved": True},
        ])
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "test-user-123"
        assert data["role"] == "therapist"

    def test_get_me_patient(self, patient_client):
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "test-user-123", "phone": "11999999999"},
        ])
        resp = patient_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "patient"

    def test_get_me_admin(self, admin_client):
        resp = admin_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "platform_admin"
        assert data.get("is_admin") is True


# ---------------------------------------------------------------------------
# Auth Required
# ---------------------------------------------------------------------------

class TestAuthRequired:
    def test_get_me_no_auth(self, client):
        resp = client._tc.get("/api/auth/me")
        assert resp.status_code == 401
