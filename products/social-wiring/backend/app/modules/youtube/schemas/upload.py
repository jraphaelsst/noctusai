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
    # youtube-drive-folder-fanout (NULL on legacy rows + on jobs queued
    # but not yet classified by the worker).
    target_format: Literal["youtube", "shorts", "unknown"] | None = None
    batch_id: UUID | None = None
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


# ─── Drive-folder fan-out (youtube-drive-folder-fanout project) ─────────

class GdriveFolderUploadRequest(BaseModel):
    """JSON payload for POST /api/videos/upload/drive-folder.

    Mirrors :class:`GdriveUploadRequest` but the URL points at a Drive
    *folder*, not a single file. Every video inside the folder (recursing
    one level for subfolders) becomes its own ``upload_jobs`` row sharing
    one ``batch_id`` so the dashboard can group them.

    Two input shapes (exactly one must be set):

    1. ``metadata`` — fully specified `UploadMetadata` (manual mode;
       matches the existing single-file Drive endpoint contract).
    2. ``product_code`` — Vista CRM lookup mode. Server fetches the
       property by code, then `build_youtube_metadata(prop, code)`
       produces the title/description/tags. Optional ``privacy_status``
       overrides the default ``"private"`` for this path.

    The worker stamps ``target_format`` per-video after download+classify
    regardless of which mode produced the metadata.
    """

    drive_folder_url: HttpUrl
    metadata: UploadMetadata | None = None
    product_code: str | None = Field(default=None, max_length=20)
    privacy_status: PrivacyStatus = "private"

    @model_validator(mode="after")
    def _validate_drive_host(self) -> "GdriveFolderUploadRequest":
        host = self.drive_folder_url.host or ""
        if not host.endswith("google.com") and not host.endswith("googleusercontent.com"):
            raise ValueError(
                f"drive_folder_url must point to a Google host (got {host!r}). "
                "Supported: drive.google.com."
            )
        return self

    @model_validator(mode="after")
    def _exactly_one_metadata_source(self) -> "GdriveFolderUploadRequest":
        has_metadata = self.metadata is not None
        has_code = bool((self.product_code or "").strip())
        if has_metadata and has_code:
            raise ValueError(
                "metadata and product_code are mutually exclusive — pass one or "
                "the other (metadata = manual mode; product_code = Vista lookup mode)."
            )
        if not has_metadata and not has_code:
            raise ValueError(
                "must provide either `metadata` (manual mode) or `product_code` "
                "(Vista lookup mode)."
            )
        return self


class BatchChildOut(BaseModel):
    """One job inside a batch — minimal shape returned by the fan-out
    endpoint so the UI can immediately render a per-video progress row
    without re-fetching full metadata it just submitted."""

    job_id: UUID
    file_name: str
    # None for files at the root of the Drive folder; otherwise the
    # immediate subfolder name (useful for human-readable display like
    # "Episode 3/clip.mp4").
    parent_subfolder: str | None = None


class BatchUploadCreated(BaseModel):
    """Response shape for the drive-folder fan-out endpoint.

    Returns ``batch_id`` (so the UI can poll the batch-status endpoint
    for aggregate progress) plus one entry per queued child. The UI
    typically also polls each child's individual `/upload/{job_id}/status`
    for per-row progress."""

    batch_id: UUID
    jobs: list[BatchChildOut]


class BatchStatusCounts(BaseModel):
    """Per-status counts inside a batch — one bucket per
    `UploadJobStatus` value. Always present even when zero so the UI
    can render a uniform table."""

    queued: int = 0
    downloading: int = 0
    uploading: int = 0
    processing: int = 0
    published: int = 0
    notified: int = 0
    failed: int = 0


class BatchStatusOut(BaseModel):
    """Aggregate state of a Drive-folder fan-out batch.

    Returned by `GET /api/videos/upload/batch/{batch_id}`. The UI
    polls this for the high-level "3/5 published, 1 uploading, 1
    failed" header + the per-row detail in `jobs`."""

    batch_id: UUID
    total: int
    counts: BatchStatusCounts
    jobs: list[UploadJobOut]
