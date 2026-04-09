"""
Tests for the Session Journal Router.

Covers: list completed sessions, get session detail,
list summary versions, get audio download info, auth checks,
role-based track filtering, permission enforcement, patient views,
clinic admin views, expired audio handling, and pagination.
"""
import pytest
from datetime import datetime, timedelta, timezone

_now = datetime.now(timezone.utc)
_future_expiry = (_now + timedelta(days=3)).isoformat()
_past_expiry = (_now - timedelta(days=1)).isoformat()

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

# Session record owned by a different therapist
SAMPLE_SESSION_RECORD_OTHER = {
    "id": "sr-other",
    "appointment_id": "appt-002",
    "therapist_id": "other-therapist",
    "patient_id": "other-patient",
    "status": "completed",
}

SAMPLE_SUMMARY_CLINICAL = {
    "id": "sum-001",
    "session_record_id": "sr-001",
    "track": "clinical",
    "version_number": 1,
    "summary": "Resumo da sessao clinica.",
    "created_at": "2026-04-01T16:00:00Z",
}

SAMPLE_SUMMARY_BASE = {
    "id": "sum-002",
    "session_record_id": "sr-001",
    "track": "base",
    "version_number": 1,
    "summary": "Resumo da sessao para paciente.",
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
    "download_expires_at": _future_expiry,
}

SAMPLE_AUDIO_SEGMENT_EXPIRED = {
    "id": "seg-002",
    "appointment_id": "appt-001",
    "segment_number": 2,
    "segment_type": "main",
    "started_at": "2026-04-01T15:50:00Z",
    "ended_at": "2026-04-01T16:00:00Z",
    "audio_url": "https://storage.example.com/audio/seg-002.webm",
    "download_expires_at": _past_expiry,
}

SAMPLE_PATIENT_NOTE = {
    "id": "note-001",
    "session_record_id": "sr-001",
    "patient_id": "test-user-123",
    "note_text": "Minha anotacao pessoal.",
    "created_at": "2026-04-01T17:00:00Z",
}

SAMPLE_OBSERVATION = {
    "id": "obs-001",
    "session_record_id": "sr-001",
    "therapist_id": "test-user-123",
    "observation_text": "Paciente apresentou melhora.",
    "is_initial": True,
    "created_at": "2026-04-01T16:00:00Z",
    "deleted_at": None,
}


def _setup_tables(mock_sb, **overrides):
    """Set up common mock data with optional overrides."""
    defaults = {
        "appointments": [SAMPLE_APPOINTMENT_COMPLETED],
        "session_records": [SAMPLE_SESSION_RECORD],
        "session_summary_versions": [SAMPLE_SUMMARY_CLINICAL],
        "session_observations": [],
        "session_audio_segments": [SAMPLE_AUDIO_SEGMENT],
        "patient_session_notes": [],
    }
    defaults.update(overrides)
    for table, data in defaults.items():
        mock_sb.set_table_data(table, data)


class TestListCompletedSessions:
    """GET /api/journal/sessions"""

    def test_list_completed_sessions_therapist(self, client):
        """Therapist lists completed sessions."""
        _setup_tables(client._mock_supabase)
        resp = client.get("/api/journal/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_completed_sessions_patient(self, patient_client):
        """Patient lists their own completed sessions."""
        _setup_tables(patient_client._mock_supabase)
        resp = patient_client.get("/api/journal/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_completed_sessions_clinic_admin(self, clinic_admin_client):
        """Clinic admin lists sessions for their clinic."""
        _setup_tables(clinic_admin_client._mock_supabase)
        resp = clinic_admin_client.get("/api/journal/sessions")
        assert resp.status_code == 200

    def test_list_completed_sessions_with_patient_filter(self, client):
        """Therapist filters by patient_id."""
        _setup_tables(client._mock_supabase)
        resp = client.get("/api/journal/sessions?patient_id=patient-001")
        assert resp.status_code == 200

    def test_list_completed_sessions_pagination(self, client):
        """Pagination params are accepted."""
        _setup_tables(client._mock_supabase, appointments=[])
        resp = client.get("/api/journal/sessions?page=1&page_size=5")
        assert resp.status_code == 200

    def test_list_completed_sessions_empty(self, client):
        """No completed sessions returns empty list."""
        _setup_tables(client._mock_supabase, appointments=[])
        resp = client.get("/api/journal/sessions")
        assert resp.status_code == 200

    def test_list_completed_sessions_invalid_page_size(self, client):
        """page_size > 100 returns 422."""
        resp = client.get("/api/journal/sessions?page_size=200")
        assert resp.status_code == 422

    def test_list_completed_sessions_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/journal/sessions")
        assert resp.status_code == 401


class TestGetSessionDetail:
    """GET /api/journal/sessions/:id"""

    def test_get_session_detail_therapist(self, client):
        """Therapist gets full session detail with clinical track."""
        _setup_tables(
            client._mock_supabase,
            session_observations=[SAMPLE_OBSERVATION],
        )
        resp = client.get("/api/journal/sessions/sr-001")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["track"] == "clinical"
        assert "observations" in data
        assert "summary_versions" in data

    def test_get_session_detail_patient(self, patient_client):
        """Patient gets base track summary and personal notes."""
        patient_record = {
            **SAMPLE_SESSION_RECORD,
            "patient_id": "test-user-123",
        }
        _setup_tables(
            patient_client._mock_supabase,
            session_records=[patient_record],
            session_summary_versions=[SAMPLE_SUMMARY_BASE],
            patient_session_notes=[SAMPLE_PATIENT_NOTE],
        )
        resp = patient_client.get("/api/journal/sessions/sr-001")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["track"] == "base"
        assert "patient_notes" in data

    def test_get_session_detail_therapist_forbidden(self, client):
        """Therapist cannot access another therapist's session."""
        _setup_tables(
            client._mock_supabase,
            session_records=[SAMPLE_SESSION_RECORD_OTHER],
        )
        resp = client.get("/api/journal/sessions/sr-other")
        assert resp.status_code == 403

    def test_get_session_detail_patient_forbidden(self, patient_client):
        """Patient cannot access another patient's session."""
        _setup_tables(
            patient_client._mock_supabase,
            session_records=[SAMPLE_SESSION_RECORD_OTHER],
        )
        resp = patient_client.get("/api/journal/sessions/sr-other")
        assert resp.status_code == 403

    def test_get_session_detail_not_found(self, client):
        """Non-existent session record returns 404."""
        client._mock_supabase.set_table_data("session_records", [])
        resp = client.get("/api/journal/sessions/nonexistent")
        assert resp.status_code == 404

    def test_get_session_detail_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/journal/sessions/sr-001")
        assert resp.status_code == 401


class TestListSummaryVersions:
    """GET /api/journal/sessions/:id/versions"""

    def test_list_summary_versions_therapist(self, client):
        """Therapist lists clinical summary versions."""
        _setup_tables(client._mock_supabase)
        resp = client.get("/api/journal/sessions/sr-001/versions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_summary_versions_patient(self, patient_client):
        """Patient lists base summary versions."""
        patient_record = {
            **SAMPLE_SESSION_RECORD,
            "patient_id": "test-user-123",
        }
        _setup_tables(
            patient_client._mock_supabase,
            session_records=[patient_record],
            session_summary_versions=[SAMPLE_SUMMARY_BASE],
        )
        resp = patient_client.get("/api/journal/sessions/sr-001/versions")
        assert resp.status_code == 200

    def test_list_summary_versions_therapist_forbidden(self, client):
        """Therapist cannot list versions for another therapist's session."""
        _setup_tables(
            client._mock_supabase,
            session_records=[SAMPLE_SESSION_RECORD_OTHER],
        )
        resp = client.get("/api/journal/sessions/sr-other/versions")
        assert resp.status_code == 403

    def test_list_summary_versions_not_found(self, client):
        """Non-existent session returns 404."""
        client._mock_supabase.set_table_data("session_records", [])
        resp = client.get("/api/journal/sessions/nonexistent/versions")
        assert resp.status_code == 404

    def test_list_summary_versions_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/journal/sessions/sr-001/versions")
        assert resp.status_code == 401


class TestGetSessionAudio:
    """GET /api/journal/sessions/:id/audio"""

    def test_get_audio_download_info(self, client):
        """Therapist gets audio download info."""
        _setup_tables(client._mock_supabase)
        resp = client.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert "segments" in data
        assert data["session_record_id"] == "sr-001"

    def test_get_audio_expired_segment(self, client):
        """Expired audio segment returns null audio_url and is_expired=True."""
        _setup_tables(
            client._mock_supabase,
            session_audio_segments=[SAMPLE_AUDIO_SEGMENT_EXPIRED],
        )
        resp = client.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 200
        data = resp.json()["data"]
        segments = data["segments"]
        assert len(segments) == 1
        assert segments[0]["is_expired"] is True
        assert segments[0]["audio_url"] is None

    def test_get_audio_active_segment(self, client):
        """Non-expired audio segment returns audio_url and is_expired=False."""
        _setup_tables(client._mock_supabase)
        resp = client.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 200
        data = resp.json()["data"]
        segments = data["segments"]
        assert len(segments) == 1
        assert segments[0]["is_expired"] is False
        assert segments[0]["audio_url"] is not None

    def test_get_audio_patient_can_access_own(self, patient_client):
        """Patient can access audio for their own session."""
        patient_record = {
            **SAMPLE_SESSION_RECORD,
            "patient_id": "test-user-123",
        }
        _setup_tables(
            patient_client._mock_supabase,
            session_records=[patient_record],
        )
        resp = patient_client.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 200

    def test_get_audio_patient_forbidden(self, patient_client):
        """Patient cannot access audio for another patient's session."""
        _setup_tables(
            patient_client._mock_supabase,
            session_records=[SAMPLE_SESSION_RECORD_OTHER],
        )
        resp = patient_client.get("/api/journal/sessions/sr-other/audio")
        assert resp.status_code == 403

    def test_get_audio_no_segments(self, client):
        """Session with no audio segments returns empty list."""
        _setup_tables(
            client._mock_supabase,
            session_audio_segments=[],
        )
        resp = client.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["segments"] == []

    def test_get_audio_not_found(self, client):
        """Non-existent session returns 404."""
        client._mock_supabase.set_table_data("session_records", [])
        resp = client.get("/api/journal/sessions/nonexistent/audio")
        assert resp.status_code == 404

    def test_get_audio_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/journal/sessions/sr-001/audio")
        assert resp.status_code == 401
