"""
LiveKit Service — Room management, token generation, recording control.

All LiveKit calls are wrapped in try/except with graceful degradation.
If THERAPY_LIVEKIT_* vars are not set, the service operates in mock mode
and returns placeholder data suitable for development.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _is_mock_mode() -> bool:
    """Check whether LiveKit credentials are configured."""
    return not all([
        settings.therapy_livekit_url,
        settings.therapy_livekit_api_key,
        settings.therapy_livekit_api_secret,
    ])


def _get_livekit_api():
    """Lazy-import and return the LiveKit API client.

    Returns None if livekit-api is not installed or credentials missing.
    """
    if _is_mock_mode():
        return None
    try:
        from livekit import api as livekit_api  # type: ignore[import-untyped]
        return livekit_api
    except ImportError:
        logger.warning("livekit-api package not installed — operating in mock mode")
        return None


# ---------------------------------------------------------------------------
# Room Management
# ---------------------------------------------------------------------------

async def create_room(room_name: str) -> Dict[str, Any]:
    """Create a LiveKit room.

    In mock mode, returns synthetic room data.
    """
    lk = _get_livekit_api()
    if lk is None:
        logger.info("LiveKit mock: create_room(%s)", room_name)
        return {"room_name": room_name, "mock": True, "sid": f"mock-room-{room_name}"}

    try:
        room_service = lk.RoomServiceClient(
            settings.therapy_livekit_url,
            settings.therapy_livekit_api_key,
            settings.therapy_livekit_api_secret,
        )
        room = await room_service.create_room(
            lk.CreateRoomRequest(name=room_name, empty_timeout=600, max_participants=2),
        )
        return {"room_name": room.name, "sid": room.sid, "mock": False}
    except Exception as e:
        logger.error("LiveKit create_room failed: %s", e)
        return {"room_name": room_name, "mock": True, "error": str(e)}


async def generate_token(
    room_name: str,
    participant_identity: str,
    participant_name: str,
) -> str:
    """Generate a JWT token for room access.

    In mock mode, returns a placeholder string.
    """
    lk = _get_livekit_api()
    if lk is None:
        logger.info(
            "LiveKit mock: generate_token(room=%s, identity=%s)",
            room_name,
            participant_identity,
        )
        return f"mock-token-{room_name}-{participant_identity}-{int(time.time())}"

    try:
        token = lk.AccessToken(
            settings.therapy_livekit_api_key,
            settings.therapy_livekit_api_secret,
        )
        token.with_identity(participant_identity)
        token.with_name(participant_name)
        token.with_grants(
            lk.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ),
        )
        return token.to_jwt()
    except Exception as e:
        logger.error("LiveKit generate_token failed: %s", e)
        return f"mock-token-{room_name}-{participant_identity}-{int(time.time())}"


async def close_room(room_name: str) -> bool:
    """Close/delete a LiveKit room.

    Returns True on success, False on failure.
    """
    lk = _get_livekit_api()
    if lk is None:
        logger.info("LiveKit mock: close_room(%s)", room_name)
        return True

    try:
        room_service = lk.RoomServiceClient(
            settings.therapy_livekit_url,
            settings.therapy_livekit_api_key,
            settings.therapy_livekit_api_secret,
        )
        await room_service.delete_room(lk.DeleteRoomRequest(room=room_name))
        return True
    except Exception as e:
        logger.error("LiveKit close_room failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

async def start_recording(room_name: str, segment_id: str) -> Dict[str, Any]:
    """Start server-side audio recording for a room.

    In mock mode, returns synthetic recording info.
    """
    lk = _get_livekit_api()
    if lk is None:
        logger.info("LiveKit mock: start_recording(room=%s, segment=%s)", room_name, segment_id)
        return {
            "recording_id": f"mock-rec-{segment_id}",
            "room_name": room_name,
            "segment_id": segment_id,
            "mock": True,
        }

    try:
        egress_service = lk.EgressServiceClient(
            settings.therapy_livekit_url,
            settings.therapy_livekit_api_key,
            settings.therapy_livekit_api_secret,
        )
        output = lk.EncodedFileOutput(
            file_type=lk.EncodedFileType.OGG,
            filepath=f"recordings/{room_name}/{segment_id}.ogg",
        )
        egress = await egress_service.start_room_composite_egress(
            lk.RoomCompositeEgressRequest(
                room_name=room_name,
                file_outputs=[output],
                audio_only=True,
            ),
        )
        return {
            "recording_id": egress.egress_id,
            "room_name": room_name,
            "segment_id": segment_id,
            "mock": False,
        }
    except Exception as e:
        logger.error("LiveKit start_recording failed: %s", e)
        return {
            "recording_id": f"mock-rec-{segment_id}",
            "room_name": room_name,
            "segment_id": segment_id,
            "mock": True,
            "error": str(e),
        }


async def stop_recording(recording_id: str) -> Dict[str, Any]:
    """Stop a recording and return audio file info.

    In mock mode, returns synthetic file URL.
    """
    lk = _get_livekit_api()
    if lk is None:
        logger.info("LiveKit mock: stop_recording(%s)", recording_id)
        return {
            "recording_id": recording_id,
            "audio_url": f"mock://recordings/{recording_id}.ogg",
            "mock": True,
        }

    try:
        egress_service = lk.EgressServiceClient(
            settings.therapy_livekit_url,
            settings.therapy_livekit_api_key,
            settings.therapy_livekit_api_secret,
        )
        result = await egress_service.stop_egress(
            lk.StopEgressRequest(egress_id=recording_id),
        )
        # Extract file URL from result
        audio_url = None
        if result.file_results:
            audio_url = result.file_results[0].download_url
        return {
            "recording_id": recording_id,
            "audio_url": audio_url,
            "mock": False,
        }
    except Exception as e:
        logger.error("LiveKit stop_recording failed: %s", e)
        return {
            "recording_id": recording_id,
            "audio_url": None,
            "mock": True,
            "error": str(e),
        }
