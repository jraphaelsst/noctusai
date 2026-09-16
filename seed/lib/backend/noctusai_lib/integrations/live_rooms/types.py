"""Provider-agnostic value objects for live video rooms + recordings.

Pure: no IO, no vendor SDK import at module scope. The point of this
module is that `RoomInfo`/`RecordingResult`/etc. mean the same thing
whether the room provider is LiveKit or (later) something else — a
consumer never branches on which vendor is configured.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union


@dataclass(frozen=True)
class RoomInfo:
    """A created/existing room, as reported by the provider."""

    name: str
    sid: Optional[str] = None
    max_participants: Optional[int] = None
    num_participants: int = 0
    metadata: Optional[str] = None
    creation_time: Optional[int] = None  # epoch seconds


@dataclass(frozen=True)
class ParticipantInfo:
    """One participant currently (or recently) in a room."""

    identity: str
    name: Optional[str] = None
    state: Optional[str] = None
    joined_at: Optional[int] = None  # epoch seconds
    metadata: Optional[str] = None


@dataclass(frozen=True)
class S3Output:
    """An S3-compatible egress destination.

    Covers Supabase Storage's S3-compatible endpoint and Cloudflare R2
    equally — both are "S3 with a custom endpoint + force-path-style",
    never a vendor-specific output type.
    """

    bucket: str
    region: str
    endpoint: str
    access_key: str
    secret: str
    force_path_style: bool = True


@dataclass(frozen=True)
class DefaultOutput:
    """Use the LiveKit-deployment-configured default file store.

    Some LiveKit deployments configure a default S3/GCS/Azure egress
    store server-side; a consumer that doesn't need per-recording
    destination control (or doesn't have its own bucket credentials)
    passes this instead of an explicit `S3Output`.
    """


@dataclass(frozen=True)
class RecordingSpec:
    """What to record and where to put it.

    `filepath` is relative to whatever store `output` resolves to (an
    explicit `S3Output` bucket, or the deployment default for
    `DefaultOutput`) — never an absolute local path; egress writes to
    object storage, not the LiveKit server's disk.
    """

    file_type: Literal["mp4", "ogg"]
    filepath: str
    audio_only: bool = False
    layout: str = "grid"
    output: Union[S3Output, DefaultOutput] = field(default_factory=DefaultOutput)


@dataclass(frozen=True)
class RecordingHandle:
    """Returned immediately by `start_recording` — egress has been
    requested, not necessarily finished starting."""

    recording_id: str
    room_name: str


#: Normalized egress outcome. `"active"`/`"starting"`/`"ending"` are
#: transitional states a `stop_recording` caller does not usually see
#: (it just requested a stop) but are included for completeness /
#: webhook consumers that poll status mid-flight.
RecordingStatus = Literal[
    "starting", "active", "ending", "complete", "failed", "aborted",
]


@dataclass(frozen=True)
class RecordingResult:
    """The outcome of a `stop_recording` call, or an `egress_ended`
    webhook event once `parse_webhook` normalizes it."""

    recording_id: str
    status: RecordingStatus
    file_url: Optional[str] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class LiveRoomEvent:
    """A normalized webhook event from the room provider.

    `parse_webhook` only fully populates `status`/`file_url` for
    `event == "egress_ended"` — the one event type Slice L's consumers
    need. Other event types still parse (so a consumer can at least log
    them / route by `event`) but carry `raw` for anything else.
    """

    event: str
    egress_id: Optional[str] = None
    room_name: Optional[str] = None
    status: Optional[RecordingStatus] = None
    file_url: Optional[str] = None
    raw: Any = None


__all__ = [
    "DefaultOutput",
    "LiveRoomEvent",
    "ParticipantInfo",
    "RecordingHandle",
    "RecordingResult",
    "RecordingSpec",
    "RecordingStatus",
    "RoomInfo",
    "S3Output",
]
