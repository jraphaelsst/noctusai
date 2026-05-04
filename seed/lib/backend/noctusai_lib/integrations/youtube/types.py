"""YouTube Data API v3 client value objects.

Five frozen dataclasses make up the public type surface:

- `Channel` — wraps the `channels.list` response. Carries
  `uploads_playlist_id` so callers don't need to re-derive the
  channel→uploads-playlist trick that's central to cheap-quota
  channel-video listing.
- `Video` — wraps a `videos.list` item. `duration_seconds` is the
  ISO-8601 `contentDetails.duration` parsed to integer seconds.
- `Playlist` — minimal projection used by `playlistItems.list`
  responses; only id + title currently needed.
- `ListResult[T]` — paginated response wrapper. Carries the cumulative
  `quota_units_consumed` for the call so consumers can budget against
  the daily 10,000-unit quota.

The types are deliberately shallow (no nested raw-API blobs) so callers
get a stable contract that survives a hypothetical googleapiclient
version bump. Real / Fake adapters both produce identical instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar


@dataclass(frozen=True)
class Channel:
    """YouTube channel (the "owner" of uploaded videos)."""

    id: str
    title: str
    description: str
    uploads_playlist_id: str
    """Special auto-managed playlist holding every public upload of the
    channel, in reverse-chronological order. Returned by
    `channels.list?part=contentDetails` as
    `contentDetails.relatedPlaylists.uploads`. Use this with
    `playlistItems.list` for cheap (~2 units / 50 videos) listing
    instead of `search.list` (100 units / page)."""


@dataclass(frozen=True)
class Video:
    """YouTube video — flattened projection of `videos.list`."""

    id: str
    title: str
    description: str
    channel_id: str
    published_at: datetime
    duration_seconds: int
    """Parsed from ISO-8601 `contentDetails.duration` (e.g. `PT5M30S`)."""
    view_count: int


@dataclass(frozen=True)
class Playlist:
    """YouTube playlist — minimal projection (id + title)."""

    id: str
    title: str


T = TypeVar("T")


@dataclass(frozen=True)
class ListResult(Generic[T]):
    """Paginated list response.

    `next_page_token` is `None` when the underlying API stops returning
    `nextPageToken` (i.e. last page). `quota_units_consumed` is the
    quota cost of this single call (NOT cumulative across calls); use
    `FakeYoutubeClient.quota_units_consumed` (or wrap the real client)
    for cumulative totals."""

    items: list[T] = field(default_factory=list)
    next_page_token: str | None = None
    quota_units_consumed: int = 0


__all__ = [
    "Channel",
    "ListResult",
    "Playlist",
    "Video",
]
