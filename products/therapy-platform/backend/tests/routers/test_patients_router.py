"""
Tests for the Patients Router — listing, profile detail, profile update.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PATIENT = {
    "user_id": "patient-001",
    "current_therapist_id": "test-user-123",
    "origin": "platform",
    "clinic_id": None,
    "phone": "11888888888",
    "created_at": "2026-04-01T10:00:00Z",
    "is_active": True,
}

SAMPLE_PATIENT_2 = {
    "user_id": "patient-002",
    "current_therapist_id": "test-user-123",
    "origin": "self_registration",
    "clinic_id": None,
    "phone": "11777777777",
    "created_at": "2026-04-01T11:00:00Z",
    "is_active": True,
}


# ---------------------------------------------------------------------------
# List Patients
# ---------------------------------------------------------------------------

class TestListPatients:
    def test_list_patients_as_therapist(self, client):
        client._mock_supabase.set_table_data(
            "patient_profiles", [SAMPLE_PATIENT, SAMPLE_PATIENT_2]
        )
        resp = client.get("/api/patients")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "pagination" in body

    def test_list_patients_empty(self, client):
        client._mock_supabase.set_table_data("patient_profiles", [])
        resp = client.get("/api/patients")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_patients_with_busca(self, client):
        client._mock_supabase.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        resp = client.get("/api/patients?busca=888")
        assert resp.status_code == 200

    def test_list_patients_pagination(self, client):
        client._mock_supabase.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        resp = client.get("/api/patients?page=1&page_size=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 5

    def test_list_patients_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/patients")
        assert resp.status_code == 403

    def test_list_patients_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        resp = admin_client.get("/api/patients")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_patients_as_clinic_admin(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data(
            "patient_profiles", [SAMPLE_PATIENT]
        )
        resp = clinic_admin_client.get("/api/patients")
        assert resp.status_code == 200

    def test_list_patients_no_auth(self, client):
        resp = client._tc.get("/api/patients")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get Patient
# ---------------------------------------------------------------------------

class TestGetPatient:
    def test_get_patient_found_as_therapist(self, client):
        """Therapist can see their own patient."""
        client._mock_supabase.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        resp = client.get("/api/patients/patient-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "patient-001"

    def test_get_patient_not_found(self, client):
        client._mock_supabase.set_table_data("patient_profiles", [])
        resp = client.get("/api/patients/nonexistent-id")
        assert resp.status_code == 404

    def test_get_own_patient_profile(self, patient_client):
        """Patient can view their own profile."""
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {**SAMPLE_PATIENT, "user_id": "test-user-123"},
        ])
        resp = patient_client.get("/api/patients/test-user-123")
        assert resp.status_code == 200

    def test_get_other_patient_forbidden_as_patient(self, patient_client):
        """Patient cannot view another patient's profile."""
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {**SAMPLE_PATIENT, "user_id": "other-patient"},
        ])
        resp = patient_client.get("/api/patients/other-patient")
        assert resp.status_code == 403

    def test_get_patient_as_unrelated_therapist(self, client):
        """Therapist cannot view a patient not assigned to them."""
        unrelated_patient = {
            **SAMPLE_PATIENT,
            "current_therapist_id": "other-therapist-999",
        }
        client._mock_supabase.set_table_data("patient_profiles", [unrelated_patient])
        resp = client.get("/api/patients/patient-001")
        assert resp.status_code == 403

    def test_get_patient_no_auth(self, client):
        resp = client._tc.get("/api/patients/patient-001")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Update Patient
# ---------------------------------------------------------------------------

class TestUpdatePatient:
    def test_update_own_profile(self, patient_client):
        updated = {**SAMPLE_PATIENT, "user_id": "test-user-123", "phone": "11666666666"}
        patient_client._mock_supabase.set_table_data("patient_profiles", [updated])
        resp = patient_client.patch(
            "/api/patients/test-user-123",
            json={"phone": "11666666666"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["phone"] == "11666666666"

    def test_update_other_patient_forbidden(self, patient_client):
        resp = patient_client.patch(
            "/api/patients/other-patient-id",
            json={"phone": "11555555555"},
        )
        assert resp.status_code == 403

    def test_update_patient_as_therapist_forbidden(self, client):
        """Therapist role cannot update patient profiles."""
        resp = client.patch(
            "/api/patients/patient-001",
            json={"phone": "11555555555"},
        )
        assert resp.status_code == 403

    def test_update_patient_no_auth(self, client):
        resp = client._tc.patch(
            "/api/patients/patient-001",
            json={"phone": "11555555555"},
        )
        assert resp.status_code == 401
