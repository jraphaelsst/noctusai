"""The LiveKit-backed `LiveRoomProvider`.

`livekit-api` is declared in `pyproject.toml` (every product image gets
it) but imported LAZILY inside each method — importing this module, or
exercising the Fake, must never require the SDK to be installed.

**Client construction is dependency-injected, never monkeypatched.**
`client_factory` (constructor arg) returns a fresh client per call —
`livekit.api.LiveKitAPI(url, api_key, api_secret)` by default, or a
test double exposing the same `.room` / `.egress` async surface plus an
`aclose()`. `test_real_livekit.py` injects a fake factory; nothing here
patches `livekit.api` itself.

Every failure is translated to `LiveRoomError` at the boundary — never
let a vendor exception (or a raw `aiohttp`/protobuf error) escape — so
a consumer catches one exception type regardless of provider. This is
the Slice L fix-on-contact: the OLD
`products/therapy-platform/backend/app/services/livekit_service.py`
caught every real failure and returned `{"mock": True, "error": ...}`,
which made a live LiveKit outage in prod indistinguishable from a
successful dev-mode mock call. This adapter RAISES instead.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from .errors import LiveRoomError
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

logger = logging.getLogger(__name__)

# LiveKit's own `EgressStatus` enum (int-valued protobuf enum) → our
# vocabulary. Kept permissive (unknown → "active") rather than raising,
# because a status LiveKit adds later must not crash a consumer mid-poll.
_EGRESS_STATUS_MAP: dict[str, RecordingStatus] = {
    "EGRESS_STARTING": "starting",
    "EGRESS_ACTIVE": "active",
    "EGRESS_ENDING": "ending",
    "EGRESS_COMPLETE": "complete",
    "EGRESS_FAILED": "failed",
    "EGRESS_ABORTED": "aborted",
    "EGRESS_LIMIT_REACHED": "failed",
}


async def _maybe_aclose(client: Any) -> None:
    aclose = getattr(client, "aclose", None)
    if aclose is not None:
        await aclose()


class RealLiveKitProvider:
    """Real `LiveRoomProvider` over the LiveKit server SDK (`livekit-api`)."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        api_secret: str,
        client_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        if not url or not api_key or not api_secret:
            raise ValueError(
                "RealLiveKitProvider requires non-empty url, api_key, and api_secret"
            )
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret
        self._client_factory = client_factory or self._default_client_factory

    def _default_client_factory(self) -> Any:
        from livekit import api as livekit_api  # local import — keeps this module

        return livekit_api.LiveKitAPI(self._url, self._api_key, self._api_secret)

    @staticmethod
    def _map_egress_status(raw_status: Any) -> RecordingStatus:
        # `EgressInfo.status` is a plain protobuf enum FIELD — an int at
        # runtime, not an object with `.name`. The enum TYPE itself
        # (`livekit_api.EgressStatus`) is what exposes `.Name(int)`.
        from livekit import api as livekit_api

        name = livekit_api.EgressStatus.Name(raw_status)
        return _EGRESS_STATUS_MAP.get(name, "active")

    @staticmethod
    def _to_room_info(room: Any) -> RoomInfo:
        return RoomInfo(
            name=room.name,
            sid=room.sid or None,
            max_participants=room.max_participants or None,
            num_participants=room.num_participants,
            metadata=room.metadata or None,
            creation_time=room.creation_time or None,
        )

    @staticmethod
    def _to_participant_info(p: Any) -> ParticipantInfo:
        from livekit import api as livekit_api

        state = livekit_api.ParticipantInfo.State.Name(p.state)
        return ParticipantInfo(
            identity=p.identity,
            name=p.name or None,
            state=state,
            joined_at=p.joined_at or None,
            metadata=p.metadata or None,
        )

    # ── LiveRoomProvider ─────────────────────────────────────────────

    async def create_room(
        self,
        name: str,
        *,
        max_participants: Optional[int] = None,
        empty_timeout_s: int = 600,
        metadata: Optional[str] = None,
    ) -> RoomInfo:
        from livekit import api as livekit_api

        client = self._client_factory()
        try:
            kwargs: dict[str, Any] = {"name": name, "empty_timeout": empty_timeout_s}
            if max_participants is not None:
                kwargs["max_participants"] = max_participants
            if metadata is not None:
                kwargs["metadata"] = metadata
            room = await client.room.create_room(livekit_api.CreateRoomRequest(**kwargs))
            return self._to_room_info(room)
        except Exception as exc:
            raise LiveRoomError("create_room", str(exc)) from exc
        finally:
            await _maybe_aclose(client)

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
        from datetime import timedelta

        from livekit import api as livekit_api

        try:
            token = livekit_api.AccessToken(self._api_key, self._api_secret)
            token.with_identity(identity)
            if display_name is not None:
                token.with_name(display_name)
            token.with_ttl(timedelta(seconds=ttl_s))
            token.with_grants(
                livekit_api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=can_publish,
                    can_subscribe=can_subscribe,
                )
            )
            return token.to_jwt()
        except Exception as exc:
            raise LiveRoomError("issue_join_token", str(exc)) from exc

    async def close_room(self, room: str) -> None:
        from livekit import api as livekit_api

        client = self._client_factory()
        try:
            await client.room.delete_room(livekit_api.DeleteRoomRequest(room=room))
        except Exception as exc:
            raise LiveRoomError("close_room", str(exc)) from exc
        finally:
            await _maybe_aclose(client)

    async def list_participants(self, room: str) -> List[ParticipantInfo]:
        from livekit import api as livekit_api

        client = self._client_factory()
        try:
            resp = await client.room.list_participants(
                livekit_api.ListParticipantsRequest(room=room)
            )
            return [self._to_participant_info(p) for p in resp.participants]
        except Exception as exc:
            raise LiveRoomError("list_participants", str(exc)) from exc
        finally:
            await _maybe_aclose(client)

    async def remove_participant(self, room: str, identity: str) -> None:
        from livekit import api as livekit_api

        client = self._client_factory()
        try:
            await client.room.remove_participant(
                livekit_api.RoomParticipantIdentity(room=room, identity=identity)
            )
        except Exception as exc:
            raise LiveRoomError("remove_participant", str(exc)) from exc
        finally:
            await _maybe_aclose(client)

    async def start_recording(self, room: str, spec: RecordingSpec) -> RecordingHandle:
        from livekit import api as livekit_api

        client = self._client_factory()
        try:
            file_type = {
                "mp4": livekit_api.EncodedFileType.MP4,
                "ogg": livekit_api.EncodedFileType.OGG,
            }[spec.file_type]
            output_kwargs: dict[str, Any] = {"file_type": file_type, "filepath": spec.filepath}
            if isinstance(spec.output, S3Output):
                output_kwargs["s3"] = livekit_api.S3Upload(
                    access_key=spec.output.access_key,
                    secret=spec.output.secret,
                    bucket=spec.output.bucket,
                    region=spec.output.region,
                    endpoint=spec.output.endpoint,
                    force_path_style=spec.output.force_path_style,
                )
            elif not isinstance(spec.output, DefaultOutput):
                raise LiveRoomError(
                    "start_recording", f"unsupported output type: {type(spec.output).__name__}"
                )
            file_output = livekit_api.EncodedFileOutput(**output_kwargs)
            egress = await client.egress.start_room_composite_egress(
                livekit_api.RoomCompositeEgressRequest(
                    room_name=room,
                    layout=spec.layout,
                    audio_only=spec.audio_only,
                    file_outputs=[file_output],
                )
            )
            return RecordingHandle(recording_id=egress.egress_id, room_name=room)
        except LiveRoomError:
            raise
        except Exception as exc:
            raise LiveRoomError("start_recording", str(exc)) from exc
        finally:
            await _maybe_aclose(client)

    async def stop_recording(self, recording_id: str) -> RecordingResult:
        from livekit import api as livekit_api

        client = self._client_factory()
        try:
            egress = await client.egress.stop_egress(
                livekit_api.StopEgressRequest(egress_id=recording_id)
            )
            file_url = None
            if egress.file_results:
                file_url = egress.file_results[0].location or None
            duration_s = None
            if egress.started_at and egress.ended_at:
                duration_s = (egress.ended_at - egress.started_at) / 1_000_000_000
            return RecordingResult(
                recording_id=egress.egress_id,
                status=self._map_egress_status(egress.status),
                file_url=file_url,
                duration_s=duration_s,
                error=egress.error or None,
            )
        except Exception as exc:
            raise LiveRoomError("stop_recording", str(exc)) from exc
        finally:
            await _maybe_aclose(client)

    def parse_webhook(self, body: bytes, auth_header: Optional[str]) -> LiveRoomEvent:
        from livekit import api as livekit_api

        try:
            verifier = livekit_api.TokenVerifier(self._api_key, self._api_secret)
            receiver = livekit_api.WebhookReceiver(verifier)
            raw_body = body.decode() if isinstance(body, (bytes, bytearray)) else body
            event = receiver.receive(raw_body, auth_header or "")
        except Exception as exc:
            raise LiveRoomError("parse_webhook", str(exc)) from exc

        if event.event != "egress_ended" or not event.HasField("egress_info"):
            return LiveRoomEvent(
                event=event.event,
                egress_id=None,
                room_name=event.room.name if event.HasField("room") else None,
                status=None,
                file_url=None,
                raw=event,
            )

        egress = event.egress_info
        file_url = egress.file_results[0].location if egress.file_results else None
        return LiveRoomEvent(
            event="egress_ended",
            egress_id=egress.egress_id,
            room_name=egress.room_name or None,
            status=self._map_egress_status(egress.status),
            file_url=file_url,
            raw=event,
        )


__all__ = ["RealLiveKitProvider"]
