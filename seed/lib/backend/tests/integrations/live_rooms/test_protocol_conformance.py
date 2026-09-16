"""Both providers satisfy `LiveRoomProvider` structurally.

`LiveRoomProvider` is `@runtime_checkable`, so `isinstance` checks the
method NAMES exist (not signatures) — this is a cheap tripwire against
"Real renamed a method and Fake didn't follow" drift, not a substitute
for the behavioral tests in `test_fake.py` / `test_real_livekit.py`.
"""
from noctusai_lib.integrations.live_rooms.fake import FakeLiveRoomProvider
from noctusai_lib.integrations.live_rooms.protocol import LiveRoomProvider
from noctusai_lib.integrations.live_rooms.real_livekit import RealLiveKitProvider


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeLiveRoomProvider(), LiveRoomProvider)


def test_real_satisfies_protocol() -> None:
    provider = RealLiveKitProvider(url="https://x", api_key="k", api_secret="s")
    assert isinstance(provider, LiveRoomProvider)


def test_protocol_declares_every_method_both_implement() -> None:
    expected = {
        "create_room",
        "issue_join_token",
        "close_room",
        "list_participants",
        "remove_participant",
        "start_recording",
        "stop_recording",
        "parse_webhook",
    }
    fake_methods = {name for name in expected if hasattr(FakeLiveRoomProvider, name)}
    real_methods = {name for name in expected if hasattr(RealLiveKitProvider, name)}
    assert fake_methods == expected
    assert real_methods == expected
