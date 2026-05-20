"""Pydantic schemas for the upload pipeline.

Boundary types — never echo the file path / Drive cookies back to the
client. The ``UploadJobOut`` shape is read-only; mutations happen via the
upload-router endpoints, never via direct PUT on a job row.

The schemas live here (rather than reusing ``video.py`` from Phase 3)
because the upload metadata is a strict subset of what YouTube returns
+ a few upload-only fields (notify_recipients, source_url) that wouldn't
make sense on a fetched video.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator


# Status terminal/transitional aliases used by the UI for state coloring.
UploadJobStatus = Literal[
    "queued",
    "downloading",
    "uploading",
    "processing",
    "published",
    "notified",
    "failed",
]

PrivacyStatus = Literal["public", "unlisted", "private"]


class UploadMetadata(BaseModel):
    """The metadata that travels alongside every upload, regardless of
    whether the bytes come from the browser or a Drive link."""

    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=500)
    privacy_status: PrivacyStatus = "private"
    category_id: str = Field(default="22", min_length=1, max_length=4)
    notify_recipients: list[UUID] = Field(default_factory=list)
    product_code: str = Field(default="", max_length=20)
    # Optional thumbnail source. When populated (e.g. by the intake's
    # CRM lookup), ``run_upload_job`` downloads the URL + uploads it via
    # ``youtube_service.set_thumbnail`` after the video is published.
    # Best-effort: thumbnail failure does NOT fail the video upload.
    thumbnail_url: str | None = Field(default=None, max_length=2048)


class GdriveUploadRequest(BaseModel):
    """JSON payload for POST /api/videos/upload-from-drive.

    The browser-upload variant takes its metadata as multipart form
    fields (so the file body and metadata travel together); the Drive
    variant is JSON-only because there's no file body."""

    drive_url: HttpUrl
    metadata: UploadMetadata

    @model_validator(mode="after")
    def _validate_drive_host(self) -> "GdriveUploadRequest":
        host = self.drive_url.host or ""
        if not host.endswith("google.com") and not host.endswith("googleusercontent.com"):
            # Reject early so a typo'd URL doesn't cost a download attempt.
            raise ValueError(
                f"drive_url must point to a Google host (got {host!r}). "
                "Supported: drive.google.com, docs.google.com."
            )
        return self


class UploadJobOut(BaseModel):
    """Outbound shape for status polling + history list."""

    id: UUID
    status: UploadJobStatus
    progress_percent: int = Field(ge=0, le=100)
    title: str
    file_name: str
    file_size_bytes: int | None = None
    source_type: Literal["browser", "gdrive"]
    source_url: str | None = None
    youtube_video_id: str | None = None
    error_message: str | None = None
    privacy_status: PrivacyStatus
    notify_recipient_count: int = 0
    product_code: str | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def youtube_url(self) -> str | None:
        """Convenience for the UI's "open on YouTube" link.

        Computed from youtube_video_id rather than persisted because the
        URL format is stable and the video_id IS the source of truth."""
        if not self.youtube_video_id:
            return None
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"


class UploadJobCreated(BaseModel):
    """Response shape for the POST endpoints — minimal so the UI can
    immediately switch to the polling state without having to render full
    metadata it just submitted.

    Returns the job_id; callers fetch full state via /upload/{id}/status.
    """

    job_id: UUID
    status: UploadJobStatus = "queued"
