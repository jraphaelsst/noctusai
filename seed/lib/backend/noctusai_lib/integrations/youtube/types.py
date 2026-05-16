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
from typing import Generic, Literal, TypeVar

PrivacyStatus = Literal["private", "unlisted", "public"]
"""YouTube `status.privacyStatus`. Seed default is ``"private"`` —
nothing goes public unless the caller explicitly opts in (matches the
validated workspace rule: "se o usuário não pedir explicitamente
'público' ou 'não listado', suba como private")."""

TITLE_MAX_LEN = 100
"""YouTube hard limit on `snippet.title`. Longer titles are rejected
by `videos.insert`; callers should truncate before calling."""

DESCRIPTION_MAX_LEN = 5000
"""YouTube hard limit on `snippet.description`."""

UPLOAD_QUOTA_UNITS = 1600
"""`videos.insert` costs **1600 units** against the 10,000/day default
quota — by far the most expensive call in the API (≈6 uploads exhaust
a fresh daily quota). Documented here so consumers budget correctly;
the often-quoted "100" figure is the *listing* search cost, not insert."""


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


@dataclass(frozen=True)
class VideoUpload:
    """Result of a `videos.insert` (resumable upload).

    `video_id` is the newly-created YouTube id; `url` is the canonical
    watch URL. `quota_units_consumed` is fixed at
    :data:`UPLOAD_QUOTA_UNITS` (1600) — surfaced so the caller can
    decrement a daily-quota budget the same way `ListResult` does for
    read calls. `privacy_status` echoes back what the upload was
    created with (the caller may have defaulted it to ``"private"``)."""

    video_id: str
    title: str
    url: str
    privacy_status: PrivacyStatus
    quota_units_consumed: int = UPLOAD_QUOTA_UNITS


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
    "DESCRIPTION_MAX_LEN",
    "TITLE_MAX_LEN",
    "UPLOAD_QUOTA_UNITS",
    "Channel",
    "ListResult",
    "Playlist",
    "PrivacyStatus",
    "Video",
    "VideoUpload",
]
