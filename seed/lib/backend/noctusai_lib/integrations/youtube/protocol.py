"""YouTube Data API v3 client Protocol.

The seed encodes correct quota math at the contract level so consumers
never re-derive it. YouTube's daily quota defaults to 10,000 units;
the wrong listing strategy (`search.list` at 100 units/page) burns the
budget in 100 calls. The right strategy
(`channels.list` → uploads-playlist → `playlistItems.list` →
`videos.list`) costs ~2 units per page of 50 videos.

The Protocol's docstrings document the per-method quota cost so any
consumer reading the surface picks the cheap path by default.
"""

from __future__ import annotations

from typing import Protocol

from noctusai_lib.integrations.youtube.types import (
    Channel,
    ListResult,
    Video,
)


class YoutubeClient(Protocol):
    """YouTube Data API v3 client contract.

    Two concrete implementations ship in the seed:
    - `FakeYoutubeClient` — deterministic in-memory dev/test default.
      Tracks cumulative `quota_units_consumed` for assertions.
    - `RealYoutubeClient` — wraps `googleapiclient.discovery.build`.
      Logs API errors at WARN level before re-raising.

    Build via `make_youtube_client(...)`. The factory routes based on
    `use_fake` flag — see `factory.py`.

    **Quota math (YouTube daily default = 10,000 units):**

    | Method | Cost | Notes |
    |---|---|---|
    | `get_channel` | 1 | `channels.list` is 1 unit per call. |
    | `list_channel_videos` | ~2 / page of 50 | Two API calls: `playlistItems.list` (1 unit) returns up to 50 video IDs, then `videos.list` (1 unit) fetches details for the batch. The cheap path. |
    | `get_video` | 1 | `videos.list` with one ID is 1 unit. |
    | `search` | **100** | `search.list` is 100 units per page (1% of daily quota per call). PREFER `list_channel_videos` for channel-scoped listings. |

    The `ListResult.quota_units_consumed` field carries the per-call
    cost so consumers can budget against the daily quota."""

    async def get_channel(self, channel_id: str) -> Channel | None:
        """Fetch a channel by id.

        **Quota cost: 1 unit** (`channels.list?part=snippet,contentDetails`).

        Returns `None` when the channel doesn't exist."""
        ...

    async def list_channel_videos(
        self,
        channel_id: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """List a channel's uploaded videos, newest first.

        **Quota cost: ~2 units per page of 50 videos.** Implementation:
        1. Fetch the channel's `uploads_playlist_id` (cached after first call
           OR resolved per-call by `channels.list` — 1 unit).
        2. `playlistItems.list?playlistId=<uploads>` returns 50 video IDs (1 unit).
        3. `videos.list?id=<id1,id2,...,id50>` fetches details for the batch (1 unit).

        This is the cheap path. NEVER use `search.list?channelId=...` for the
        same purpose — `search.list` costs 100 units per page (50× more)."""
        ...

    async def get_video(self, video_id: str) -> Video | None:
        """Fetch a single video by id.

        **Quota cost: 1 unit** (`videos.list?id=<video_id>`).

        Returns `None` when the video doesn't exist or has been removed."""
        ...

    async def search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """Free-text video search.

        **Quota cost: 100 units per page** (`search.list` is the most
        expensive endpoint in the API). Calling this 100×/day burns the
        full default quota — measure carefully before exposing it
        in any user-facing surface.

        For channel-scoped listings (newest videos from one channel),
        use `list_channel_videos(channel_id)` instead — same data, ~50×
        cheaper."""
        ...


__all__ = ["YoutubeClient"]
