"""
LiveKit Service — thin therapy-platform mapper over the seed
`noctusai_lib.integrations.live_rooms` module.

Keeps the OLD dict-shaped call sites (`create_room(room_name)`,
`generate_token(room_name, participant_identity, participant_name)`,
`start_recording(room_name, segment_id)`, `stop_recording(recording_id)`,
`close_room(room_name)`) so `session_service.py` / `sessions.py` didn't
need a wholesale rewrite — but this module is now a THIN pass-through,
not a second LiveKit-calling implementation. All vendor logic (room/
egress management, JWT signing, webhook verification) lives in the
seed's `RealLiveKitProvider` / `FakeLiveRoomProvider`; re-pointed here
so no fork of that logic remains in this product.

**Fix on contact (Slice L, 2026-09-16).** The PREVIOUS version of this
file wrapped every LiveKit call in a bare `try/except`, logged the
error, and returned `{"mock": True, "error": str(e)}` — a live LiveKit
outage in prod was indistinguishable from a successful dev-mode mock
call. This module now lets `LiveRoomError` propagate; `session_service.
py` handles it explicitly per call site (see its own module docstring).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.config import settings
from noctusai_lib.integrations.live_rooms import (
    LiveRoomError,
    LiveRoomNotConfigured,
    make_live_room_provider,
)
from noctusai_lib.integrations.live_rooms.protocol import LiveRoomProvider
from noctusai_lib.integrations.live_rooms.types import RecordingSpec

__all__ = [
    "LiveRoomError",
    "LiveRoomNotConfigured",
    "create_room",
    "generate_token",
    "close_room",
    "start_recording",
    "stop_recording",
]

_provider: Optional[LiveRoomProvider] = None


def _get_provider() -> LiveRoomProvider:
    """Lazily build (and cache) the configured `LiveRoomProvider`.

    `use_fake` is set EXPLICITLY via `settings.therapy_use_fake_live_rooms`
    — NEVER inferred from missing `THERAPY_LIVEKIT_*` vars. A prod
    deploy missing them now raises `LiveRoomNotConfigured` at first use
    instead of silently degrading to mock data (the bug this slice
    fixes). Test env sets the flag explicitly in `tests/conftest.py`.
    """
    global _provider
    if _provider is None:
        _provider = make_live_room_provider(
            use_fake=settings.therapy_use_fake_live_rooms,
            url=settings.therapy_livekit_url,
            api_key=settings.therapy_livekit_api_key,
            api_secret=settings.therapy_livekit_api_secret,
        )
    return _provider


async def create_room(room_name: str) -> Dict[str, Any]:
    """Create (or reuse) a LiveKit room. Raises `LiveRoomError` on
    failure — callers decide how to degrade (see `session_service.
    _create_room_or_503`)."""
    room = await _get_provider().create_room(room_name, max_participants=2)
    return {"room_name": room.name, "sid": room.sid}


async def generate_token(
    room_name: str,
    participant_identity: str,
    participant_name: str,
) -> str:
    """Issue a join token for `participant_identity`. Raises
    `LiveRoomError` on failure."""
    return await _get_provider().issue_join_token(
        room_name, participant_identity, display_name=participant_name,
    )


async def close_room(room_name: str) -> None:
    """Close a LiveKit room. Raises `LiveRoomError` on failure."""
    await _get_provider().close_room(room_name)


async def start_recording(room_name: str, segment_id: str) -> Dict[str, Any]:
    """Start an audio-only OGG room-composite recording for one session
    segment. Raises `LiveRoomError` on failure — callers decide whether
    an unrecorded session is acceptable (see `session_service.
    _start_recording_degraded`)."""
    spec = RecordingSpec(
        file_type="ogg",
        filepath=f"recordings/{room_name}/{segment_id}.ogg",
        audio_only=True,
    )
    handle = await _get_provider().start_recording(room_name, spec)
    return {
        "recording_id": handle.recording_id,
        "room_name": room_name,
        "segment_id": segment_id,
    }


async def stop_recording(recording_id: str) -> Dict[str, Any]:
    """Stop a recording and return its file URL. Raises `LiveRoomError`
    on failure."""
    result = await _get_provider().stop_recording(recording_id)
    return {"recording_id": result.recording_id, "audio_url": result.file_url}
