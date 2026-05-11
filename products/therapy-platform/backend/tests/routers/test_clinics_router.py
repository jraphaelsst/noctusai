"""
Tests for the Clinics Router — directory, profile, settings, therapist management, invites.
"""
import pytest
from unittest.mock import MagicMock
from gotrue.errors import AuthApiError


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_CLINIC = {
    "id": "clinic-001",
    "name": "Clínica Bem Estar",
    "cnpj": "12345678000190",
    "responsible_person": "Dr. João",
    "contact_email": "clinica@test.com",
    "phone": "11999999999",
    "description": "Clínica especializada",
    "tagline": "Bem estar para todos",
    "specialties_offered": ["ansiedade", "depressão"],
    "is_approved": True,
    "created_at": "2026-04-01T10:00:00Z",
    "is_active": True,
}

SAMPLE_CLINIC_2 = {
    "id": "clinic-002",
    "name": "Espaço Mente",
    "cnpj": "98765432000110",
    "responsible_person": "Dra. Ana",
    "contact_email": "espaco@test.com",
    "phone": "11888888888",
    "is_approved": True,
    "created_at": "2026-04-01T11:00:00Z",
    "is_active": True,
}

SAMPLE_THERAPIST = {
    "user_id": "therapist-in-clinic",
    "clinic_id": "clinic-001",
    "crp": "06/999999",
    "bio": "Terapeuta da clínica",
    "is_approved": True,
    "is_active": True,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_CLINIC_SETTINGS = {
    "clinic_id": "test-clinic-123",
    "bank_name": "Banco do Brasil",
    "bank_agency": "1234",
    "bank_account": "56789-0",
    "pix_key": "clinica@pix.com",
    "default_commission_pct_clinic_sourced": 30,
    "default_commission_pct_therapist_sourced": 15,
}

SAMPLE_THERAPIST_CONFIG = {
    "clinic_id": "test-clinic-123",
    "therapist_id": "therapist-in-clinic",
    "pricing_policy": "therapist_sets",
    "commission_override_clinic_sourced": None,
    "commission_override_therapist_sourced": None,
    "clinic_set_default_price": None,
}


# ---------------------------------------------------------------------------
# List Clinics (Directory)
# ---------------------------------------------------------------------------

class TestListClinics:
    def test_list_clinics_returns_data(self, client):
        client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC, SAMPLE_CLINIC_2])
        resp = client.get("/api/clinics")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "pagination" in body

    def test_list_clinics_empty(self, client):
        client._mock_supabase.set_table_data("clinics", [])
        resp = client.get("/api/clinics")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_clinics_with_busca(self, client):
        client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC])
        resp = client.get("/api/clinics?busca=Bem+Estar")
        assert resp.status_code == 200

    def test_list_clinics_with_specialty(self, client):
        client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC])
        resp = client.get("/api/clinics?specialty=ansiedade")
        assert resp.status_code == 200

    def test_list_clinics_pagination(self, client):
        client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC])
        resp = client.get("/api/clinics?page=1&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 1

    def test_list_clinics_no_auth(self, client):
        resp = client._tc.get("/api/clinics")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get Clinic
# ---------------------------------------------------------------------------

class TestGetClinic:
    def test_get_clinic_found(self, client):
        client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC])
        client._mock_supabase.set_table_data("therapist_profiles", [SAMPLE_THERAPIST])
        client._mock_supabase.set_table_data("clinic_reviews", [])
        resp = client.get("/api/clinics/clinic-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Clínica Bem Estar"
        assert "therapist_count" in data
        assert "review_count" in data

    def test_get_clinic_with_reviews(self, client):
        client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC])
        client._mock_supabase.set_table_data("therapist_profiles", [])
        client._mock_supabase.set_table_data("clinic_reviews", [
            {"star_rating": 5, "clinic_id": "clinic-001"},
            {"star_rating": 3, "clinic_id": "clinic-001"},
        ])
        resp = client.get("/api/clinics/clinic-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["avg_rating"] == 4.0
        assert data["review_count"] == 2

    def test_get_clinic_not_found(self, client):
        client._mock_supabase.set_table_data("clinics", [])
        resp = client.get("/api/clinics/nonexistent-id")
        assert resp.status_code == 404

    def test_get_clinic_no_auth(self, client):
        resp = client._tc.get("/api/clinics/clinic-001")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Update Clinic
# ---------------------------------------------------------------------------

class TestUpdateClinic:
    def test_update_own_clinic(self, clinic_admin_client):
        updated = {**SAMPLE_CLINIC, "id": "test-clinic-123", "name": "Clínica Atualizada"}
        clinic_admin_client._mock_supabase.set_table_data("clinics", [updated])
        resp = clinic_admin_client.patch(
            "/api/clinics/test-clinic-123",
            json={"name": "Clínica Atualizada"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Clínica Atualizada"

    def test_update_other_clinic_forbidden(self, clinic_admin_client):
        """Clinic admin cannot update another clinic."""
        resp = clinic_admin_client.patch(
            "/api/clinics/other-clinic-456",
            json={"name": "Hack"},
        )
        assert resp.status_code == 403

    def test_update_clinic_as_therapist_forbidden(self, client):
        """Therapist cannot update a clinic profile."""
        resp = client.patch(
            "/api/clinics/clinic-001",
            json={"name": "Hack"},
        )
        assert resp.status_code == 403

    def test_update_clinic_no_auth(self, client):
        resp = client._tc.patch(
            "/api/clinics/clinic-001",
            json={"name": "No auth"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List Clinic Therapists
# ---------------------------------------------------------------------------

class TestListClinicTherapists:
    def test_list_clinic_therapists(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [SAMPLE_THERAPIST])
        resp = client.get("/api/clinics/clinic-001/therapists")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["clinic_id"] == "clinic-001"

    def test_list_clinic_therapists_empty(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = client.get("/api/clinics/clinic-001/therapists")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_clinic_therapists_no_auth(self, client):
        resp = client._tc.get("/api/clinics/clinic-001/therapists")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invite Therapist
# ---------------------------------------------------------------------------

class TestInviteTherapist:
    def test_invite_therapist_success(self, clinic_admin_client):
        # Mock clinic exists
        clinic_admin_client._mock_supabase.set_table_data("clinics", [
            {**SAMPLE_CLINIC, "id": "test-clinic-123"},
        ])

        # Mock user creation
        mock_user = MagicMock()
        mock_user.id = "invited-therapist-001"
        mock_user.email = "invited@example.com"
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        clinic_admin_client._mock_supabase.auth.admin.create_user = MagicMock(
            return_value=mock_user_resp
        )

        resp = clinic_admin_client.post(
            "/api/clinics/test-clinic-123/invite",
            json={"email": "invited@example.com", "nome": "Dr. Novo"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == "invited@example.com"
        assert data["clinic_id"] == "test-clinic-123"

    def test_invite_therapist_other_clinic_forbidden(self, clinic_admin_client):
        """Clinic admin cannot invite to another clinic."""
        resp = clinic_admin_client.post(
            "/api/clinics/other-clinic-456/invite",
            json={"email": "invited@example.com", "nome": "Dr. Novo"},
        )
        assert resp.status_code == 403

    def test_invite_therapist_as_therapist_forbidden(self, client):
        resp = client.post(
            "/api/clinics/clinic-001/invite",
            json={"email": "invited@example.com", "nome": "Dr. Novo"},
        )
        assert resp.status_code == 403

    def test_invite_therapist_duplicate_email(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data("clinics", [
            {**SAMPLE_CLINIC, "id": "test-clinic-123"},
        ])
        clinic_admin_client._mock_supabase.auth.admin.create_user = MagicMock(
            side_effect=AuthApiError("User already registered", 400, "user_already_exists")
        )
        resp = clinic_admin_client.post(
            "/api/clinics/test-clinic-123/invite",
            json={"email": "existing@example.com", "nome": "Dr. Existente"},
        )
        assert resp.status_code == 409

    def test_invite_therapist_no_auth(self, client):
        resp = client._tc.post(
            "/api/clinics/clinic-001/invite",
            json={"email": "invited@example.com", "nome": "Dr. Novo"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Clinic Settings
# ---------------------------------------------------------------------------

class TestClinicSettings:
    def test_get_settings(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data(
            "clinic_settings", [SAMPLE_CLINIC_SETTINGS]
        )
        resp = clinic_admin_client.get("/api/clinics/settings")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bank_name"] == "Banco do Brasil"

    def test_get_settings_not_found(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data("clinic_settings", [])
        resp = clinic_admin_client.get("/api/clinics/settings")
        assert resp.status_code == 404

    def test_get_settings_as_therapist_forbidden(self, client):
        resp = client.get("/api/clinics/settings")
        assert resp.status_code == 403

    def test_update_settings(self, clinic_admin_client):
        updated = {**SAMPLE_CLINIC_SETTINGS, "pix_key": "novo@pix.com"}
        clinic_admin_client._mock_supabase.set_table_data("clinic_settings", [updated])
        resp = clinic_admin_client.patch(
            "/api/clinics/settings",
            json={"pix_key": "novo@pix.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["pix_key"] == "novo@pix.com"

    def test_update_settings_as_therapist_forbidden(self, client):
        resp = client.patch(
            "/api/clinics/settings",
            json={"pix_key": "hack@pix.com"},
        )
        assert resp.status_code == 403

    def test_get_settings_no_auth(self, client):
        resp = client._tc.get("/api/clinics/settings")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Therapist Config (per-therapist within clinic)
# ---------------------------------------------------------------------------

class TestTherapistConfig:
    def test_get_therapist_config(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data(
            "clinic_therapist_config", [SAMPLE_THERAPIST_CONFIG]
        )
        resp = clinic_admin_client.get(
            "/api/clinics/therapists/therapist-in-clinic/config"
        )
        assert resp.status_code == 200

    def test_get_therapist_config_defaults(self, clinic_admin_client):
        """When no config exists, should return defaults."""
        clinic_admin_client._mock_supabase.set_table_data("clinic_therapist_config", [])
        resp = clinic_admin_client.get(
            "/api/clinics/therapists/therapist-in-clinic/config"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pricing_policy"] == "therapist_sets"

    def test_update_therapist_config(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "therapist-in-clinic", "clinic_id": "test-clinic-123"},
        ])
        clinic_admin_client._mock_supabase.set_table_data("clinic_therapist_config", [
            {**SAMPLE_THERAPIST_CONFIG, "pricing_policy": "clinic_sets"},
        ])
        resp = clinic_admin_client.patch(
            "/api/clinics/therapists/therapist-in-clinic/config",
            json={"pricing_policy": "clinic_sets"},
        )
        assert resp.status_code == 200

    def test_therapist_config_as_therapist_forbidden(self, client):
        resp = client.get(
            "/api/clinics/therapists/therapist-in-clinic/config"
        )
        assert resp.status_code == 403
