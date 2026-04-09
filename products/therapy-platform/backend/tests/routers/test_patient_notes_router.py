"""
Tests for the Patient Notes Router.

Covers: create note, list notes, update note,
and auth/permission checks (patient-only access).
"""
import pytest

SAMPLE_SESSION_RECORD = {
    "id": "sr-001",
    "therapist_id": "therapist-001",
    "patient_id": "test-user-123",
}

SAMPLE_NOTE = {
    "id": "note-001",
    "session_record_id": "sr-001",
    "patient_id": "test-user-123",
    "note_text": "Me senti bem durante a sessao de hoje.",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestCreatePatientNote:
    """POST /api/patient-notes"""

    def test_create_note(self, patient_client):
        """Patient creates a session note."""
        patient_client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        patient_client._mock_supabase.set_table_data("patient_session_notes", [SAMPLE_NOTE])
        resp = patient_client.post("/api/patient-notes", json={
            "session_record_id": "sr-001",
            "note_text": "Me senti bem durante a sessao.",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_create_note_missing_text(self, patient_client):
        """Missing note_text returns 422."""
        resp = patient_client.post("/api/patient-notes", json={
            "session_record_id": "sr-001",
        })
        assert resp.status_code == 422

    def test_create_note_therapist_forbidden(self, client):
        """Therapist cannot create patient notes."""
        resp = client.post("/api/patient-notes", json={
            "session_record_id": "sr-001",
            "note_text": "Nao deveria funcionar.",
        })
        assert resp.status_code == 403

    def test_create_note_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/patient-notes", json={
            "session_record_id": "sr-001",
            "note_text": "Test",
        })
        assert resp.status_code == 401


class TestListPatientNotes:
    """GET /api/patient-notes/session/:id"""

    def test_list_notes(self, patient_client):
        """Patient lists own notes for a session."""
        patient_client._mock_supabase.set_table_data("patient_session_notes", [SAMPLE_NOTE])
        resp = patient_client.get("/api/patient-notes/session/sr-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_notes_therapist_forbidden(self, client):
        """Therapist cannot access patient notes."""
        resp = client.get("/api/patient-notes/session/sr-001")
        assert resp.status_code == 403


class TestUpdatePatientNote:
    """PATCH /api/patient-notes/:id"""

    def test_update_note(self, patient_client):
        """Patient updates own note."""
        patient_client._mock_supabase.set_table_data("patient_session_notes", [SAMPLE_NOTE])
        patient_client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        resp = patient_client.patch("/api/patient-notes/note-001", json={
            "note_text": "Texto atualizado com novas reflexoes.",
        })
        assert resp.status_code == 200

    def test_update_note_therapist_forbidden(self, client):
        """Therapist cannot update patient notes."""
        resp = client.patch("/api/patient-notes/note-001", json={
            "note_text": "Nao deveria funcionar.",
        })
        assert resp.status_code == 403

    def test_update_note_not_found(self, patient_client):
        """Non-existent note returns 404."""
        patient_client._mock_supabase.set_table_data("patient_session_notes", [])
        resp = patient_client.patch("/api/patient-notes/nonexistent", json={
            "note_text": "Texto qualquer.",
        })
        assert resp.status_code == 404
