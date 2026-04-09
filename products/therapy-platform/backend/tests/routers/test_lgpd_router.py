"""
Tests for the LGPD Router — data deletion endpoints.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_WALLET = {"id": "wallet-001", "user_id": "test-user-123", "balance": 0}

SAMPLE_SESSION = {
    "id": "session-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "status": "completed",
}

SAMPLE_OBSERVATION = {
    "id": "obs-001",
    "session_id": "session-001",
    "therapist_id": "test-user-123",
    "content": "Paciente apresentou melhora.",
}


# ---------------------------------------------------------------------------
# Patient Data Deletion
# ---------------------------------------------------------------------------

class TestPatientDeleteMyData:
    def test_delete_my_data_success(self, patient_client):
        patient_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        patient_client._mock_supabase.set_table_data("wallet_movements", [])
        patient_client._mock_supabase.set_table_data("messages", [])
        patient_client._mock_supabase.set_table_data("conversation_participants", [])
        patient_client._mock_supabase.set_table_data("patient_longitudinal_analyses", [])
        patient_client._mock_supabase.set_table_data("patient_session_notes", [])
        patient_client._mock_supabase.set_table_data("patient_profiles", [])
        patient_client._mock_supabase.set_table_data("action_log", [])

        resp = patient_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR EXCLUSAO",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "deleted_tables" in data
        assert "kept_tables" in data
        assert "patient_profiles" in data["deleted_tables"]
        assert "session_records" in data["kept_tables"]

    def test_delete_my_data_wrong_confirmation(self, patient_client):
        resp = patient_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR",
        })
        assert resp.status_code == 422

    def test_delete_my_data_empty_confirmation(self, patient_client):
        resp = patient_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "",
        })
        assert resp.status_code == 422

    def test_delete_my_data_as_therapist_forbidden(self, client):
        resp = client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR EXCLUSAO",
        })
        assert resp.status_code == 403

    def test_delete_my_data_as_admin_forbidden(self, admin_client):
        resp = admin_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR EXCLUSAO",
        })
        assert resp.status_code == 403

    def test_delete_my_data_no_auth(self, patient_client):
        resp = patient_client._tc.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR EXCLUSAO",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Therapist Data Deletion
# ---------------------------------------------------------------------------

class TestTherapistDeleteData:
    def test_delete_session(self, client):
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION])
        client._mock_supabase.set_table_data("session_observations", [])
        client._mock_supabase.set_table_data("session_summary_versions", [])

        resp = client.post("/api/lgpd/delete-data/session/session-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "session_records" in data["deleted"]

    def test_delete_observation(self, client):
        client._mock_supabase.set_table_data("session_observations", [SAMPLE_OBSERVATION])

        resp = client.post("/api/lgpd/delete-data/observation/obs-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "session_observations" in data["deleted"]

    def test_delete_all(self, client):
        client._mock_supabase.set_table_data("session_summary_versions", [])
        client._mock_supabase.set_table_data("session_observations", [])
        client._mock_supabase.set_table_data("session_records", [])
        client._mock_supabase.set_table_data("messages", [])
        client._mock_supabase.set_table_data("conversation_participants", [])
        client._mock_supabase.set_table_data("wallets", [])
        client._mock_supabase.set_table_data("wallet_movements", [])
        client._mock_supabase.set_table_data("therapist_settings", [])
        client._mock_supabase.set_table_data("therapist_profiles", [])
        client._mock_supabase.set_table_data("action_log", [])

        resp = client.post("/api/lgpd/delete-data/all/ignored")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "therapist_profiles" in data["deleted"]
        assert "session_records" in data["deleted"]

    def test_delete_invalid_entity_type(self, client):
        resp = client.post("/api/lgpd/delete-data/invalid/some-id")
        assert resp.status_code == 400

    def test_delete_data_as_patient_forbidden(self, patient_client):
        resp = patient_client.post("/api/lgpd/delete-data/session/session-001")
        assert resp.status_code == 403

    def test_delete_data_no_auth(self, client):
        resp = client._tc.post("/api/lgpd/delete-data/session/session-001")
        assert resp.status_code == 401
