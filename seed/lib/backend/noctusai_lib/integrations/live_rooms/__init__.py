"""Live video rooms + server-side recording. One vocabulary, one vendor
today (LiveKit), more later without touching a consumer.

**What this is.** The part every "video call with a recording"
integration otherwise rewrites per-vendor: create a room, issue a
per-participant join token, start/stop a composite (room-wide)
recording to S3-compatible storage, and normalize the vendor's webhook
delivery once the recording finishes. A consumer swaps LiveKit for
another provider by changing one factory call, not by hunting down
every `from livekit import ...`.

**What it is deliberately NOT.**

* Not authorization — a consumer decides WHO may join a room before it
  calls `issue_join_token`; this package has no concept of a user.
* Not egress storage lifecycle — retention/deletion of a finished
  recording's file is the consumer's concern once it has the
  `RecordingResult.file_url` (or the webhook's `LiveRoomEvent.file_url`).
* Not a webhook HTTP endpoint — `parse_webhook` normalizes a body the
  consumer's own router already received; it doesn't listen on a port.

**Recipe:**

    from noctusai_lib.integrations.live_rooms import make_live_room_provider
    from noctusai_lib.integrations.live_rooms.types import RecordingSpec, S3Output

    provider = make_live_room_provider(
        use_fake=settings.use_fake_live_rooms,
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    room = await provider.create_room("appt-123", max_participants=2)
    token = await provider.issue_join_token(room.name, "therapist-1", display_name="Terapeuta")
    handle = await provider.start_recording(
        room.name,
        RecordingSpec(
            file_type="ogg", audio_only=True, filepath=f"recordings/{room.name}.ogg",
            output=S3Output(bucket=..., region=..., endpoint=..., access_key=..., secret=...),
        ),
    )
    # ... later, once the room-composite egress finishes:
    result = await provider.stop_recording(handle.recording_id)
    assert result.status in ("complete", "failed")
"""
from __future__ import annotations

from .errors import LiveRoomError, LiveRoomNotConfigured
from .factory import make_live_room_provider
from .fake import FakeLiveRoomProvider
from .protocol import LiveRoomProvider
from .real_livekit import RealLiveKitProvider
from .types import (
    DefaultOutput,
    LiveRoomEvent,
    ParticipantInfo,
    RecordingHandle,
    RecordingResult,
    RecordingSpec,
    RecordingStatus,
    RoomInfo,
    S3Output,
)

__all__ = [
    "DefaultOutput",
    "FakeLiveRoomProvider",
    "LiveRoomError",
    "LiveRoomEvent",
    "LiveRoomNotConfigured",
    "LiveRoomProvider",
    "ParticipantInfo",
    "RealLiveKitProvider",
    "RecordingHandle",
    "RecordingResult",
    "RecordingSpec",
    "RecordingStatus",
    "RoomInfo",
    "S3Output",
    "make_live_room_provider",
]
