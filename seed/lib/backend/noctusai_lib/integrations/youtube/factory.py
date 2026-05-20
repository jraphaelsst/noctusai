"""Factory for `YoutubeClient` — Fake or Real, by flag.

Mirrors the canonical Protocol+Fake+Real+factory shape established by
`integrations/google_calendar` + `google_maps`. The factory is the
single seam consumers reach for: pass `use_fake=True` for tests / dev,
or supply real credentials for production.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.youtube.fake import FakeYoutubeClient
from noctusai_lib.integrations.youtube.protocol import YoutubeClient


def make_youtube_client(
    *,
    use_fake: bool = False,
    api_key: str | None = None,
    oauth_credentials: Any = None,
    fake_seed_data: dict[str, Any] | None = None,
) -> YoutubeClient:
    """Build a `YoutubeClient`.

    - `use_fake=True` → returns `FakeYoutubeClient`, optionally
      pre-populated by `fake_seed_data` with keys `channels`, `videos`,
      `playlists` (each mapping id → value object). Useful for tests
      and local dev.
    - `use_fake=False` → returns `RealYoutubeClient` configured with
      `api_key` (read-only public data) OR `oauth_credentials` (any
      `google.oauth2.credentials.Credentials`-shaped object). At least
      one must be supplied; otherwise `RealYoutubeClient.__init__`
      raises `ValueError`.

    Lazy import of `RealYoutubeClient` keeps the fake path importable
    in slim environments that don't ship `google-api-python-client`."""
    if use_fake:
        seed = fake_seed_data or {}
        return FakeYoutubeClient(
            channels=seed.get("channels"),
            videos=seed.get("videos"),
            playlists=seed.get("playlists"),
            owned_channel_info=seed.get("owned_channel_info"),
            owned_videos=seed.get("owned_videos"),
        )

    # Lazy import — googleapiclient is heavy.
    from noctusai_lib.integrations.youtube.real import RealYoutubeClient

    return RealYoutubeClient(api_key=api_key, oauth_credentials=oauth_credentials)


__all__ = ["make_youtube_client"]
