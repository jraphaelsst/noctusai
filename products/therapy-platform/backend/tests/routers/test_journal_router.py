"""
Tests for the Session Journal Router.

Covers: list completed sessions, get session detail,
list summary versions, get audio download info, and auth checks.
"""
import pytest

SAMPLE_APPOINTMENT_COMPLETED = {
    "id": "appt-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "scheduled_start": "2026-04-01T15:00:00Z",
    "scheduled_end": "2026-04-01T15:50:00Z",
    "status": "completed",
    "clinic_id": None,
}

SAMPLE_SESSION_RECORD = {
    "id": "sr-001",
    "appointment_id": "appt-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "status": "completed",
}

SAMPLE_SUMMARY = {
    "id": "sum-001",
    "session_record_id": "sr-001",
    "track": "clinical",
    "version_number": 1,
    "summary": "Resumo da sessao clinica.",
    "created_at": "2026-04-01T16:00:00Z",
}

SAMPLE_AUDIO_SEGMENT = {
    "id": "seg-001",
    "appointment_id": "appt-001",
    "segment_number": 1,
    "segment_type": "main",
    "started_at": "2026-04-01T15:00:00Z",
    "ended_at": "2026-04-01T15:50:00Z",
    "audio_url": "https://storage.example.com/audio/seg-001.webm",
    "download_expires_at": "2026-04-05T15:50:00Z",
}


class TestListCompletedSessions:
    """GET /api/journal/sessions"""

    def test_list_completed_sessions_therapist(self, client):
        """Therapist lists completed sessions."""
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT_COMPLETED])
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("session_summary_versions", [SAMPLE_SUMMARY])
        resp = client.get("/api/journal/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_completed_sessions_pagination(self, client):
        """Pagination params are accepted."""
        client._mock_supabase.set_table_data("appointments", [])
        client._mock_supabase.set_table_data("session_records", [])
        client._mock_supabase.set_table_data("session_summary_versions", [])
        resp = client.get("/api/journal/sessions?page=1&page_size=5")
        assert resp.status_code == 200

    def test_list_completed_sessions_empty(self, client):
        """No completed sessions returns empty list."""
        client._mock_supabase.set_table_data("appointments", [])
        resp = client.get("/api/journal/sessions")
        assert resp.status_code == 200

    def test_list_completed_sessions_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/journal/sessions")
        assert resp.status_code == 401


class TestGetSessionDetail:
    """GET /api/journal/sessions/:id"""

    def test_get_session_detail_therapist(self, client):
        """Therapist gets full session detail with clinical track."""
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("session_summary_versions", [SAMPLE_SUMMARY])
        client._mock_supabase.set_table_data("session_observations", [])
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT_COMPLETED])
        resp = client.get("/api/journal/sessions/sr-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert data["track"] == "clinical"
        assert "observations" in data

    def test_get_session_detail_not_found(self, client):
        """Non-existent session record returns 404."""
        client._mock_supabase.set_table_data("session_records", [])
        resp = client.get("/api/journal/sessions/nonexistent")
        assert resp.status_code == 404


class TestListSummaryVersions:
    """GET /api/journal/sessions/:id/versions"""

    def test_list_summary_versions(self, client):
        """Therapist lists clinical summary versions."""
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("session_summary_versions", [SAMPLE_SUMMARY])
        resp = client.get("/api/journal/sessions/sr-001/versions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_summary_versions_not_found(self, client):
        """Non-existent session returns 404."""
        client._mock_supabase.set_table_data("session_records", [])
        resp = client.get("/api/journal/sessions/nonexistent/versions")
        assert resp.status_code == 404


class TestGetSessionAudio:
    """GET /api/journal/sessions/:id/audio"""

    def test_get_audio_download_info(self, client):
        """Therapist gets audio download info."""
        client._mock_supabase.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        client._mock_supabase.set_table_data("session_audio_segments", [SAMPLE_AUDIO_SEGMENT])
        resp = client.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert "segments" in data

    def test_get_audio_not_found(self, client):
        """Non-existent session returns 404."""
        client._mock_supabase.set_table_data("session_records", [])
        resp = client.get("/api/journal/sessions/nonexistent/audio")
        assert resp.status_code == 404

    def test_get_audio_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 401
