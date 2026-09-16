"""The single seam consumers reach for — Fake or the Real LiveKit
provider, by flag."""
from __future__ import annotations

from typing import Any, Callable, Optional, Union

from .errors import LiveRoomNotConfigured
from .fake import FakeLiveRoomProvider
from .real_livekit import RealLiveKitProvider


def make_live_room_provider(
    *,
    use_fake: bool = False,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    client_factory: Optional[Callable[[], Any]] = None,
) -> Union[FakeLiveRoomProvider, RealLiveKitProvider]:
    """Build a `LiveRoomProvider`. Both branches satisfy the same
    Protocol, so a consumer selects here once and never branches on the
    provider afterward.

    Args:
        use_fake: when True, return `FakeLiveRoomProvider` regardless of
            `url`/`api_key`/`api_secret` — the dev/test path. A
            consumer MUST select this explicitly (e.g. from its own
            settings/env), never as a silent fallback when credentials
            happen to be missing in a prod-like environment — that
            silent-fallback shape is exactly what Slice L removed from
            therapy-platform's old `livekit_service.py`.
        url / api_key / api_secret: required when `use_fake=False`.
        client_factory: forwarded to `RealLiveKitProvider` — the DI seam
            for tests; leave `None` in production code.

    Raises:
        LiveRoomNotConfigured: `use_fake=False` and any of
            `url`/`api_key`/`api_secret` is missing.
    """
    if use_fake:
        return FakeLiveRoomProvider()

    missing = [
        name
        for name, value in (("url", url), ("api_key", api_key), ("api_secret", api_secret))
        if not value
    ]
    if missing:
        raise LiveRoomNotConfigured(
            f"make_live_room_provider: missing required config for the real "
            f"provider: {', '.join(missing)}"
        )
    return RealLiveKitProvider(
        url=url,  # type: ignore[arg-type]
        api_key=api_key,  # type: ignore[arg-type]
        api_secret=api_secret,  # type: ignore[arg-type]
        client_factory=client_factory,
    )


__all__ = ["make_live_room_provider"]
