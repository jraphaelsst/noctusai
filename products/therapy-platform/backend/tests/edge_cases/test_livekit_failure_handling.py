"""Slice L fix-on-contact: `LiveRoomError` from the LiveKit provider is no
longer swallowed into `{"mock": True, "error": ...}`. This asserts
`session_service.py`'s explicit handling, split by whether the failing
call is fatal to the session (`create_room`/`generate_token` → 503) or
degrades it (`start_recording` → the session still starts, unrecorded).

No monkeypatching of `app.services.livekit_service` here: a
`_RaisingProvider` test double implements `LiveRoomProvider` and is
injected through `livekit_service`'s own module-level provider cache —
the DI seam `_get_provider()` is built around (see its docstring) —
rather than patching any of our own functions. Non-failing calls
delegate to a real `FakeLiveRoomProvider` so a multi-step flow (e.g.
"room creation succeeds, then recording fails") behaves like the real
adapter would, not like an unconditional stub.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services import livekit_service
from app.services.livekit_service import LiveRoomError
from noctusai_lib.integrations.live_rooms.fake import FakeLiveRoomProvider

_now = datetime.now(timezone.utc)
_from = (_now - timedelta(hours=1)).isoformat()
_until = (_now + timedelta(hours=2)).isoformat()


class _RaisingProvider:
    """`LiveRoomProvider` test double: one named method raises
    `LiveRoomError`, every other method delegates to a real
    `FakeLiveRoomProvider`."""

    def __init__(self, *, fail_on: str) -> None:
        self._fail_on = fail_on
        self._delegate = FakeLiveRoomProvider()

    async def create_room(self, name: str, **kwargs: Any):
        if self._fail_on == "create_room":
            raise LiveRoomError("create_room", "LiveKit unreachable")
        return await self._delegate.create_room(name, **kwargs)

    async def issue_join_token(self, room: str, identity: str, **kwargs: Any) -> str:
        if self._fail_on == "issue_join_token":
            raise LiveRoomError("issue_join_token", "signing failed")
        return await self._delegate.issue_join_token(room, identity, **kwargs)

    async def close_room(self, room: str) -> None:
        return await self._delegate.close_room(room)

    async def list_participants(self, room: str):
        return await self._delegate.list_participants(room)

    async def remove_participant(self, room: str, identity: str) -> None:
        return await self._delegate.remove_participant(room, identity)

    async def start_recording(self, room: str, spec: Any):
        if self._fail_on == "start_recording":
            raise LiveRoomError("start_recording", "egress unavailable")
        return await self._delegate.start_recording(room, spec)

    async def stop_recording(self, recording_id: str):
        return await self._delegate.stop_recording(recording_id)

    def parse_webhook(self, body: bytes, auth_header: Optional[str]):
        return self._delegate.parse_webhook(body, auth_header)


def _inject_provider(fail_on: str) -> None:
    livekit_service._provider = _RaisingProvider(fail_on=fail_on)


def _appt():
    return {
        "id": "appt-lk-fail-001",
        "therapist_id": "test-user-123",
        "patient_id": "patient-lk-fail-001",
        "scheduled_start": _from,
        "scheduled_end": _until,
        "status": "waiting",
        "clinic_id": None,
    }


def _room():
    return {
        "id": "room-lk-fail-001",
        "appointment_id": "appt-lk-fail-001",
        "meeting_url": "/session/lk-fail-uuid",
        "livekit_room_name": "therapy-appt-lk-fail-001",
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
        "id": "consent-lk-fail-001",
        "appointment_id": "appt-lk-fail-001",
        "patient_id": "patient-lk-fail-001",
        "therapist_id": "test-user-123",
        "clinic_id": None,
        "scope": "recording",
        "policy_version": "v1",
        "purpose_text": "Consentimento para gravação da sessão.",
        "actor_user_id": "patient-lk-fail-001",
        "granted_at": "2026-04-22T10:00:00-03:00",
        "revoked_at": None,
    }


def _seed(mock_sb):
    mock_sb.set_table_data("appointments", [_appt()])
    mock_sb.set_table_data("video_rooms", [_room()])
    mock_sb.set_table_data("session_audio_segments", [])
    mock_sb.set_table_data("session_interruptions", [])
    mock_sb.set_table_data("platform_settings", [])
    mock_sb.set_table_data("session_records", [])
    mock_sb.set_table_data("consent_records", [_consent()])


class TestCreateRoomFailureIsFatal:
    """A `create_room` failure means no video call is possible — the
    session start must surface a visible 503, never a silent mock room."""

    def test_start_session_returns_503_when_create_room_raises(self, client):
        _seed(client._mock_supabase)
        _inject_provider(fail_on="create_room")

        resp = client.post(
            "/api/sessions/appt-lk-fail-001/start", json={"consent_given": True}
        )

        assert resp.status_code == 503, resp.text
        assert "videochamada" in resp.json()["error"]["message"].lower()

        # The DB write for the segment happens AFTER create_room succeeds,
        # so a create_room failure must leave zero inserted segments.
        assert client._mock_supabase.table("session_audio_segments").inserted_payloads == []


class TestGenerateTokenFailureIsFatal:
    """A token-issuance failure means nobody can join — also a 503,
    even though the room + recording were created successfully."""

    def test_start_session_returns_503_when_issue_join_token_raises(self, client):
        _seed(client._mock_supabase)
        _inject_provider(fail_on="issue_join_token")

        resp = client.post(
            "/api/sessions/appt-lk-fail-001/start", json={"consent_given": True}
        )

        assert resp.status_code == 503, resp.text


class TestStartRecordingFailureDegradesNotBlocks:
    """A `start_recording` failure must NOT block the session — it starts
    unrecorded, with the failure visible in the response and the
    segment's `recording_id` column left NULL (its natural "no
    recording" state)."""

    def test_start_session_succeeds_unrecorded_when_start_recording_raises(self, client):
        _seed(client._mock_supabase)
        _inject_provider(fail_on="start_recording")

        resp = client.post(
            "/api/sessions/appt-lk-fail-001/start", json={"consent_given": True}
        )

        assert resp.status_code == 200, resp.text
        recording = resp.json()["data"]["recording"]
        assert recording.get("recording_failed") is True
        assert "recording_id" not in recording

        payloads = client._mock_supabase.table("session_audio_segments").inserted_payloads
        assert payloads, "the segment row is still created even though recording failed"
        # The follow-up `.update({"recording_id": ...})` never fires because
        # `rec_info.get("recording_id")` is falsy — no later payload carries
        # a recording_id patch.
        assert not any("recording_id" in p for p in payloads[1:])
