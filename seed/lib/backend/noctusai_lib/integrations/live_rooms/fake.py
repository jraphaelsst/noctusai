"""In-memory `LiveRoomProvider` for tests and local dev.

No network, no LiveKit SDK import. A recording started via
`start_recording` stays `"active"` until either `stop_recording` is
called directly, or a test calls `simulate_egress_complete` to model
the async, egress-finishes-later-than-the-request path a real
room-composite egress takes (mirrors `FakePaymentGateway`'s
event-simulation style for the same reason: some outcomes only ever
arrive via a webhook, and a consumer's webhook handler needs a Fake
event to test against too).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .errors import LiveRoomError
from .types import (
    LiveRoomEvent,
    ParticipantInfo,
    RecordingHandle,
    RecordingResult,
    RecordingSpec,
    RecordingStatus,
    RoomInfo,
)


@dataclass
class _FakeRoom:
    info: RoomInfo
    participants: Dict[str, ParticipantInfo] = field(default_factory=dict)
    closed: bool = False


@dataclass
class _FakeRecording:
    room_name: str
    spec: RecordingSpec
    status: RecordingStatus = "active"
    file_url: Optional[str] = None
    error: Optional[str] = None


class FakeLiveRoomProvider:
    """Deterministic, dependency-free `LiveRoomProvider`.

    State (`self.rooms`, `self.recordings`) is public and inspectable —
    tests assert against it directly rather than through a second mock
    layer, same convention as `FakePaymentGateway`.
    """

    def __init__(self) -> None:
        self.rooms: Dict[str, _FakeRoom] = {}
        self.recordings: Dict[str, _FakeRecording] = {}
        self._room_seq = 0
        self._rec_seq = 0

    # ── LiveRoomProvider ─────────────────────────────────────────────

    async def create_room(
        self,
        name: str,
        *,
        max_participants: Optional[int] = None,
        empty_timeout_s: int = 600,
        metadata: Optional[str] = None,
    ) -> RoomInfo:
        existing = self.rooms.get(name)
        if existing is not None and not existing.closed:
            return existing.info
        self._room_seq += 1
        info = RoomInfo(
            name=name,
            sid=f"RM_fake_{self._room_seq}",
            max_participants=max_participants,
            num_participants=0,
            metadata=metadata,
            creation_time=int(time.time()),
        )
        self.rooms[name] = _FakeRoom(info=info)
        return info

    async def issue_join_token(
        self,
        room: str,
        identity: str,
        *,
        display_name: Optional[str] = None,
        can_publish: bool = True,
        can_subscribe: bool = True,
        ttl_s: int = 3600,
    ) -> str:
        # Mirrors `RealLiveKitProvider.issue_join_token`: signing a join
        # JWT is pure crypto, no network call to LiveKit — the real
        # adapter never validates room existence here either (LiveKit
        # itself can create a room on first join when the token grants
        # `room_join=True`). A consumer that issues a token before/without
        # an explicit `create_room` (therapy-platform's `/token` endpoint
        # does exactly this) must not be rejected by the Fake for a
        # constraint the Real path doesn't enforce — found via the
        # therapy-platform router test suite during Slice L authoring.
        fake_room = self.rooms.get(room)
        if fake_room is None or fake_room.closed:
            fake_room = _FakeRoom(info=RoomInfo(name=room))
            self.rooms[room] = fake_room
        fake_room.participants[identity] = ParticipantInfo(
            identity=identity,
            name=display_name,
            state="joined",
            joined_at=int(time.time()),
        )
        return f"fake-token.{room}.{identity}.{int(time.time())}"

    async def close_room(self, room: str) -> None:
        fake_room = self.rooms.get(room)
        if fake_room is not None:
            fake_room.closed = True
            fake_room.participants.clear()

    async def list_participants(self, room: str) -> List[ParticipantInfo]:
        fake_room = self.rooms.get(room)
        if fake_room is None:
            return []
        return list(fake_room.participants.values())

    async def remove_participant(self, room: str, identity: str) -> None:
        fake_room = self.rooms.get(room)
        if fake_room is not None:
            fake_room.participants.pop(identity, None)

    async def start_recording(self, room: str, spec: RecordingSpec) -> RecordingHandle:
        if room not in self.rooms or self.rooms[room].closed:
            raise LiveRoomError("start_recording", f"room not found or closed: {room!r}")
        self._rec_seq += 1
        recording_id = f"fake-rec-{self._rec_seq}-{uuid.uuid4().hex[:8]}"
        self.recordings[recording_id] = _FakeRecording(room_name=room, spec=spec)
        return RecordingHandle(recording_id=recording_id, room_name=room)

    async def stop_recording(self, recording_id: str) -> RecordingResult:
        rec = self.recordings.get(recording_id)
        if rec is None:
            raise LiveRoomError("stop_recording", f"unknown recording_id: {recording_id!r}")
        if rec.status == "active":
            rec.status = "complete"
            rec.file_url = rec.file_url or (
                f"fake://recordings/{recording_id}.{rec.spec.file_type}"
            )
        return RecordingResult(
            recording_id=recording_id,
            status=rec.status,
            file_url=rec.file_url,
            duration_s=0.0 if rec.status == "complete" else None,
            error=rec.error,
        )

    def parse_webhook(self, body: bytes, auth_header: Optional[str]) -> LiveRoomEvent:
        """No signature to verify in Fake mode — `auth_header` is
        accepted for Protocol conformance but ignored. `body` is a JSON
        document shaped like `simulate_egress_complete`'s return, e.g.
        the payload a test's webhook-handler test constructs directly.
        """
        try:
            raw = body.decode() if isinstance(body, (bytes, bytearray)) else body
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise LiveRoomError("parse_webhook", f"malformed body: {exc}") from exc
        event = payload.get("event")
        if not event:
            raise LiveRoomError("parse_webhook", "missing 'event' field")
        return LiveRoomEvent(
            event=event,
            egress_id=payload.get("egress_id"),
            room_name=payload.get("room_name"),
            status=payload.get("status"),
            file_url=payload.get("file_url"),
            raw=payload,
        )

    # ── Test-only simulation seam ────────────────────────────────────

    def simulate_egress_complete(
        self,
        recording_id: str,
        *,
        file_url: Optional[str] = None,
        status: RecordingStatus = "complete",
    ) -> LiveRoomEvent:
        """Model the `egress_ended` webhook LiveKit sends once a
        room-composite egress actually finishes — asynchronously, and
        not necessarily in response to this process's own
        `stop_recording` call. Updates `self.recordings` AND returns the
        `LiveRoomEvent` a consumer's webhook handler would receive, so a
        test can feed it straight into that handler instead of also
        constructing a JSON body for `parse_webhook`.
        """
        rec = self.recordings.get(recording_id)
        if rec is None:
            raise LiveRoomError("simulate_egress_complete", f"unknown recording_id: {recording_id!r}")
        rec.status = status
        rec.file_url = file_url or (
            f"fake://recordings/{recording_id}.{rec.spec.file_type}" if status == "complete" else None
        )
        if status != "complete":
            rec.error = "simulated egress failure"
        return LiveRoomEvent(
            event="egress_ended",
            egress_id=recording_id,
            room_name=rec.room_name,
            status=status,
            file_url=rec.file_url,
            raw={"simulated": True},
        )


__all__ = ["FakeLiveRoomProvider"]
