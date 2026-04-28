"""
Tests for the Sessions Router.

Covers: start, pause, resume, end, reopen, get status,
get overtime info, get token, and auth/permission checks.
"""
import pytest
from datetime import datetime, timedelta, timezone

# Use dynamic dates that always encompass "now" so access window checks pass.
_now = datetime.now(timezone.utc)
_from = (_now - timedelta(hours=1)).isoformat()
_until = (_now + timedelta(hours=2)).isoformat()
_sched_start = (_now - timedelta(minutes=5)).isoformat()
_sched_end = (_now + timedelta(minutes=45)).isoformat()

SAMPLE_APPOINTMENT = {
    "id": "appt-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "scheduled_start": _sched_start,
    "scheduled_end": _sched_end,
    "status": "waiting",
    "meeting_link": "/session/test-uuid",
    "clinic_id": None,
}

SAMPLE_VIDEO_ROOM = {
    "id": "room-001",
    "appointment_id": "appt-001",
    "meeting_url": "/session/test-uuid",
    "livekit_room_name": "therapy-appt-001",
    "accessible_from": _from,
    "accessible_until": _until,
    "status": "pending",
    "total_pauses": 0,
    "session_started_at": None,
}

SAMPLE_SESSION_RECORD = {
    "id": "sr-001",
    "appointment_id": "appt-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "status": "active",
}

# compliance-audit-reconciliation Phase 5 (Q5, 2026-04-22): start_session
# now requires a persisted `recording` consent on the appointment.
SAMPLE_RECORDING_CONSENT = {
    "id": "consent-001",
    "appointment_id": "appt-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "clinic_id": None,
    "scope": "recording",
    "policy_version": "v1",
    "purpose_text": "Consentimento para gravação da sessão.",
    "actor_user_id": "patient-001",
    "granted_at": "2026-04-22T10:00:00-03:00",
    "revoked_at": None,
}


def _setup_session_tables(mock_sb, *, with_consent: bool = True):
    """Set up common mock data for session tests.

    `with_consent=True` (default) seeds an active `recording` consent —
    matches the happy-path expectation for session-start. Pass
    `with_consent=False` to test the missing-consent branch.
    """
    mock_sb.set_table_data("appointments", [SAMPLE_APPOINTMENT])
    mock_sb.set_table_data("video_rooms", [SAMPLE_VIDEO_ROOM])
    mock_sb.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
    mock_sb.set_table_data("session_audio_segments", [])
    mock_sb.set_table_data("platform_settings", [])
    mock_sb.set_table_data(
        "consent_records",
        [SAMPLE_RECORDING_CONSENT] if with_consent else [],
    )


class TestStartSession:
    """POST /api/sessions/:id/start"""

    def test_start_session_therapist(self, client):
        """Therapist starts a session with consent."""
        _setup_session_tables(client._mock_supabase)
        resp = client.post("/api/sessions/appt-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_start_session_consent_required(self, client):
        """Starting with the legacy `consent_given=False` flag returns 400."""
        _setup_session_tables(client._mock_supabase)
        resp = client.post("/api/sessions/appt-001/start", json={
            "consent_given": False,
        })
        assert resp.status_code == 400

    def test_start_session_without_consent_record_blocked(self, client):
        """Even with `consent_given=True`, session start fails if no persisted
        `recording` consent exists (Phase 5 / Q5 enforcement)."""
        _setup_session_tables(client._mock_supabase, with_consent=False)
        resp = client.post("/api/sessions/appt-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 400
        assert "POST /api/consents/grant" in resp.json()["error"]["message"]

    def test_start_session_with_revoked_consent_blocked(self, client):
        """A revoked consent is not active — start_session must refuse."""
        _setup_session_tables(client._mock_supabase, with_consent=False)
        revoked = {**SAMPLE_RECORDING_CONSENT, "revoked_at": "2026-04-22T11:00:00-03:00"}
        client._mock_supabase.set_table_data("consent_records", [revoked])
        resp = client.post("/api/sessions/appt-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 400

    def test_start_session_patient_forbidden(self, patient_client):
        """Patient cannot start sessions."""
        resp = patient_client.post("/api/sessions/appt-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 403

    def test_start_session_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/sessions/appt-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 401


class TestPauseSession:
    """POST /api/sessions/:id/pause"""

    def test_pause_session(self, client):
        """Therapist pauses a running session."""
        _setup_session_tables(client._mock_supabase)
        # Set status to in_progress for pause
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT, "status": "in_progress",
        }])
        client._mock_supabase.set_table_data("video_rooms", [{
            **SAMPLE_VIDEO_ROOM, "status": "active",
        }])
        resp = client.post("/api/sessions/appt-001/pause")
        assert resp.status_code == 200

    def test_pause_session_patient_forbidden(self, patient_client):
        """Patient cannot pause sessions."""
        resp = patient_client.post("/api/sessions/appt-001/pause")
        assert resp.status_code == 403


class TestResumeSession:
    """POST /api/sessions/:id/resume"""

    def test_resume_session(self, client):
        """Therapist resumes a paused session."""
        _setup_session_tables(client._mock_supabase)
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT, "status": "in_progress",
        }])
        client._mock_supabase.set_table_data("video_rooms", [{
            **SAMPLE_VIDEO_ROOM, "status": "paused",
        }])
        resp = client.post("/api/sessions/appt-001/resume")
        assert resp.status_code == 200

    def test_resume_session_patient_forbidden(self, patient_client):
        """Patient cannot resume sessions."""
        resp = patient_client.post("/api/sessions/appt-001/resume")
        assert resp.status_code == 403


class TestEndSession:
    """POST /api/sessions/:id/end"""

    def test_end_session(self, client):
        """Therapist ends a session."""
        _setup_session_tables(client._mock_supabase)
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT, "status": "in_progress",
        }])
        client._mock_supabase.set_table_data("video_rooms", [{
            **SAMPLE_VIDEO_ROOM, "status": "active",
        }])
        resp = client.post("/api/sessions/appt-001/end")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_end_session_with_observation(self, client):
        """Therapist ends a session with an initial observation."""
        _setup_session_tables(client._mock_supabase)
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT, "status": "in_progress",
        }])
        client._mock_supabase.set_table_data("video_rooms", [{
            **SAMPLE_VIDEO_ROOM, "status": "active",
        }])
        resp = client.post("/api/sessions/appt-001/end", json={
            "initial_observation": "Paciente apresentou melhora significativa.",
        })
        assert resp.status_code == 200

    def test_end_session_patient_forbidden(self, patient_client):
        """Patient cannot end sessions."""
        resp = patient_client.post("/api/sessions/appt-001/end")
        assert resp.status_code == 403


class TestReopenSession:
    """POST /api/sessions/:id/reopen"""

    def test_reopen_session(self, client):
        """Therapist reopens a session after auto-finalization."""
        _setup_session_tables(client._mock_supabase)
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT, "status": "completed",
        }])
        client._mock_supabase.set_table_data("video_rooms", [{
            **SAMPLE_VIDEO_ROOM,
            "status": "auto_finalized",
            "auto_finalized_at": (_now - timedelta(minutes=5)).isoformat(),
            "reopen_button_visible_until": (_now + timedelta(minutes=25)).isoformat(),
            "reopen_count": 0,
        }])
        resp = client.post("/api/sessions/appt-001/reopen")
        assert resp.status_code == 200

    def test_reopen_session_patient_forbidden(self, patient_client):
        """Patient cannot reopen sessions."""
        resp = patient_client.post("/api/sessions/appt-001/reopen")
        assert resp.status_code == 403


class TestGetSessionStatus:
    """GET /api/sessions/:id/status"""

    def test_get_status(self, client):
        """Therapist gets session status."""
        _setup_session_tables(client._mock_supabase)
        resp = client.get("/api/sessions/appt-001/status")
        assert resp.status_code == 200

    def test_get_status_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/sessions/appt-001/status")
        assert resp.status_code == 401


class TestGetOvertimeInfo:
    """GET /api/sessions/:id/overtime"""

    def test_get_overtime_info(self, client):
        """Therapist gets overtime information."""
        _setup_session_tables(client._mock_supabase)
        resp = client.get("/api/sessions/appt-001/overtime")
        assert resp.status_code == 200


class TestGetSessionToken:
    """GET /api/sessions/:id/token"""

    def test_get_token(self, client):
        """Therapist gets a LiveKit token for the session."""
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT,
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
        }])
        client._mock_supabase.set_table_data("video_rooms", [{
            **SAMPLE_VIDEO_ROOM,
            "status": "active",
        }])
        resp = client.get("/api/sessions/appt-001/token")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_get_token_appointment_not_found(self, client):
        """Non-existent appointment returns 404."""
        client._mock_supabase.set_table_data("appointments", [])
        resp = client.get("/api/sessions/nonexistent/token")
        assert resp.status_code == 404

    def test_get_token_no_video_room(self, client):
        """Appointment without video room returns 404."""
        client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT,
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
        }])
        client._mock_supabase.set_table_data("video_rooms", [])
        resp = client.get("/api/sessions/appt-001/token")
        assert resp.status_code == 404
