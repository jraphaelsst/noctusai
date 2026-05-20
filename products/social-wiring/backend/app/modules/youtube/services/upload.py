"""Upload pipeline orchestrator.

Owns the full lifecycle of a single video upload:

    queue_browser_upload(file, metadata) ──┐
                                            ├─→ run_upload_job(job_id)
    queue_drive_upload(url, metadata)   ──┘         │
                                                     ├── (gdrive download if needed)
                                                     ├── youtube_service.upload_video
                                                     ├── notification_service.notify_upload  (Phase 4)
                                                     └── status transitions persisted

Status transitions are written to ``social_wiring.upload_jobs`` via the
service-role client so RLS doesn't block intra-org progress updates from
the backend's BackgroundTasks worker.

Notification dispatch is wired in Phase 4: after the upload reaches
``status='published'``, if a non-empty ``notify_recipients[]`` array
exists on the job AND a ``notification_service`` is configured, the
worker fires per-recipient/per-channel sends and transitions to
``status='notified'`` when any send succeeds. Per-recipient failures
become ``notification_log`` rows (the upload itself stays ``published``).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TYPE_CHECKING
from uuid import UUID, uuid4

from app.modules.youtube.schemas.upload import UploadMetadata
from app.services import gdrive_service
from app.modules.youtube.services.youtube import (
    YouTubeNotConnected,
    YouTubeService,
    YouTubeServiceError,
)

if TYPE_CHECKING:
    # Forward reference only — keeps the import graph cycle-free
    # (notification_service does NOT import from upload_service).
    from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_TABLE = "upload_jobs"
_SCHEMA = "social_wiring"

# YT-side processing wait (S4-1). After videos.insert, the bytes are on
# YT but transcoding may still be in flight. We wait for
# upload_status="processed" so the completion message arrives only when
# the operator can actually share the URL.
YT_PROCESSING_POLL_S = 30.0
YT_PROCESSING_TIMEOUT_S = 10 * 60  # 10 minutes — covers all but the
                                    # longest-form videos.


class UploadServiceError(Exception):
    """Raised by queue_* when the inbound payload is malformed before any
    DB row exists. Pipeline-time failures (during run_upload_job) flip the
    job row to status='failed' instead of raising — the row is the source
    of truth, not the call stack."""


@dataclass
class QueuedJob:
    """What queue_* returns to the router after the row is inserted but
    before any heavy lifting runs."""

    job_id: UUID
    status: str = "queued"


@dataclass(frozen=True)
class BatchChild:
    """One child job queued by ``queue_drive_folder_upload``."""

    job_id: UUID
    file_name: str
    parent_subfolder: str | None


@dataclass
class BatchQueued:
    """What ``queue_drive_folder_upload`` returns to the router.

    ``batch_id`` lets the dashboard group siblings; ``children`` is the
    per-video list the router uses to spawn one BackgroundTask each. An
    empty ``children`` list is never returned — if no videos were found
    the service raises :class:`UploadServiceError` BEFORE inserting
    anything (mirrors the single-file path's pre-insert validation)."""

    batch_id: UUID
    children: list[BatchChild] = field(default_factory=list)


class UploadService:
    """Per-request collaborator. Constructed from the user-scoped Supabase
    client (for the queue insert + RLS-checked reads) and the service-role
    client (for status transitions during the background run).

    The two-client split is deliberate: queueing must be RLS-bounded so a
    user can't insert a job for someone else's org, but the background
    worker has no JWT context — it needs service-role to write progress.
    """

    def __init__(
        self,
        *,
        user_supabase,
        admin_supabase,
        upload_dir: Path,
        youtube_service: YouTubeService,
        notification_service: "NotificationService | None" = None,
        redis_client: Any = None,
    ):
        self._user = user_supabase
        self._admin = admin_supabase
        self._upload_dir = upload_dir
        self._youtube = youtube_service
        # Optional: when None, the publishing path stops at status='published'
        # and skips the notification dispatch. Backward-compatible with
        # Phase 2/3 tests that constructed the service without it.
        self._notification_service = notification_service
        # Redis client used by the global upload queue. When None, the
        # queue is bypassed (single-process dev paths + tests that don't
        # care about queueing semantics). Production paths always pass
        # the real client so the queue gates every upload uniformly —
        # browser uploads, dashboard retries, and WhatsApp triggers all
        # share the same FIFO + bounded-parallel budget.
        self._redis_client = redis_client
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    # ─── Queue (RLS-bounded; runs synchronously in the request) ────────
    def queue_browser_upload(
        self,
        *,
        org_id: UUID,
        created_by: UUID | None,
        metadata: UploadMetadata,
        file_name: str,
        file_size_bytes: int | None,
        local_path: Path,
    ) -> QueuedJob:
        """Insert a row for a browser-uploaded file already on local disk.

        The router writes the multipart body to ``upload_dir`` BEFORE
        calling this — so by the time we insert, the file path is real
        and ``run_upload_job`` can stream it to YouTube without touching
        the request body again."""
        if not local_path.exists():
            raise UploadServiceError(
                f"queue_browser_upload called with missing local file: {local_path}"
            )

        return self._insert_job(
            org_id=org_id,
            created_by=created_by,
            metadata=metadata,
            source_type="browser",
            source_url=None,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
        )

    def queue_drive_upload(
        self,
        *,
        org_id: UUID,
        created_by: UUID | None,
        metadata: UploadMetadata,
        drive_url: str,
    ) -> QueuedJob:
        """Insert a row for a Drive-sourced upload. Download happens in
        ``run_upload_job`` (background) — file_size_bytes is unknown
        until then so it stays NULL on the queued row.

        Accepts both single-file URLs and folder URLs. Folder URLs
        trigger the pick_youtube_video() path in _materialise_source()."""
        # Defensive parse — schema-level validator already ran, but a
        # malformed URL slipping through would fail in the background
        # task with worse diagnostics.
        if gdrive_service.is_folder_url(drive_url):
            try:
                gdrive_service.parse_folder_id(drive_url)
            except gdrive_service.InvalidDriveURL as exc:
                raise UploadServiceError(str(exc)) from exc
        else:
            try:
                gdrive_service.parse_file_id(drive_url)
            except gdrive_service.InvalidDriveURL as exc:
                raise UploadServiceError(str(exc)) from exc

        return self._insert_job(
            org_id=org_id,
            created_by=created_by,
            metadata=metadata,
            source_type="gdrive",
            source_url=drive_url,
            file_name=_filename_from_drive_url(drive_url),
            file_size_bytes=None,
        )

    def _insert_job(
        self,
        *,
        org_id: UUID,
        created_by: UUID | None,
        metadata: UploadMetadata,
        source_type: str,
        source_url: str | None,
        file_name: str,
        file_size_bytes: int | None,
        batch_id: UUID | None = None,
        target_format: str | None = None,
    ) -> QueuedJob:
        payload = {
            "org_id": str(org_id),
            "title": metadata.title,
            "description": metadata.description,
            "tags": metadata.tags,
            "privacy_status": metadata.privacy_status,
            "category_id": metadata.category_id,
            "source_type": source_type,
            "source_url": source_url,
            "file_name": file_name,
            "file_size_bytes": file_size_bytes,
            "notify_recipients": [str(r) for r in metadata.notify_recipients],
            "product_code": metadata.product_code or None,
            "thumbnail_url": metadata.thumbnail_url,
            "created_by": str(created_by) if created_by else None,
        }
        # youtube-drive-folder-fanout columns — omitted from payload when
        # None so legacy callers + the single-file paths don't accidentally
        # spam NULLs (the columns default to NULL in the DB anyway).
        if batch_id is not None:
            payload["batch_id"] = str(batch_id)
        if target_format is not None:
            payload["target_format"] = target_format

        response = (
            self._user
            .schema(_SCHEMA)
            .table(_TABLE)
            .insert(payload)
            .execute()
        )
        if not response.data:
            raise UploadServiceError(
                "upload_jobs insert returned no rows — RLS or constraint failure"
            )
        row = response.data[0]
        return QueuedJob(job_id=UUID(row["id"]))

    # ─── Drive-folder fan-out (youtube-drive-folder-fanout) ─────────────
    def queue_drive_folder_upload(
        self,
        *,
        org_id: UUID,
        created_by: UUID | None,
        metadata: UploadMetadata,
        drive_folder_url: str,
    ) -> BatchQueued:
        """Download a Drive folder + queue one row per video found.

        Strategy:
          1. Parse the folder URL upfront (cheap; bad URL → 4xx without
             touching disk).
          2. Call :func:`gdrive_service.iter_drive_folder_videos` which
             downloads everything via gdown and returns one ref per
             accepted video (one level of subfolder recursion; oversized
             + non-video files dropped on the floor).
          3. For each ref, insert an ``upload_jobs`` row sharing the
             same ``batch_id`` then **rename** the on-disk file into the
             canonical ``<job_id>__<file_name>`` shape that the existing
             browser-source ``_materialise_source`` path knows how to
             find. Source type stays ``"browser"`` (the file is already
             on disk — re-fetching from Drive would be wasteful) and
             ``source_url`` records the originating folder for audit.
          4. Worker classifies each video at run time and stamps
             ``target_format``; Shorts-tagged videos get a ``#Shorts``
             description suffix before the YT upload call.

        Raises:
            :class:`UploadServiceError` — the folder URL is unparseable,
                the Drive download failed, the folder contained no
                accepted videos, OR no row could be inserted (RLS / DB
                gap). The exception wraps the underlying message so the
                router can translate to the right HTTP status.

        Sibling failure isolation: once at least one row is inserted,
        per-row failures (e.g. one rename hitting EEXIST) mark THAT
        child failed and continue with the rest — matches the
        "each job independent" contract.
        """
        # Pre-flight URL parse so a typo never costs a Drive download.
        try:
            gdrive_service.parse_folder_id(drive_folder_url)
        except gdrive_service.InvalidDriveURL as exc:
            raise UploadServiceError(str(exc)) from exc

        batch_id = uuid4()
        target_dir = self._upload_dir / "drive-batch" / str(batch_id)

        try:
            refs = gdrive_service.iter_drive_folder_videos(
                folder_url=drive_folder_url,
                target_dir=target_dir,
            )
        except gdrive_service.GoogleDriveError as exc:
            raise UploadServiceError(
                f"Drive folder fanout failed: {exc}"
            ) from exc

        children: list[BatchChild] = []
        first_error: Exception | None = None
        for ref in refs:
            try:
                queued = self._insert_job(
                    org_id=org_id,
                    created_by=created_by,
                    metadata=metadata,
                    source_type="browser",
                    # source_url records the original folder for audit
                    # — it is NOT what `_materialise_source` looks at
                    # (the worker uses the canonical on-disk path).
                    source_url=drive_folder_url,
                    file_name=ref.file_name,
                    file_size_bytes=ref.file_size_bytes,
                    batch_id=batch_id,
                )
            except UploadServiceError as exc:
                # Insert failure: drop this ref's file (the worker would
                # never get to it) and remember the first error so we
                # can re-raise if ALL inserts failed.
                gdrive_service.cleanup(ref.local_path)
                first_error = first_error or exc
                logger.exception(
                    "queue_drive_folder_upload: insert failed for %s in batch %s",
                    ref.file_name, batch_id,
                )
                continue

            # Move from drive-batch/<batch_id>/.../<name> to the canonical
            # browser-upload location so `_materialise_source` (source_type
            # ="browser") finds it deterministically. Use rename_for_job
            # to share the same naming convention as browser uploads.
            try:
                rename_for_job(
                    ref.local_path,
                    queued.job_id,
                    ref.file_name,
                    target_dir=self._upload_dir,
                )
            except OSError as exc:
                # File-system gap (disk full, permission). Mark the row
                # failed so the dashboard reflects it; the sibling jobs
                # keep running.
                logger.exception(
                    "queue_drive_folder_upload: rename failed for job %s (file %s)",
                    queued.job_id, ref.file_name,
                )
                self._mark_failed(
                    queued.job_id,
                    f"failed to stage Drive file on disk: {exc}",
                )
                continue

            children.append(
                BatchChild(
                    job_id=queued.job_id,
                    file_name=ref.file_name,
                    parent_subfolder=ref.parent_subfolder,
                )
            )

        if not children:
            # Every ref hit an insert error — surface the first one so
            # the router returns a meaningful detail.
            if first_error is not None:
                raise UploadServiceError(
                    f"all {len(refs)} Drive folder rows failed to queue: {first_error}"
                ) from first_error
            # Defensive: refs was non-empty (iter_drive_folder_videos
            # raises otherwise) so we shouldn't reach here. Surface a
            # loud signal if we ever do.
            raise UploadServiceError(
                "Drive folder fanout produced no queued jobs (unreachable branch)"
            )

        return BatchQueued(batch_id=batch_id, children=children)

    # ─── Run (background; uses service-role client) ────────────────────
    def run_upload_job(self, *, job_id: UUID) -> None:
        """Background-task entry point. Owns the full pipeline for a job.

        Errors are CAPTURED into the job row, not raised — the request
        already returned 202 by the time this runs, so an uncaught
        exception would only land in the worker log and the user would
        see "uploading..." forever.

        Queue: every entry point flows through this method. When a Redis
        client was injected at construction, the job acquires a slot in
        the global :class:`UploadQueue` before doing any Drive/YT work —
        so browser uploads, dashboard retries, and WhatsApp triggers
        share the same FIFO + bounded-parallel budget without any per-call-
        site plumbing. When the client is None (legacy / test paths),
        queueing is bypassed cleanly.
        """
        job = self._fetch_job(job_id)
        if job is None:
            logger.error("run_upload_job: job_id=%s not found", job_id)
            return

        queue_token = self._acquire_queue_slot(job_id)
        try:
            self._do_upload_pipeline(job_id, job)
        finally:
            self._release_queue_slot(queue_token, job_id)

    def _acquire_queue_slot(self, job_id: UUID) -> bool:
        """Enqueue + block until the job is within the run band.

        Returns True when the queue is enabled (release should fire),
        False when the Redis client is None (no-op).
        """
        if self._redis_client is None:
            return False
        from app.config import settings
        from app.modules.youtube.services.upload_queue import UploadQueue

        queue = UploadQueue(self._redis_client)
        max_concurrent = max(1, getattr(settings, "upload_max_concurrent", 1))
        job_key = str(job_id)
        try:
            queue.enqueue(job_key)
        except Exception:
            logger.exception(
                "upload_queue.enqueue failed for job %s — proceeding without queue", job_id
            )
            return False

        # Blocking sync wait — we're already inside an asyncio.to_thread call
        # (or a BackgroundTasks worker thread), so sleeping here is fine.
        # The outer asyncio loop stays free for other requests.
        import time
        while True:
            try:
                pos = queue.position(job_key)
            except Exception:
                logger.exception(
                    "upload_queue.position failed for job %s — proceeding without wait",
                    job_id,
                )
                return True
            if pos == 0 or pos <= max_concurrent:
                return True
            time.sleep(3.0)

    def _release_queue_slot(self, was_acquired: bool, job_id: UUID) -> None:
        """Release the queue slot. Safe to call when acquisition failed."""
        if not was_acquired or self._redis_client is None:
            return
        try:
            from app.modules.youtube.services.upload_queue import UploadQueue

            UploadQueue(self._redis_client).release(str(job_id))
        except Exception:
            logger.exception("upload_queue.release failed for job %s", job_id)

    def _do_upload_pipeline(self, job_id: UUID, job: dict[str, Any]) -> None:
        """Inner pipeline — runs AFTER the queue slot is acquired.

        Split from ``run_upload_job`` so the queue acquire/release is a
        clean outer wrapper. Behavior unchanged from the pre-queue
        version below this point.
        """
        try:
            local_path = self._materialise_source(job)
        except gdrive_service.GoogleDriveError as exc:
            self._mark_failed(job_id, f"Drive download failed: {exc}")
            return

        # youtube-drive-folder-fanout Phase 4 — classify + stamp
        # target_format AFTER the file is on disk. Skipped on retries
        # where the row already carries a value (idempotent).
        target_format = self._classify_and_stamp_target_format(
            job_id=job_id,
            local_path=local_path,
            existing=job.get("target_format"),
        )

        # Shorts-aware description: when YT auto-detects vertical+≤3min
        # as a Short on its side, the `#Shorts` tag in the description
        # is a documented ranking signal. Idempotent — never duplicates
        # the tag if it's already present.
        description = self._shorts_aware_description(
            description=job.get("description") or "",
            target_format=target_format,
        )

        try:
            self._update_status(job_id, status="uploading", progress_percent=20)
            video_id = self._youtube.upload_video(
                org_id=UUID(job["org_id"]),
                file_path=str(local_path),
                title=job["title"],
                description=description,
                tags=job.get("tags") or [],
                privacy_status=job.get("privacy_status") or "private",
                category_id=job.get("category_id") or "22",
            )
        except YouTubeNotConnected as exc:
            # NO cleanup on failure — keep the file on disk so the
            # dashboard retry button can re-run the upload without
            # re-downloading from Drive. The download cache TTL +
            # cleanup_orphans sweep eventually reclaim orphaned files.
            self._mark_failed(
                job_id,
                f"YouTube not connected for this org: {exc}. "
                "Reconnect via Settings → YouTube before retrying.",
            )
            return
        except YouTubeServiceError as exc:
            self._mark_failed(job_id, f"YouTube upload failed: {exc}")
            return
        except Exception as exc:
            # Catch-all because the background worker has no other error
            # surface — let the user SEE the failure on the job row.
            logger.exception("upload_video raised unexpected error for job_id=%s", job_id)
            self._mark_failed(job_id, f"Unexpected upload failure: {exc}")
            return

        # Thumbnail upload (S4-2) — best-effort. The video stays up even
        # if the thumbnail fails; YT picks a frame from the video as the
        # default. Done BEFORE the processing wait so the thumbnail is
        # ready by the time the operator clicks the URL.
        thumbnail_url = job.get("thumbnail_url")
        if thumbnail_url:
            self._upload_thumbnail_best_effort(
                org_id=UUID(job["org_id"]),
                video_id=video_id,
                thumbnail_url=thumbnail_url,
            )

        # YT-side processing. The insert call returns once YT has
        # received the bytes, but the video isn't immediately playable —
        # YT still has to transcode it. Mark "processing" then poll
        # ``get_processing_status`` until ``upload_status == "processed"``
        # so the completion notification arrives only when the operator
        # can actually share the URL. Bounded by ``YT_PROCESSING_TIMEOUT_S``
        # so a stuck-processing video doesn't block the pipeline forever.
        self._update_status(
            job_id,
            status="processing",
            progress_percent=99,
            youtube_video_id=video_id,
        )
        self._wait_for_yt_processing(
            job_id=job_id, org_id=UUID(job["org_id"]), video_id=video_id
        )

        # Success path — mark published + cleanup the local file. The
        # cleanup runs HERE (not in a finally) so failure paths keep the
        # file for retry. Both gdrive- and browser-sourced jobs cleanup
        # the same way; the router writes browser uploads with a
        # job-id-prefixed name so cleanup is unambiguous either way.
        self._update_status(
            job_id,
            status="published",
            progress_percent=100,
            youtube_video_id=video_id,
        )
        try:
            gdrive_service.cleanup(local_path)
        except Exception:
            logger.exception(
                "post-upload cleanup failed for job_id=%s path=%s",
                job_id,
                local_path,
            )

        # ─── Phase 4: notification dispatch ────────────────────────────
        # Stays at 'published' when:
        #   - notify_recipients[] is empty (opt-out path)
        #   - all dispatch attempts fail (preserves auditability —
        #     'notified' should only fire when at least one recipient
        #     actually heard about the new video)
        # Transitions to 'notified' when ≥1 send succeeded.
        notify_ids = job.get("notify_recipients") or []
        if self._notification_service and notify_ids:
            self._dispatch_notifications(job_id)

    def _dispatch_notifications(self, job_id: UUID) -> None:
        """Run the notification dispatcher, catch all exceptions, flip
        to status='notified' when at least one recipient succeeded.

        Errors here MUST NOT undo the publish — the upload itself is
        already final. The notification_log captures per-recipient
        failures for the dashboard's "delivery health" panel."""
        if self._notification_service is None:
            return
        try:
            # ``notify_upload`` is async; ``run_upload_job`` is sync (BackgroundTasks
            # runs sync functions in a worker thread, where no event loop is
            # already running — so ``asyncio.run`` is safe). If the worker
            # ever moves to async-native, this becomes ``await``.
            outcome = asyncio.run(
                self._notification_service.notify_upload(job_id=job_id)
            )
        except Exception:
            logger.exception(
                "notification dispatch failed for job_id=%s — "
                "upload stays at status='published'",
                job_id,
            )
            return

        if outcome.succeeded > 0:
            self._update_status(job_id, status="notified")

    # ─── Read endpoints (RLS-bounded via user_supabase) ────────────────
    def get_job(self, *, job_id: UUID, org_id: UUID) -> dict[str, Any] | None:
        """Fetch a single job by id. RLS ensures the caller can only see
        jobs in their own org; the explicit ``org_id`` filter is belt-
        and-braces so a misconfigured RLS policy doesn't leak."""
        response = (
            self._user
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("id", str(job_id))
            .eq("org_id", str(org_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    def list_history(
        self,
        *,
        org_id: UUID,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Most-recent-first job list for the Upload page's history table."""
        response = (
            self._user
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(response.data or [])

    def get_batch_status(
        self, *, org_id: UUID, batch_id: UUID
    ) -> dict[str, Any] | None:
        """Aggregate state of one Drive-folder fan-out batch.

        Returns ``None`` when no rows match (404 → caller's
        responsibility). RLS-bounded via the user client; an explicit
        ``org_id`` filter belt-and-braces against policy misconfig.

        Returns:
            ``{ "batch_id": UUID, "total": N, "counts": {<status>: <n>},
                "jobs": [<row>] }`` — counts always include every
                status key with a default of 0 so the UI can render a
                uniform table.
        """
        response = (
            self._user
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("batch_id", str(batch_id))
            .order("created_at", desc=False)
            .execute()
        )
        rows = list(response.data or [])
        if not rows:
            return None

        counts: dict[str, int] = {
            "queued": 0,
            "downloading": 0,
            "uploading": 0,
            "processing": 0,
            "published": 0,
            "notified": 0,
            "failed": 0,
        }
        for row in rows:
            st = row.get("status")
            if st in counts:
                counts[st] += 1

        return {
            "batch_id": batch_id,
            "total": len(rows),
            "counts": counts,
            "jobs": rows,
        }

    # ─── Internals (admin-client paths) ────────────────────────────────
    def _fetch_job(self, job_id: UUID) -> dict[str, Any] | None:
        """Service-role fetch — no org filter because the background task
        already trusts the job_id; row-existence is the only check."""
        response = (
            self._admin
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("id", str(job_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    def _materialise_source(self, job: dict[str, Any]) -> Path:
        """Return a local file path that ``upload_video`` can read.

        Browser uploads already live at ``upload_dir/<job_id>__<file_name>``;
        Drive uploads need a download + status='downloading' transition
        for the UI's progress bar.

        Phase 5: folder URLs route through ``pick_youtube_video`` which
        downloads all files, classifies them (YT vs REELS), picks the
        YouTube-format one, and cleans up the rest."""
        if job["source_type"] == "browser":
            local_path = self._upload_dir / f"{job['id']}__{job['file_name']}"
            if not local_path.exists():
                raise gdrive_service.GoogleDriveError(
                    f"browser-uploaded file missing: {local_path}. "
                    "It may have been cleaned up before the worker ran."
                )
            return local_path

        # gdrive — single file or folder
        source_url = job["source_url"]
        self._update_status(UUID(job["id"]), status="downloading", progress_percent=5)

        if gdrive_service.is_folder_url(source_url):
            # Folder path: download all files, classify, pick YT
            folder_result = gdrive_service.pick_youtube_video(
                folder_url=source_url,
                target_dir=self._upload_dir / "drive" / str(job["id"]),
            )
            self._update_row(
                UUID(job["id"]),
                file_name=folder_result.file_name,
                file_size_bytes=folder_result.file_size_bytes,
            )
            return folder_result.local_path
        else:
            # Single file path
            result = gdrive_service.download_from_drive(
                drive_url=source_url,
                target_dir=self._upload_dir / "drive",
            )
            self._update_row(
                UUID(job["id"]),
                file_name=result.file_name,
                file_size_bytes=result.file_size_bytes,
            )
            return result.local_path

    def _update_status(
        self,
        job_id: UUID,
        *,
        status: str,
        progress_percent: int | None = None,
        youtube_video_id: str | None = None,
    ) -> None:
        update: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if progress_percent is not None:
            update["progress_percent"] = progress_percent
        if youtube_video_id is not None:
            update["youtube_video_id"] = youtube_video_id
        self._update_row(job_id, **update)

    def _update_row(self, job_id: UUID, **fields: Any) -> None:
        try:
            (
                self._admin
                .schema(_SCHEMA)
                .table(_TABLE)
                .update(fields)
                .eq("id", str(job_id))
                .execute()
            )
        except Exception:
            # The worker has no caller to surface this to. Log loudly and
            # keep going — a missed status update is degraded UX, not a
            # data-loss event.
            logger.exception("upload_jobs update failed for job_id=%s", job_id)

    def _upload_thumbnail_best_effort(
        self,
        *,
        org_id: UUID,
        video_id: str,
        thumbnail_url: str,
    ) -> None:
        """Download the thumbnail URL + push to YT. Logs + swallows
        every failure mode so a thumbnail issue never fails the video.

        Size cap is enforced loosely (YT-side limit is 2MB). Anything
        beyond 5MB is rejected upfront to avoid a slow + futile upload.
        """
        try:
            import httpx

            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                response = client.get(thumbnail_url)
                response.raise_for_status()
                content = response.content
                content_type = response.headers.get(
                    "content-type", "image/jpeg"
                ).split(";")[0].strip()
        except Exception:
            logger.warning(
                "thumbnail download failed for %s — leaving YT default. video_id=%s",
                thumbnail_url, video_id,
            )
            return

        if len(content) > 5 * 1024 * 1024:
            logger.warning(
                "thumbnail %s is %.1fMB — exceeds 5MB sanity cap; skipping.",
                thumbnail_url, len(content) / (1024 * 1024),
            )
            return

        try:
            self._youtube.set_thumbnail(
                org_id=org_id,
                video_id=video_id,
                image_bytes=content,
                mime_type=content_type if "image/" in content_type else "image/jpeg",
            )
            logger.info(
                "thumbnail uploaded for video_id=%s (%d bytes)", video_id, len(content)
            )
        except YouTubeServiceError as exc:
            logger.warning(
                "thumbnail set failed for video_id=%s: %s. "
                "Video stays up with default thumbnail.",
                video_id, exc,
            )

    def _wait_for_yt_processing(
        self,
        *,
        job_id: UUID,
        org_id: UUID,
        video_id: str,
    ) -> None:
        """Poll YT's processingDetails until the video is playable.

        Polls every ``YT_PROCESSING_POLL_S`` seconds, up to
        ``YT_PROCESSING_TIMEOUT_S`` total. Each poll costs 1 quota unit
        — the timeout cap keeps it bounded (max ~20 calls for a 10-min
        timeout).

        Terminal "ready" state: ``upload_status == "processed"`` AND
        ``processing_status == "succeeded"``. Either ``failed`` /
        ``rejected`` / ``terminated`` makes us mark the job failed
        instead of published.

        On timeout: we don't fail the job — the video is uploaded, it
        just may still be transcoding. The completion message goes out
        with a small note. Better than blocking the pipeline forever.
        """
        import time as _time

        deadline = _time.time() + YT_PROCESSING_TIMEOUT_S
        last_log = 0.0
        while _time.time() < deadline:
            try:
                state = self._youtube.get_processing_status(
                    org_id=org_id, video_id=video_id
                )
            except YouTubeServiceError as exc:
                logger.warning(
                    "yt-processing-poll: get_processing_status failed for %s: %s. "
                    "Treating as ready and continuing.",
                    video_id, exc,
                )
                return

            up = state.get("upload_status")
            proc = state.get("processing_status")

            if up == "processed" and proc == "succeeded":
                logger.info(
                    "yt-processing: video_id=%s is ready (upload=%s, proc=%s)",
                    video_id, up, proc,
                )
                return

            if up in {"failed", "rejected", "deleted"} or proc == "failed" or proc == "terminated":
                msg = f"YouTube processing failed: upload_status={up} processing_status={proc}"
                logger.error("yt-processing: %s (video_id=%s)", msg, video_id)
                self._mark_failed(job_id, msg)
                raise YouTubeServiceError(msg)

            # Periodic visibility log (every ~60s) so the operator can
            # see we're still polling, without spamming.
            now = _time.time()
            if now - last_log > 60:
                logger.info(
                    "yt-processing: still waiting (video_id=%s, upload=%s, proc=%s)",
                    video_id, up, proc,
                )
                last_log = now

            _time.sleep(YT_PROCESSING_POLL_S)

        logger.warning(
            "yt-processing: timeout after %ds (video_id=%s) — proceeding to publish.",
            YT_PROCESSING_TIMEOUT_S, video_id,
        )

    # ─── youtube-drive-folder-fanout Phase 4 helpers ───────────────────
    @staticmethod
    def _shorts_aware_description(*, description: str, target_format: str | None) -> str:
        """Append ``#Shorts`` to vertical-video descriptions, idempotently.

        YouTube auto-promotes vertical + ≤3-min uploads as Shorts on
        their side; the ``#Shorts`` description tag is the documented
        ranking signal that helps the algorithm pick them up faster.
        For horizontal / unknown / pre-existing-tag descriptions the
        function is a pass-through."""
        if target_format != "shorts":
            return description
        if "#Shorts" in description or "#shorts" in description:
            return description
        if description:
            return f"{description}\n\n#Shorts"
        return "#Shorts"

    def _classify_and_stamp_target_format(
        self,
        *,
        job_id: UUID,
        local_path: Path,
        existing: str | None,
    ) -> str:
        """Classify the on-disk video + stamp ``target_format`` on the row.

        Idempotent: if the row already carries a non-NULL value (retry
        path, or batch-fanout with a pre-stamped row), returns it
        without re-classifying. Maps ``gdrive_service.classify_video_format``'s
        ``"reels"`` → ``"shorts"`` (the DB CHECK constraint values are
        ``youtube`` / ``shorts`` / ``unknown``).

        Best-effort: ANY classification failure stamps ``"unknown"``
        rather than failing the upload — a misclassified Shorts goes
        through as long-form (still uploads, just doesn't get the
        Shorts ranking nudge) which is far less bad than aborting.
        """
        if existing:
            return existing

        try:
            raw = gdrive_service.classify_video_format(local_path)
        except Exception:
            logger.exception(
                "classify_video_format raised for job %s (path=%s) — stamping 'unknown'",
                job_id, local_path,
            )
            raw = "unknown"

        target = "shorts" if raw == "reels" else raw
        if target not in ("youtube", "shorts", "unknown"):
            # Defensive — keeps the DB CHECK happy if classify ever
            # returns a new value we didn't expect.
            target = "unknown"

        self._update_row(job_id, target_format=target)
        return target

    def _mark_failed(self, job_id: UUID, error_message: str) -> None:
        self._update_row(
            job_id,
            status="failed",
            error_message=error_message,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ─── Retry surface (dashboard "🔄 Tentar de novo" button) ───────────
    def retry_failed_job(
        self, *, job_id: UUID, org_id: UUID
    ) -> dict[str, Any]:
        """Re-queue a previously-failed job so ``run_upload_job`` can run again.

        Validates:
          - Job exists (else 404 at router layer).
          - Caller's org matches the job's org (RLS + explicit check).
          - Job is currently in ``failed`` state (else 409).

        Side-effects:
          - status → ``queued`` (the existing transition that
            ``run_upload_job`` reads from).
          - ``error_message`` → cleared.
          - ``progress_percent`` → 0 (so the dashboard's progress bar
            resets cleanly).

        Returns the updated row. The router kicks ``run_upload_job`` via
        ``BackgroundTasks`` so this method itself stays synchronous +
        side-effect-only.

        Note: this does NOT re-validate that the Drive folder (for
        gdrive-sourced jobs) is still accessible. If the source vanished
        between failure + retry, ``run_upload_job`` will re-fail with a
        Drive error and the loop terminates naturally — no infinite
        retry, no data loss.
        """
        row = self.get_job(job_id=job_id, org_id=org_id)
        if row is None:
            raise UploadServiceError(f"job {job_id} not found")
        if row.get("status") != "failed":
            raise UploadServiceError(
                f"job {job_id} is in status={row.get('status')!r}; "
                "retry only works on failed jobs."
            )

        # Drop any stale queue entry so the retry joins fresh at the BACK
        # of the queue (fairness) — not the position the prior attempt
        # held when it failed. Safe-when-absent; idempotent.
        if self._redis_client is not None:
            try:
                from app.modules.youtube.services.upload_queue import UploadQueue

                UploadQueue(self._redis_client).release(str(job_id))
            except Exception:
                logger.exception(
                    "retry_failed_job: stale queue release failed for %s",
                    job_id,
                )

        self._update_row(
            job_id,
            status="queued",
            error_message=None,
            progress_percent=0,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        refreshed = self.get_job(job_id=job_id, org_id=org_id)
        return refreshed or row


# ─── Browser-upload helpers (used by the router) ───────────────────────
@contextmanager
def stage_browser_upload(
    *,
    upload_dir: Path,
    file_name: str,
    upload_stream,
) -> Iterator[Path]:
    """Stream the multipart body to a sentinel path the router can pass
    into queue_browser_upload.

    Sentinel naming: ``<random>__<filename>`` until the job_id exists,
    then renamed to ``<job_id>__<filename>`` so the worker can locate it.
    Yielding context-managed for use in routers; the file is NOT auto-
    deleted (the worker owns that)."""
    import uuid as _uuid

    upload_dir.mkdir(parents=True, exist_ok=True)
    sentinel = upload_dir / f"staging-{_uuid.uuid4().hex}__{file_name}"
    try:
        with open(sentinel, "wb") as fh:
            shutil.copyfileobj(upload_stream, fh)
        yield sentinel
    except Exception:
        # If the router fails to queue the job, we leave nothing behind.
        gdrive_service.cleanup(sentinel)
        raise


def rename_for_job(
    staging_path: Path,
    job_id: UUID,
    file_name: str,
    *,
    target_dir: Path | None = None,
) -> Path:
    """Move a staged upload to the canonical job-id-prefixed path.

    ``target_dir`` defaults to ``staging_path.parent`` (rename in place —
    the right default for browser uploads which are staged in
    ``upload_dir`` already). The multi-candidate Drive flow stages files
    in a subdirectory (``upload_dir/<folder_name>``) and MUST pass
    ``target_dir=upload_dir`` explicitly — ``_materialise_source`` looks
    for browser-source files at ``upload_dir / <job_id>__<file_name>``,
    not at the staging subdir, so an in-place rename leaves the worker
    unable to find the file.
    """
    base = target_dir or staging_path.parent
    base.mkdir(parents=True, exist_ok=True)
    final = base / f"{job_id}__{file_name}"
    staging_path.rename(final)
    return final


def _filename_from_drive_url(url: str) -> str:
    """Provisional filename for the queued row before download starts.

    Real filename gets backfilled by ``_materialise_source`` once the
    Content-Disposition header is parsed; this placeholder is only ever
    visible if the job stays queued (e.g. background worker crashed)."""
    return f"drive-pending.mp4"
