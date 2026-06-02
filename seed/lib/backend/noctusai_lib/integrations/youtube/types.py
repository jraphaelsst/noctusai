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

UploadStatus = Literal[
    "uploaded",
    "processed",
    "failed",
    "rejected",
    "deleted",
    "unknown",
]
"""YouTube ``status.uploadStatus`` — the lifecycle state of the upload
itself. ``"unknown"`` is the seed's safe-default when the API omits the
field (never raises; consumers branch on the explicit literal).

Terminal "ready-to-share" state is ``"processed"`` AND
:data:`ProcStatus` ``"succeeded"``. ``"failed"`` / ``"rejected"`` /
``"deleted"`` are unrecoverable; the operator surface should mark the
job failed."""

ProcStatus = Literal[
    "processing",
    "succeeded",
    "failed",
    "terminated",
    "unknown",
]
"""YouTube ``processingDetails.processingStatus`` — distinct from
:data:`UploadStatus` because YT can have *uploaded* bytes that are
still transcoding. ``"unknown"`` is the seed's safe-default. Pair with
:data:`UploadStatus` to decide "is the video shareable?"."""

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

SHORTS_MAX_DURATION_SECONDS = 180
"""Upper duration bound for a YouTube Short. YouTube raised the ceiling
from 60s to **180s (3 min)** in October 2024. The Data API exposes NO
`is_short` field — Shorts are ordinary `Video` resources — so duration
is one inference signal (see :func:`classify_short`). A video longer
than this is never a Short; `≤ 60s` is a high-confidence Short; the
`61–180s` band is genuinely ambiguous (duration alone can't decide)."""


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
class VideoFull:
    """Richer YouTube video projection — wraps `videos.list?part=snippet,
    statistics,status,contentDetails`.

    Distinct from :class:`Video` because consumer UI surfaces frequently
    need the wider field set (thumbnail URL, raw ISO-8601 duration, full
    engagement metrics, privacy state, tags, category). Splitting from
    `Video` rather than widening it keeps the cheap-quota
    `list_channel_videos` value-object lean (the wide projection costs
    nothing extra in YT-API units — `part=` selection is free — but
    callers reading the type surface should see at a glance which
    projection a method emits).

    Seed convention (matches :class:`Video`):
    - `duration_seconds` is the parsed ISO-8601 integer-second value.
    - `duration_iso` is the raw ISO-8601 string echoed back (so callers
      that round-trip to an external client get the same shape YT emits).
    - `published_at` is timezone-aware UTC.
    - Numeric fields default to 0 when the API omits them (no Optional
      ints — keeps consumer arithmetic loud-failure-free).
    - `tags` is `()` (empty tuple) when absent, never `None` — frozen
      to match the dataclass frozen contract.
    - `privacy_status` reuses :data:`PrivacyStatus` with `"unknown"` as
      the API-omitted-the-field carve-out (mirrors
      :class:`ProcessingStatus.privacy_status`)."""

    id: str
    title: str
    description: str
    channel_id: str
    published_at: datetime
    duration_seconds: int
    """Parsed from ISO-8601 `contentDetails.duration` (e.g. `PT5M30S`)."""
    duration_iso: str
    """Raw ISO-8601 `contentDetails.duration` string echoed back
    (e.g. `"PT5M30S"`). Empty string when the API omits it."""
    thumbnail_url: str
    """Highest-resolution thumbnail URL the API returned. Picked in
    order: `maxres` → `high` → `medium` → `default`. Empty string when
    no thumbnails are present."""
    privacy_status: PrivacyStatus | Literal["unknown"]
    """`"unknown"` is the API-omitted-the-field carve-out, mirroring
    :class:`ProcessingStatus.privacy_status`."""
    view_count: int
    like_count: int
    comment_count: int
    tags: tuple[str, ...] = ()
    """Frozen-tuple to satisfy the dataclass `frozen=True` constraint
    (lists are unhashable in a frozen context). Empty when absent."""
    category_id: str = ""


@dataclass(frozen=True)
class ChannelInfo:
    """Authenticated-channel metadata — wraps `channels.list?mine=True&
    part=snippet,statistics`.

    Distinct from :class:`Channel` because the OAuth-authenticated
    `mine=True` call returns the engagement counters (subscriber /
    video / view) the operator surface displays, but does NOT include
    `contentDetails.relatedPlaylists.uploads` (the API surfaces those
    on different `part=` selections). Splitting types keeps each
    projection self-describing.

    Numeric fields default to 0 when the API omits them (no Optional —
    keeps consumer arithmetic loud-failure-free)."""

    channel_id: str
    title: str
    subscriber_count: int
    video_count: int
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


@dataclass(frozen=True)
class ProcessingStatus:
    """YouTube post-upload processing state, mirroring
    ``videos.list?part=status,processingDetails`` for one video.

    Distinct from :class:`VideoUpload` because the `videos.insert` call
    returns once YT has *received* the bytes — transcoding then runs
    asynchronously on YT-side and a separate poll is required before
    the video is shareable. Used by upload pipelines that surface
    "your video is ready" only when the operator can actually share
    the URL.

    Terminal "ready" state: ``upload_status == "processed"`` AND
    ``processing_status == "succeeded"``. ``"unknown"`` literals carry
    the API-omitted-the-field case explicitly so consumers branch on
    the value rather than truthy-check (no silent-errors)."""

    video_id: str
    upload_status: UploadStatus
    processing_status: ProcStatus
    privacy_status: PrivacyStatus | Literal["unknown"]
    """``"unknown"`` is the API-omitted-the-field case (post-revoke /
    deleted videos). Keeping it explicit here mirrors
    :data:`UploadStatus` / :data:`ProcStatus`."""
    quota_units_consumed: int = 1
    """1 unit (`videos.list?id=<video_id>` is 1 unit regardless of
    ``part`` selection)."""


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
    "SHORTS_MAX_DURATION_SECONDS",
    "TITLE_MAX_LEN",
    "UPLOAD_QUOTA_UNITS",
    "Channel",
    "ChannelInfo",
    "ListResult",
    "Playlist",
    "PrivacyStatus",
    "ProcStatus",
    "ProcessingStatus",
    "UploadStatus",
    "Video",
    "VideoFull",
    "VideoUpload",
]
