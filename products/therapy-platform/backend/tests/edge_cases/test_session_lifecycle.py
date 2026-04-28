"""
Session lifecycle edge cases -- state machine transitions, access windows, overtime.

Tests verify that the video session state machine enforces valid transitions
and that access windows, auto-finalization, and reopen logic work correctly.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

_now = datetime.now(timezone.utc)
_from = (_now - timedelta(hours=1)).isoformat()
_until = (_now + timedelta(hours=2)).isoformat()
_past = (_now - timedelta(hours=3)).isoformat()
_far_past = (_now - timedelta(hours=5)).isoformat()
_future = (_now + timedelta(hours=5)).isoformat()


def _appt(status="waiting", therapist_id="test-user-123"):
    return {
        "id": "appt-lc-001",
        "therapist_id": therapist_id,
        "patient_id": "patient-lc-001",
        "scheduled_start": _from,
        "scheduled_end": _until,
        "status": status,
        "clinic_id": None,
    }


def _room(status="pending", accessible_from=_from, accessible_until=_until, **kwargs):
    base = {
        "id": "room-lc-001",
        "appointment_id": "appt-lc-001",
        "meeting_url": "/session/lc-uuid",
        "livekit_room_name": "therapy-appt-lc-001",
        "accessible_from": accessible_from,
        "accessible_until": accessible_until,
        "status": status,
        "total_pauses": 0,
        "session_started_at": None,
        "reopen_button_visible_until": None,
        "reopen_count": 0,
    }
    base.update(kwargs)
    return base


def _setup(mock_sb, appt_kwargs=None, room_kwargs=None, segments=None, *, with_consent=True):
    appt = _appt(**(appt_kwargs or {}))
    room = _room(**(room_kwargs or {}))
    mock_sb.set_table_data("appointments", [appt])
    mock_sb.set_table_data("video_rooms", [room])
    mock_sb.set_table_data("session_audio_segments", segments or [])
    mock_sb.set_table_data("session_interruptions", [])
    mock_sb.set_table_data("platform_settings", [])
    mock_sb.set_table_data("session_records", [])
    # compliance-audit-reconciliation Phase 5 (Q5): start_session requires
    # an active `recording` consent. Default True for the happy path.
    mock_sb.set_table_data("consent_records", [{
        "id": "consent-lc-001",
        "appointment_id": "appt-lc-001",
        "patient_id": "patient-lc-001",
        "therapist_id": appt["therapist_id"],
        "clinic_id": None,
        "scope": "recording",
        "policy_version": "v1",
        "purpose_text": "Consentimento para gravação da sessão.",
        "actor_user_id": "patient-lc-001",
        "granted_at": "2026-04-22T10:00:00-03:00",
        "revoked_at": None,
    }] if with_consent else [])


# ===================================================================
# Invalid state transitions
# ===================================================================

class TestInvalidStateTransitions:
    """Session state machine must reject invalid transitions."""

    def test_start_when_already_in_progress(self, client):
        """Start session when appointment is already in_progress -> error."""
        _setup(client._mock_supabase, appt_kwargs={"status": "in_progress"})
        resp = client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 400

    def test_resume_when_not_paused(self, client):
        """Resume session when room is active (not paused) -> error."""
        _setup(client._mock_supabase,
               appt_kwargs={"status": "in_progress"},
               room_kwargs={"status": "active"})
        resp = client.post("/api/sessions/appt-lc-001/resume")
        assert resp.status_code == 400

    def test_pause_when_not_active(self, client):
        """Pause session when room is not active -> error."""
        _setup(client._mock_supabase,
               appt_kwargs={"status": "in_progress"},
               room_kwargs={"status": "paused"})
        resp = client.post("/api/sessions/appt-lc-001/pause", json={})
        assert resp.status_code == 400

    def test_end_when_not_in_progress(self, client):
        """End session when room is closed -> error."""
        _setup(client._mock_supabase,
               appt_kwargs={"status": "completed"},
               room_kwargs={"status": "closed"})
        resp = client.post("/api/sessions/appt-lc-001/end", json={})
        assert resp.status_code == 400

    def test_reopen_after_intentional_close(self, client):
        """Reopen session after therapist-initiated end (status='closed') -> error."""
        _setup(client._mock_supabase,
               appt_kwargs={"status": "completed"},
               room_kwargs={"status": "closed"})
        resp = client.post("/api/sessions/appt-lc-001/reopen")
        assert resp.status_code == 400

    def test_reopen_after_auto_finalization_allowed(self, client):
        """Reopen session after auto_finalized within visibility window -> success."""
        visible_until = (_now + timedelta(minutes=20)).isoformat()
        _setup(
            client._mock_supabase,
            appt_kwargs={"status": "completed"},
            room_kwargs={
                "status": "auto_finalized",
                "reopen_button_visible_until": visible_until,
            },
        )
        resp = client.post("/api/sessions/appt-lc-001/reopen")
        assert resp.status_code == 200

    def test_reopen_after_visibility_window_expired(self, client):
        """Reopen after visibility window expired -> error."""
        expired = (_now - timedelta(minutes=5)).isoformat()
        _setup(
            client._mock_supabase,
            appt_kwargs={"status": "completed"},
            room_kwargs={
                "status": "auto_finalized",
                "reopen_button_visible_until": expired,
            },
        )
        resp = client.post("/api/sessions/appt-lc-001/reopen")
        assert resp.status_code == 400

    def test_patient_cannot_start_session(self, patient_client):
        """Patient POST /api/sessions/:id/start -> 403."""
        _setup(patient_client._mock_supabase)
        resp = patient_client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 403

    def test_patient_cannot_end_session(self, patient_client):
        """Patient POST /api/sessions/:id/end -> 403."""
        resp = patient_client.post("/api/sessions/appt-lc-001/end", json={})
        assert resp.status_code == 403


# ===================================================================
# Access window boundary
# ===================================================================

class TestAccessWindowBoundary:
    """Session must respect the access window defined in the video room."""

    def test_start_before_window_opens(self, client):
        """Start session before accessible_from -> denied."""
        _setup(
            client._mock_supabase,
            room_kwargs={
                "accessible_from": _future,
                "accessible_until": (_now + timedelta(hours=6)).isoformat(),
            },
        )
        resp = client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 400

    def test_start_after_window_closes(self, client):
        """Start session after accessible_until -> denied."""
        _setup(
            client._mock_supabase,
            room_kwargs={
                "accessible_from": _far_past,
                "accessible_until": _past,
            },
        )
        resp = client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 400

    def test_start_within_window_succeeds(self, client):
        """Start session within valid access window -> success."""
        _setup(client._mock_supabase)
        resp = client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 200

    def test_resume_after_window_closes(self, client):
        """Resume a paused session after the access window -> denied."""
        _setup(
            client._mock_supabase,
            appt_kwargs={"status": "in_progress"},
            room_kwargs={
                "status": "paused",
                "accessible_from": _far_past,
                "accessible_until": _past,
            },
        )
        resp = client.post("/api/sessions/appt-lc-001/resume")
        assert resp.status_code == 400


# ===================================================================
# Consent requirement
# ===================================================================

class TestConsentRequirement:
    """Session start requires explicit consent for recording."""

    def test_start_without_consent_body(self, client):
        """Missing consent_given field -> validation error."""
        _setup(client._mock_supabase)
        resp = client.post("/api/sessions/appt-lc-001/start", json={})
        assert resp.status_code == 422

    def test_start_with_consent_false(self, client):
        """consent_given=False -> 400."""
        _setup(client._mock_supabase)
        resp = client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": False,
        })
        assert resp.status_code == 400


# ===================================================================
# Overtime alerts
# ===================================================================

class TestOvertimeAlerts:
    """Overtime endpoint returns correct alert thresholds."""

    def test_overtime_with_time_remaining(self, client):
        """When time remains, alerts below the threshold are not triggered."""
        sb = client._mock_supabase
        sb.set_table_data("video_rooms", [_room(
            accessible_until=(_now + timedelta(minutes=60)).isoformat(),
        )])
        sb.set_table_data("appointments", [_appt()])
        resp = client.get("/api/sessions/appt-lc-001/overtime")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["remaining_seconds"] > 0
        # With 60 minutes remaining, the 30-minute threshold should NOT be triggered
        for alert in data["alerts"]:
            if alert["threshold_minutes"] == 30:
                assert alert["triggered"] is False

    def test_overtime_near_end(self, client):
        """When < 5 minutes remain, the 5-minute alert is triggered."""
        sb = client._mock_supabase
        sb.set_table_data("video_rooms", [_room(
            accessible_until=(_now + timedelta(minutes=3)).isoformat(),
        )])
        sb.set_table_data("appointments", [_appt()])
        resp = client.get("/api/sessions/appt-lc-001/overtime")
        assert resp.status_code == 200
        data = resp.json()["data"]
        for alert in data["alerts"]:
            if alert["threshold_minutes"] == 5:
                assert alert["triggered"] is True

    def test_overtime_expired(self, client):
        """When time is up, all alerts are triggered."""
        sb = client._mock_supabase
        sb.set_table_data("video_rooms", [_room(
            accessible_until=_past,
        )])
        sb.set_table_data("appointments", [_appt()])
        resp = client.get("/api/sessions/appt-lc-001/overtime")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["remaining_seconds"] == 0
        for alert in data["alerts"]:
            assert alert["triggered"] is True


# ===================================================================
# Therapist ownership validation
# ===================================================================

class TestTherapistOwnershipValidation:
    """Only the assigned therapist can manipulate the session."""

    def test_other_therapist_cannot_start(self, client):
        """A therapist who is not the assigned one cannot start the session."""
        _setup(
            client._mock_supabase,
            appt_kwargs={"therapist_id": "other-therapist-999"},
        )
        resp = client.post("/api/sessions/appt-lc-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 403

    def test_other_therapist_cannot_end(self, client):
        """A therapist who is not the assigned one cannot end the session."""
        _setup(
            client._mock_supabase,
            appt_kwargs={"status": "in_progress", "therapist_id": "other-therapist-999"},
            room_kwargs={"status": "active"},
        )
        resp = client.post("/api/sessions/appt-lc-001/end", json={})
        assert resp.status_code == 403
