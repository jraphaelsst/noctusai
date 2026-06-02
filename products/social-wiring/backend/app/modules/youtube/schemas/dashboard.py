"""Pydantic schemas for the Dashboard surface.

All outbound — Phase 4 dashboard endpoints are read-only aggregates.
The cache-row column set is the source of truth; these schemas project
the subset the dashboard panels render.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KpiStats(BaseModel):
    """Top-row KPI aggregates — one card per field on the dashboard."""

    total_videos: int = 0
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    subscriber_count: int = 0
    last_synced_at: datetime | None = None
    channel_id: str | None = None
    channel_title: str | None = None


class TopVideoItem(BaseModel):
    """One row in the dashboard's top-5-by-views panel.

    Subset of `VideoOut` — the full video shape isn't needed for the
    panel (no description, no tags), so the payload stays small.
    """

    youtube_video_id: str
    title: str | None = None
    thumbnail_url: str | None = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    published_at: datetime | None = None
    duration: str | None = None
    uploaded_via_app: bool = False


NotificationDeliveryStatus = Literal["none", "all_sent", "partial", "all_failed"]


class QueueEntry(BaseModel):
    """One slot in the global upload queue."""

    position: int
    job_id: str
    enqueued_at: float
    title: str | None = None
    product_code: str | None = None
    status: str | None = None


class QueueState(BaseModel):
    """Snapshot of the global upload queue for the dashboard panel."""

    max_concurrent: int
    entries: list[QueueEntry] = Field(default_factory=list)
    total: int = 0


class RecentUploadItem(BaseModel):
    """One row in the dashboard's "recent uploads via app" panel.

    Joins upload_jobs (the job lifecycle) with notification_log
    (the dispatch outcome) so the dashboard can surface delivery
    health alongside the upload itself."""

    job_id: str
    youtube_video_id: str | None = None
    title: str
    status: str
    privacy_status: str | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
    # Notification delivery summary — derived from notification_log:
    #   none        — no notify_recipients[] (opt-out)
    #   all_sent    — every dispatch attempt succeeded
    #   partial     — some sent, some failed
    #   all_failed  — every attempt failed (job stayed at 'published')
    notification_status: NotificationDeliveryStatus = "none"
    notification_attempts: int = 0
    notification_succeeded: int = 0
    notification_failed: int = 0
