"""
Tests for the Observations Router.

Covers: create observation, list observations, update observation,
soft-delete observation, and auth/permission checks.
"""
import pytest

SAMPLE_SESSION_RECORD = {
    "id": "sr-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
}

SAMPLE_OBSERVATION = {
    "id": "obs-001",
    "session_record_id": "sr-001",
    "therapist_id": "test-user-123",
    "observation_text": "Paciente demonstrou boa reflexao sobre conflitos familiares.",
    "is_initial": False,
    # MOCK-SELECT-PREDICATE-FIX (45be944): observations router filters via
    # `.is_("deleted_at", "null")` on SELECT before ownership check. The
    # seed mock's `_eval_is` is literal Python `is`: `None is "null"` →
    # False, so rows with `deleted_at: None` get filtered out → 404. Seed
    # the literal string "null" (interned by Python → `"null" is "null"` →
    # True) so the predicate passes. Real PostgREST stores PostgreSQL NULL;
    # this is a test-only shim until the seed mock fixes IS NULL semantics.
    "deleted_at": "null",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestCreateObservation:
    """POST /api/observations"""

    def test_create_observation(self, client):
        """Therapist creates an observation for a session."""
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        client._mock_supabase.set_table_data("session_summary_versions", [])
        resp = client.post("/api/observations", json={
            "session_record_id": "sr-001",
            "observation_text": "Paciente demonstrou boa reflexao.",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_create_observation_missing_text(self, client):
        """Missing observation_text returns 422."""
        resp = client.post("/api/observations", json={
            "session_record_id": "sr-001",
        })
        assert resp.status_code == 422

    def test_create_observation_empty_text(self, client):
        """Empty observation_text returns 422."""
        resp = client.post("/api/observations", json={
            "session_record_id": "sr-001",
            "observation_text": "",
        })
        assert resp.status_code == 422

    def test_create_observation_patient_forbidden(self, patient_client):
        """Patient cannot create observations."""
        resp = patient_client.post("/api/observations", json={
            "session_record_id": "sr-001",
            "observation_text": "Test",
        })
        assert resp.status_code == 403

    def test_create_observation_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/observations", json={
            "session_record_id": "sr-001",
            "observation_text": "Test",
        })
        assert resp.status_code == 401


class TestListObservations:
    """GET /api/observations/session/:id"""

    def test_list_observations(self, client):
        """Therapist lists observations for a session."""
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        resp = client.get("/api/observations/session/sr-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_observations_patient_forbidden(self, patient_client):
        """Patient cannot view therapist observations."""
        resp = patient_client.get("/api/observations/session/sr-001")
        assert resp.status_code == 403


class TestUpdateObservation:
    """PATCH /api/observations/:id"""

    def test_update_observation(self, client):
        """Therapist updates an observation."""
        client._mock_supabase.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        client._mock_supabase.set_table_data("session_summary_versions", [])
        resp = client.patch("/api/observations/obs-001", json={
            "observation_text": "Texto atualizado com novas observacoes.",
        })
        assert resp.status_code == 200

    def test_update_observation_patient_forbidden(self, patient_client):
        """Patient cannot update observations."""
        resp = patient_client.patch("/api/observations/obs-001", json={
            "observation_text": "Nao deveria funcionar.",
        })
        assert resp.status_code == 403


class TestDeleteObservation:
    """DELETE /api/observations/:id"""

    def test_soft_delete_observation(self, client):
        """Therapist soft-deletes an observation."""
        client._mock_supabase.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        client._mock_supabase.set_table_data("session_summary_versions", [])
        resp = client.delete("/api/observations/obs-001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_delete_observation_not_found(self, client):
        """Non-existent observation returns 404."""
        client._mock_supabase.set_table_data("session_observations", [])
        resp = client.delete("/api/observations/nonexistent")
        assert resp.status_code == 404

    def test_delete_observation_patient_forbidden(self, patient_client):
        """Patient cannot delete observations."""
        resp = patient_client.delete("/api/observations/obs-001")
        assert resp.status_code == 403
