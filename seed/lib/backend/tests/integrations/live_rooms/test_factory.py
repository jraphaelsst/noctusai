"""`make_live_room_provider` — the one seam a consumer touches."""
import pytest

from noctusai_lib.integrations.live_rooms.errors import LiveRoomNotConfigured
from noctusai_lib.integrations.live_rooms.factory import make_live_room_provider
from noctusai_lib.integrations.live_rooms.fake import FakeLiveRoomProvider
from noctusai_lib.integrations.live_rooms.real_livekit import RealLiveKitProvider


def test_use_fake_wins_regardless_of_missing_config() -> None:
    provider = make_live_room_provider(use_fake=True)
    assert isinstance(provider, FakeLiveRoomProvider)


def test_use_fake_ignores_partial_real_config() -> None:
    provider = make_live_room_provider(use_fake=True, url="https://x")
    assert isinstance(provider, FakeLiveRoomProvider)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"url": "https://x"},
        {"url": "https://x", "api_key": "k"},
        {"api_key": "k", "api_secret": "s"},
    ],
)
def test_real_provider_requires_full_config(kwargs: dict) -> None:
    with pytest.raises(LiveRoomNotConfigured):
        make_live_room_provider(use_fake=False, **kwargs)


def test_real_provider_builds_with_full_config() -> None:
    provider = make_live_room_provider(
        use_fake=False, url="https://lk.example.com", api_key="k", api_secret="s"
    )
    assert isinstance(provider, RealLiveKitProvider)


def test_client_factory_is_forwarded() -> None:
    sentinel = object()
    provider = make_live_room_provider(
        use_fake=False,
        url="https://lk.example.com",
        api_key="k",
        api_secret="s",
        client_factory=lambda: sentinel,
    )
    assert isinstance(provider, RealLiveKitProvider)
    assert provider._client_factory() is sentinel
