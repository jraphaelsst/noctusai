"""Regression guards for `therapy.session_audio_segments` schema correctness.

The 2026-05-03 audit (`projects/.../therapy-audio-lifecycle-schema-reconciliation/`)
found that `session_service.py`, `transcription_service.py`, and
`session_journal.py` were inserting / querying segments via `appointment_id` —
a column that never existed on `session_audio_segments`. The live PostgREST
silently dropped the writes; tests passed because the mock didn't validate
columns. The refactor (Phase 1a) routes every site through
`video_room_id`, mirroring the canonical pattern at `ai_pipeline.py:386-396`.

These tests assert the refactored writes/reads land on `video_room_id`, NOT
`appointment_id`. They run against the canonical `MockSupabaseClient`
fixture and read `inserted_payloads` directly — no monkey-patching.

Phase 1b parallel: the migration `009_session_audio_segments_recording_id.sql`
added the long-missing `recording_id TEXT` column. The lifecycle code already
attempted to write/read it, so its persistence becomes real once the column
exists. The recording_id round-trip test below asserts the LiveKit
`stop_recording(...)` call fires when the column is populated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

_now = datetime.now(timezone.utc)
_from = (_now - timedelta(hours=1)).isoformat()
_until = (_now + timedelta(hours=2)).isoformat()


def _appt():
    return {
        "id": "appt-schema-001",
        "therapist_id": "test-user-123",
        "patient_id": "patient-schema-001",
        "scheduled_start": _from,
        "scheduled_end": _until,
        "status": "waiting",
        "clinic_id": None,
    }


def _room():
    return {
        "id": "room-schema-001",
        "appointment_id": "appt-schema-001",
        "meeting_url": "/session/schema-uuid",
        "livekit_room_name": "therapy-appt-schema-001",
        "accessible_from": _from,
        "accessible_until": _until,
        "status": "pending",
        "total_pauses": 0,
        "session_started_at": None,
        "reopen_button_visible_until": None,
        "reopen_count": 0,
    }


def _consent():
    return {
        "id": "consent-schema-001",
        "appointment_id": "appt-schema-001",
        "patient_id": "patient-schema-001",
        "therapist_id": "test-user-123",
        "clinic_id": None,
        "scope": "recording",
        "policy_version": "v1",
        "purpose_text": "Consentimento para gravação da sessão.",
        "actor_user_id": "patient-schema-001",
        "granted_at": "2026-04-22T10:00:00-03:00",
        "revoked_at": None,
    }


def _seed(mock_sb, *, segments=None):
    mock_sb.set_table_data("appointments", [_appt()])
    mock_sb.set_table_data("video_rooms", [_room()])
    mock_sb.set_table_data("session_audio_segments", segments or [])
    mock_sb.set_table_data("session_interruptions", [])
    mock_sb.set_table_data("platform_settings", [])
    mock_sb.set_table_data("session_records", [])
    mock_sb.set_table_data("consent_records", [_consent()])


class TestStartSessionInsertsByVideoRoomId:
    """`start_session` MUST insert segments keyed by `video_room_id`, never `appointment_id`."""

    def test_start_session_inserts_video_room_id_not_appointment_id(self, client):
        _seed(client._mock_supabase)

        with patch("app.services.session_service.livekit_service.create_room",
                   new_callable=AsyncMock) as mock_create, \
             patch("app.services.session_service.livekit_service.start_recording",
                   new_callable=AsyncMock) as mock_start_rec, \
             patch("app.services.session_service.livekit_service.generate_token",
                   new_callable=AsyncMock) as mock_token:
            mock_create.return_value = {"sid": "lk-room-1"}
            mock_start_rec.return_value = {"recording_id": "egress-001"}
            mock_token.return_value = "lk.token.value"

            resp = client.post("/api/sessions/appt-schema-001/start", json={"consent_given": True})

        assert resp.status_code == 200, resp.text

        payloads = client._mock_supabase.table("session_audio_segments").inserted_payloads
        assert payloads, "start_session should have inserted exactly one segment"
        first = payloads[0]
        assert first.get("video_room_id") == "room-schema-001", \
            f"Expected video_room_id='room-schema-001', got {first}"
        assert "appointment_id" not in first, \
            f"Phase 1a regression: appointment_id leaked back into insert payload: {first}"


class TestRecordingIdRoundTrip:
    """Phase 1b: `recording_id` column exists post-009 migration; persisted writes
    must round-trip and unblock LiveKit `stop_recording(...)` at session-end."""

    def test_end_session_invokes_stop_recording_when_recording_id_present(self, client):
        # Pre-seed an in-progress session with a segment that already has a
        # recording_id (simulating start_recording having resolved).
        appt = {**_appt(), "status": "in_progress"}
        room = {**_room(), "status": "active"}
        segment = {
            "id": "seg-schema-001",
            "video_room_id": "room-schema-001",
            "segment_number": 1,
            "segment_type": "initial",
            "started_at": _from,
            "ended_at": None,
            "recording_id": "egress-001",
        }
        client._mock_supabase.set_table_data("appointments", [appt])
        client._mock_supabase.set_table_data("video_rooms", [room])
        client._mock_supabase.set_table_data("session_audio_segments", [segment])
        client._mock_supabase.set_table_data("session_interruptions", [])
        client._mock_supabase.set_table_data("platform_settings", [])
        client._mock_supabase.set_table_data("session_records", [])

        with patch("app.services.session_service.livekit_service.stop_recording",
                   new_callable=AsyncMock) as mock_stop_rec, \
             patch("app.services.session_service.livekit_service.close_room",
                   new_callable=AsyncMock) as mock_close:
            resp = client.post("/api/sessions/appt-schema-001/end")

        assert resp.status_code == 200, resp.text
        # Pre-009: this assertion would have failed because the read at
        # `active_segment.get("recording_id")` always returned None.
        mock_stop_rec.assert_called_once_with("egress-001")


class TestQueryFiltersVideoRoomId:
    """Lifecycle queries that look up the active segment must filter by
    `video_room_id`, not `appointment_id`."""

    def test_pause_session_queries_by_video_room_id(self, client):
        # An active session with one open segment.
        appt = {**_appt(), "status": "in_progress"}
        room = {**_room(), "status": "active"}
        segment = {
            "id": "seg-pause-001",
            "video_room_id": "room-schema-001",
            "segment_number": 1,
            "segment_type": "initial",
            "started_at": _from,
            "ended_at": None,
            "recording_id": "egress-pause-001",
        }
        client._mock_supabase.set_table_data("appointments", [appt])
        client._mock_supabase.set_table_data("video_rooms", [room])
        client._mock_supabase.set_table_data("session_audio_segments", [segment])
        client._mock_supabase.set_table_data("session_interruptions", [])
        client._mock_supabase.set_table_data("platform_settings", [])

        with patch("app.services.session_service.livekit_service.stop_recording",
                   new_callable=AsyncMock) as mock_stop_rec:
            resp = client.post("/api/sessions/appt-schema-001/pause", json={"reason": "break"})

        assert resp.status_code == 200, resp.text
        # Confirms the SELECT-then-update path resolved the active segment by
        # video_room_id (else the segment wouldn't have been found and
        # stop_recording wouldn't have fired).
        mock_stop_rec.assert_called_once_with("egress-pause-001")
