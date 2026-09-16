"""`FakeLiveRoomProvider` — the in-memory dev/test path."""
import pytest

from noctusai_lib.integrations.live_rooms.errors import LiveRoomError
from noctusai_lib.integrations.live_rooms.fake import FakeLiveRoomProvider
from noctusai_lib.integrations.live_rooms.types import RecordingSpec, S3Output


@pytest.mark.asyncio
async def test_create_room_is_idempotent_on_name() -> None:
    provider = FakeLiveRoomProvider()
    first = await provider.create_room("room-a", max_participants=2)
    second = await provider.create_room("room-a", max_participants=2)
    assert first == second


@pytest.mark.asyncio
async def test_create_room_after_close_makes_a_fresh_room() -> None:
    provider = FakeLiveRoomProvider()
    first = await provider.create_room("room-a")
    await provider.close_room("room-a")
    second = await provider.create_room("room-a")
    assert second.sid != first.sid


@pytest.mark.asyncio
async def test_issue_join_token_tracks_participant() -> None:
    provider = FakeLiveRoomProvider()
    await provider.create_room("room-a")
    token = await provider.issue_join_token("room-a", "user-1", display_name="Ana")
    assert token
    participants = await provider.list_participants("room-a")
    assert [p.identity for p in participants] == ["user-1"]
    assert participants[0].name == "Ana"


@pytest.mark.asyncio
async def test_issue_join_token_on_unknown_room_auto_vivifies() -> None:
    """Mirrors `RealLiveKitProvider`: token issuance never validates room
    existence (pure JWT signing, no network call) — a consumer that
    issues a token before/without an explicit `create_room` must not be
    rejected by the Fake for a constraint the Real path doesn't enforce."""
    provider = FakeLiveRoomProvider()
    token = await provider.issue_join_token("nope", "user-1")
    assert token
    participants = await provider.list_participants("nope")
    assert [p.identity for p in participants] == ["user-1"]


@pytest.mark.asyncio
async def test_remove_participant() -> None:
    provider = FakeLiveRoomProvider()
    await provider.create_room("room-a")
    await provider.issue_join_token("room-a", "user-1")
    await provider.remove_participant("room-a", "user-1")
    assert await provider.list_participants("room-a") == []


@pytest.mark.asyncio
async def test_close_room_clears_participants() -> None:
    provider = FakeLiveRoomProvider()
    await provider.create_room("room-a")
    await provider.issue_join_token("room-a", "user-1")
    await provider.close_room("room-a")
    assert await provider.list_participants("room-a") == []


@pytest.mark.asyncio
async def test_start_recording_on_unknown_room_raises() -> None:
    provider = FakeLiveRoomProvider()
    spec = RecordingSpec(file_type="ogg", filepath="x.ogg", audio_only=True)
    with pytest.raises(LiveRoomError):
        await provider.start_recording("nope", spec)


@pytest.mark.asyncio
async def test_stop_recording_immediately_completes_by_default() -> None:
    provider = FakeLiveRoomProvider()
    await provider.create_room("room-a")
    handle = await provider.start_recording(
        "room-a", RecordingSpec(file_type="ogg", filepath="x.ogg", audio_only=True)
    )
    result = await provider.stop_recording(handle.recording_id)
    assert result.status == "complete"
    assert result.file_url == f"fake://recordings/{handle.recording_id}.ogg"


@pytest.mark.asyncio
async def test_stop_recording_unknown_id_raises() -> None:
    provider = FakeLiveRoomProvider()
    with pytest.raises(LiveRoomError):
        await provider.stop_recording("nope")


@pytest.mark.asyncio
async def test_simulate_egress_complete_before_stop_recording() -> None:
    """Models the real-world race: the `egress_ended` webhook can arrive
    asynchronously, independent of a `stop_recording` call."""
    provider = FakeLiveRoomProvider()
    await provider.create_room("room-a")
    handle = await provider.start_recording(
        "room-a",
        RecordingSpec(
            file_type="mp4",
            filepath="x.mp4",
            output=S3Output(
                bucket="b", region="r", endpoint="e", access_key="ak", secret="sk"
            ),
        ),
    )
    event = provider.simulate_egress_complete(handle.recording_id, file_url="s3://b/x.mp4")
    assert event.event == "egress_ended"
    assert event.status == "complete"
    assert event.file_url == "s3://b/x.mp4"

    # stop_recording afterwards reports the already-completed state, not a
    # second "freshly completed" transition.
    result = await provider.stop_recording(handle.recording_id)
    assert result.status == "complete"
    assert result.file_url == "s3://b/x.mp4"


@pytest.mark.asyncio
async def test_simulate_egress_failure() -> None:
    provider = FakeLiveRoomProvider()
    await provider.create_room("room-a")
    handle = await provider.start_recording(
        "room-a", RecordingSpec(file_type="ogg", filepath="x.ogg")
    )
    event = provider.simulate_egress_complete(handle.recording_id, status="failed")
    assert event.status == "failed"
    assert event.file_url is None


def test_parse_webhook_roundtrips_simulated_event() -> None:
    import json

    provider = FakeLiveRoomProvider()
    body = json.dumps(
        {
            "event": "egress_ended",
            "egress_id": "fake-rec-1",
            "room_name": "room-a",
            "status": "complete",
            "file_url": "fake://recordings/fake-rec-1.ogg",
        }
    ).encode()
    event = provider.parse_webhook(body, auth_header=None)
    assert event.event == "egress_ended"
    assert event.egress_id == "fake-rec-1"
    assert event.file_url == "fake://recordings/fake-rec-1.ogg"


def test_parse_webhook_malformed_body_raises() -> None:
    provider = FakeLiveRoomProvider()
    with pytest.raises(LiveRoomError):
        provider.parse_webhook(b"not json", auth_header=None)


def test_parse_webhook_missing_event_field_raises() -> None:
    provider = FakeLiveRoomProvider()
    with pytest.raises(LiveRoomError):
        provider.parse_webhook(b"{}", auth_header=None)
