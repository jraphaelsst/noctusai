"""Pydantic schemas for the Videos surface.

Outbound shapes only — Phase 3 has no inbound write endpoints other than
the sync trigger, which takes no body. The cache row's column set is
larger than what the UI consumes; ``VideoOut`` projects the subset the
Videos page + Dashboard actually render so the API doesn't ship more
data than necessary.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

PrivacyStatus = Literal["public", "unlisted", "private"]
VideoKind = Literal["video", "short"]


class VideoOut(BaseModel):
    """Outbound shape for the Videos page list + detail.

    When served from ``youtube_videos`` the ``kind`` is ``"video"`` and
    ``is_short`` / ``detected_via`` are None. When served from
    ``youtube_shorts`` those fields are populated."""

    id: UUID
    youtube_video_id: str
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    duration: str | None = None             # ISO-8601 (PT1M30S)
    privacy_status: PrivacyStatus | None = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    favorite_count: int = 0
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = None
    uploaded_via_app: bool = False
    synced_at: datetime
    # Shorts-only fields (None for regular videos):
    kind: VideoKind = "video"
    is_short: Optional[bool] = None
    detected_via: Optional[str] = None

    @property
    def youtube_url(self) -> str:
        """Convenience for the UI's "open on YouTube" link.

        Computed from youtube_video_id — the URL format is stable and the
        ID IS the source of truth."""
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"


class VideoListResponse(BaseModel):
    """Paginated list response. Cursor-based pagination so the UI can
    keep "load more" semantics without total-count round trips (which
    YouTube's API doesn't expose cheaply)."""

    items: list[VideoOut]
    next_cursor: str | None = None         # opaque; pass back as ?cursor=...
    total_known: int                        # rows currently in the cache


class VideoSyncResult(BaseModel):
    """Response shape for POST /api/videos/sync.

    Reports what the sync did so the UI can surface progress without a
    second status round-trip. ``inserted`` + ``updated`` may overlap when
    the cache had stale rows that the sync refreshed."""

    inserted: int = 0
    updated: int = 0
    fetched: int = 0
    pages: int = 0
    quota_units_estimated: int = 0
    last_synced_at: datetime


class VideoUpdateIn(BaseModel):
    """Request body for PATCH /api/videos/{youtube_video_id}.

    All fields are optional — only the provided fields are written through
    to YouTube and mirrored to the catalog. An empty body is a no-op
    (returns the current VideoOut unchanged).

    Validation mirrors the YouTube Data API constraints:
    - ``title``: 1–100 characters (YT hard limit; enforced here so the
      error is surfaced before a quota-unit is spent).
    - ``description``: ≤5000 characters (YT limit).
    - ``privacy_status``: one of the three canonical values."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="snippet.title — 1-100 chars (YouTube hard limit).",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="snippet.description — ≤5000 chars (YouTube hard limit).",
    )
    privacy_status: PrivacyStatus | None = Field(
        default=None,
        description="status.privacyStatus — public | unlisted | private.",
    )
