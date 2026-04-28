"""
Tests for the LGPD Router — data deletion endpoints.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

# Fixtures shape-correct against the live therapy schema (verified Phase 0 via
# Supabase MCP, `compliance-audit-reconciliation` project 2026-04-22):
# - `wallets` is keyed by (owner_id, owner_type)
# - `session_records` links to appointments via appointment_id (no therapist_id column)
# - `session_observations` links via session_record_id (no session_id column)
# Therapist ownership of sessions flows session_records → appointments.therapist_id.

SAMPLE_WALLET = {"id": "wallet-001", "owner_id": "test-user-123", "owner_type": "patient", "balance": 0}

SAMPLE_APPOINTMENT = {"id": "appt-001", "therapist_id": "test-user-123", "patient_id": "patient-001"}

SAMPLE_SESSION_RECORD = {"id": "session-001", "appointment_id": "appt-001"}

SAMPLE_OBSERVATION = {"id": "obs-001", "session_record_id": "session-001", "observation_text": "Paciente apresentou melhora."}


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
        # Therapist ownership flows session_records.appointment_id → appointments.therapist_id.
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        client._mock_supabase.set_table_data("session_observations", [])
        client._mock_supabase.set_table_data("session_summary_versions", [])

        resp = client.post("/api/lgpd/delete-data/session/session-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "session_records" in data["deleted"]

    def test_delete_observation(self, client):
        # Observation ownership chains observation → session_record → appointment → therapist.
        client._mock_supabase.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])

        resp = client.post("/api/lgpd/delete-data/observation/obs-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "session_observations" in data["deleted"]

    def test_delete_all(self, client):
        # Seed the full dependency graph: therapist → appointment → session_record + video_room.
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("video_rooms", [{"id": "vr-001", "appointment_id": "appt-001"}])
        for t in (
            "session_summary_versions", "session_observations",
            "session_audio_segments", "session_interruptions",
            "clinical_longitudinal_analyses", "patient_longitudinal_analyses",
            "messages", "conversation_participants",
            "wallets", "wallet_movements",
            "therapist_settings", "therapist_profiles",
            "action_log",
        ):
            client._mock_supabase.set_table_data(t, [])

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
