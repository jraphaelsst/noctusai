"""The `LiveRoomProvider` Protocol both `RealLiveKitProvider` and
`FakeLiveRoomProvider` implement."""
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from .types import ParticipantInfo, RecordingHandle, RecordingResult, RecordingSpec, RoomInfo


@runtime_checkable
class LiveRoomProvider(Protocol):
    """Create/join/record a live video room. One vocabulary, N vendors
    (LiveKit today).

    Every method is `async` — including `issue_join_token`, which does
    no IO of its own in the LiveKit adapter (pure JWT signing) — so that
    a consumer written against this Protocol never has to special-case
    "this one call happens to be sync." Therapy's existing call sites
    already `await` every one of these.

    Deliberately narrow. It does **not** own:

    * **who is allowed to join** — that's the consumer's own
      authorization check before it calls `issue_join_token`;
    * **egress storage lifecycle** (retention, deletion) — the consumer
      owns what happens to a file once `RecordingResult.file_url` names
      it;
    * **the webhook HTTP endpoint** — `parse_webhook` only normalizes a
      body- already-received-by-the-consumer's-router into a
      `LiveRoomEvent`; routing/verifying the request reached the right
      handler is the consumer's router.
    """

    async def create_room(
        self,
        name: str,
        *,
        max_participants: Optional[int] = None,
        empty_timeout_s: int = 600,
        metadata: Optional[str] = None,
    ) -> RoomInfo:
        """Create a room, or return the existing one if `name` already
        exists (LiveKit's own `CreateRoom` is idempotent on name)."""
        ...

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
        """Return a signed JWT a client SDK uses to join `room` as
        `identity`."""
        ...

    async def close_room(self, room: str) -> None:
        """Delete a room, disconnecting any remaining participants."""
        ...

    async def list_participants(self, room: str) -> List[ParticipantInfo]:
        ...

    async def remove_participant(self, room: str, identity: str) -> None:
        ...

    async def start_recording(self, room: str, spec: RecordingSpec) -> RecordingHandle:
        """Start a room-composite egress recording. Returns immediately
        with a handle — the recording itself finishes asynchronously
        (poll `stop_recording`'s return, or consume the
        `egress_ended` webhook via `parse_webhook`)."""
        ...

    async def stop_recording(self, recording_id: str) -> RecordingResult:
        ...

    def parse_webhook(self, body: bytes, auth_header: Optional[str]):
        """Verify + normalize a LiveKit webhook POST body into a
        `LiveRoomEvent`. Sync — no IO, just signature verification +
        protobuf parsing. Raises `LiveRoomError` on a bad signature or
        malformed body."""
        ...


__all__ = ["LiveRoomProvider"]
