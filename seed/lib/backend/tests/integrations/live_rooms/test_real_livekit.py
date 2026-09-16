"""`RealLiveKitProvider` — a fake `client_factory` is injected through the
constructor (the DI seam per the module's own docstring); nothing here
monkeypatches `livekit.api` itself.
"""
import base64
import hashlib

import pytest
from google.protobuf.json_format import MessageToJson
from livekit import api as lk

from noctusai_lib.integrations.live_rooms.errors import LiveRoomError
from noctusai_lib.integrations.live_rooms.real_livekit import RealLiveKitProvider
from noctusai_lib.integrations.live_rooms.types import RecordingSpec, S3Output

API_KEY = "test-key"
API_SECRET = "test-secret-32-bytes-minimum!!!!"


class _FakeRoomService:
    def __init__(self) -> None:
        self.deleted = []
        self.removed = []
        self.raise_on = None

    async def create_room(self, req):
        if self.raise_on == "create_room":
            raise RuntimeError("boom")
        return lk.Room(
            name=req.name,
            sid="RM_fake",
            max_participants=req.max_participants,
            num_participants=0,
            metadata=req.metadata,
        )

    async def delete_room(self, req):
        self.deleted.append(req.room)
        return lk.DeleteRoomResponse()

    async def list_participants(self, req):
        return lk.ListParticipantsResponse(
            participants=[
                lk.ParticipantInfo(identity="user-1", name="Ana", joined_at=1000),
            ]
        )

    async def remove_participant(self, req):
        self.removed.append((req.room, req.identity))
        return lk.RemoveParticipantResponse()


class _FakeEgressService:
    def __init__(self) -> None:
        self.raise_on = None

    async def start_room_composite_egress(self, req):
        if self.raise_on == "start_recording":
            raise RuntimeError("egress boom")
        return lk.EgressInfo(
            egress_id="EG_fake",
            room_name=req.room_name,
            status=lk.EgressStatus.EGRESS_STARTING,
        )

    async def stop_egress(self, req):
        return lk.EgressInfo(
            egress_id=req.egress_id,
            status=lk.EgressStatus.EGRESS_COMPLETE,
            file_results=[lk.FileInfo(location="s3://bucket/rec.ogg")],
            started_at=1_000_000_000,
            ended_at=6_000_000_000,
        )


class _FakeClient:
    def __init__(self) -> None:
        self.room = _FakeRoomService()
        self.egress = _FakeEgressService()
        self.aclose_calls = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


@pytest.fixture()
def fake_client() -> _FakeClient:
    return _FakeClient()


@pytest.fixture()
def provider(fake_client: _FakeClient) -> RealLiveKitProvider:
    return RealLiveKitProvider(
        url="https://lk.example.com",
        api_key=API_KEY,
        api_secret=API_SECRET,
        client_factory=lambda: fake_client,
    )


def test_constructor_requires_all_credentials() -> None:
    with pytest.raises(ValueError):
        RealLiveKitProvider(url="", api_key=API_KEY, api_secret=API_SECRET)
    with pytest.raises(ValueError):
        RealLiveKitProvider(url="https://x", api_key="", api_secret=API_SECRET)
    with pytest.raises(ValueError):
        RealLiveKitProvider(url="https://x", api_key=API_KEY, api_secret="")


@pytest.mark.asyncio
async def test_create_room_maps_fields_and_closes_client(
    provider: RealLiveKitProvider, fake_client: _FakeClient
) -> None:
    room = await provider.create_room("room-a", max_participants=2, metadata="m")
    assert room.name == "room-a"
    assert room.sid == "RM_fake"
    assert room.max_participants == 2
    assert room.metadata == "m"
    assert fake_client.aclose_calls == 1


@pytest.mark.asyncio
async def test_create_room_wraps_provider_failure(
    provider: RealLiveKitProvider, fake_client: _FakeClient
) -> None:
    fake_client.room.raise_on = "create_room"
    with pytest.raises(LiveRoomError) as exc_info:
        await provider.create_room("room-a")
    assert exc_info.value.op == "create_room"
    # the client is still closed even on failure
    assert fake_client.aclose_calls == 1


@pytest.mark.asyncio
async def test_issue_join_token_returns_a_jwt(provider: RealLiveKitProvider) -> None:
    token = await provider.issue_join_token(
        "room-a", "therapist-1", display_name="Terapeuta", ttl_s=60
    )
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature


@pytest.mark.asyncio
async def test_close_room_calls_delete(
    provider: RealLiveKitProvider, fake_client: _FakeClient
) -> None:
    await provider.close_room("room-a")
    assert fake_client.room.deleted == ["room-a"]


@pytest.mark.asyncio
async def test_list_participants_maps_state_enum(provider: RealLiveKitProvider) -> None:
    participants = await provider.list_participants("room-a")
    assert len(participants) == 1
    assert participants[0].identity == "user-1"
    assert participants[0].name == "Ana"
    # unset State field (proto default 0) maps to its enum NAME, not the
    # raw int — this caught a real bug during authoring (`state` came back
    # as the string "0" before the fix).
    assert participants[0].state == "JOINING"


@pytest.mark.asyncio
async def test_remove_participant(
    provider: RealLiveKitProvider, fake_client: _FakeClient
) -> None:
    await provider.remove_participant("room-a", "user-1")
    assert fake_client.room.removed == [("room-a", "user-1")]


@pytest.mark.asyncio
async def test_start_recording_with_s3_output(provider: RealLiveKitProvider) -> None:
    spec = RecordingSpec(
        file_type="mp4",
        filepath="recordings/room-a.mp4",
        output=S3Output(
            bucket="b", region="us-east-1", endpoint="https://s3.example.com",
            access_key="ak", secret="sk",
        ),
    )
    handle = await provider.start_recording("room-a", spec)
    assert handle.recording_id == "EG_fake"
    assert handle.room_name == "room-a"


@pytest.mark.asyncio
async def test_start_recording_wraps_provider_failure(
    provider: RealLiveKitProvider, fake_client: _FakeClient
) -> None:
    fake_client.egress.raise_on = "start_recording"
    with pytest.raises(LiveRoomError) as exc_info:
        await provider.start_recording(
            "room-a", RecordingSpec(file_type="ogg", filepath="x.ogg")
        )
    assert exc_info.value.op == "start_recording"


@pytest.mark.asyncio
async def test_stop_recording_maps_status_and_duration(
    provider: RealLiveKitProvider,
) -> None:
    result = await provider.stop_recording("EG_fake")
    assert result.status == "complete"
    assert result.file_url == "s3://bucket/rec.ogg"
    assert result.duration_s == pytest.approx(5.0)


def test_parse_webhook_valid_signature_maps_egress_ended(
    provider: RealLiveKitProvider,
) -> None:
    event = lk.WebhookEvent(
        event="egress_ended",
        egress_info=lk.EgressInfo(
            egress_id="EG_1",
            room_name="room-a",
            status=lk.EgressStatus.EGRESS_COMPLETE,
            file_results=[lk.FileInfo(location="s3://bucket/rec.ogg")],
        ),
    )
    body = MessageToJson(event).encode()
    token = _sign_body(body)

    parsed = provider.parse_webhook(body, token)
    assert parsed.event == "egress_ended"
    assert parsed.egress_id == "EG_1"
    assert parsed.room_name == "room-a"
    assert parsed.status == "complete"
    assert parsed.file_url == "s3://bucket/rec.ogg"


def test_parse_webhook_other_event_type_still_parses(
    provider: RealLiveKitProvider,
) -> None:
    event = lk.WebhookEvent(event="room_started", room=lk.Room(name="room-a"))
    body = MessageToJson(event).encode()
    token = _sign_body(body)

    parsed = provider.parse_webhook(body, token)
    assert parsed.event == "room_started"
    assert parsed.room_name == "room-a"
    assert parsed.status is None


def test_parse_webhook_bad_signature_raises(provider: RealLiveKitProvider) -> None:
    body = MessageToJson(lk.WebhookEvent(event="egress_ended")).encode()
    with pytest.raises(LiveRoomError) as exc_info:
        provider.parse_webhook(body, "not-a-real-jwt")
    assert exc_info.value.op == "parse_webhook"


def test_parse_webhook_tampered_body_raises(provider: RealLiveKitProvider) -> None:
    body = MessageToJson(lk.WebhookEvent(event="egress_ended")).encode()
    token = _sign_body(body)
    tampered = body + b" "
    with pytest.raises(LiveRoomError):
        provider.parse_webhook(tampered, token)


def _sign_body(body: bytes) -> str:
    digest = hashlib.sha256(body).digest()
    sha256_b64 = base64.b64encode(digest).decode()
    return lk.AccessToken(API_KEY, API_SECRET).with_sha256(sha256_b64).to_jwt()
