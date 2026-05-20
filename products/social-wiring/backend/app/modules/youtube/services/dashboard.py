"""Read-only aggregates for the Dashboard panels.

Source of truth: the local ``video_cache`` (synced explicitly via the
videos pipeline). Reads are RLS-bounded by the user-scoped supabase
client — the dashboard NEVER touches YouTube's API directly. Every
panel is a thin Postgres aggregate over cached rows; sub-millisecond
on a 500-video channel.

The "recent uploads with delivery status" panel joins ``upload_jobs``
+ ``notification_log`` (Python-side; PostgREST joins are awkward and
the row counts are small — last 10 jobs at most).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.services.credential_vault import CredentialStore

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"


class DashboardService:
    """Per-request collaborator. Constructed from the user-scoped
    supabase client. Admin client only needed for the credentials lookup
    (channel_id / channel_title for the "Connected channel" card),
    which lives behind the encrypted-tokens table → service-role required."""

    def __init__(
        self,
        *,
        user_supabase,
        admin_supabase,
        credential_store: CredentialStore,
    ):
        self._user = user_supabase
        self._admin = admin_supabase
        self._store = credential_store

    # ─── KPI aggregates ────────────────────────────────────────────────
    def kpi_stats(self, *, org_id: UUID) -> dict[str, Any]:
        """Sum view/like/comment counts across the cached video set +
        return the channel's connected-state metadata. Single round-trip
        (the SUM aggregate) + a credential lookup."""
        response = (
            self._user
            .schema(_SCHEMA)
            .table("video_cache")
            .select("view_count, like_count, comment_count, synced_at")
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(response.data or [])

        total_videos = len(rows)
        total_views = sum(int(r.get("view_count") or 0) for r in rows)
        total_likes = sum(int(r.get("like_count") or 0) for r in rows)
        total_comments = sum(int(r.get("comment_count") or 0) for r in rows)
        # Most-recent synced_at across the cache → "last sync" indicator.
        last_synced = None
        for r in rows:
            ts = r.get("synced_at")
            if ts and (last_synced is None or ts > last_synced):
                last_synced = ts

        # Channel metadata from the connected-credentials row, if any.
        channel_id: str | None = None
        channel_title: str | None = None
        try:
            cred = self._store.get(str(org_id), "youtube")
            if cred is not None:
                channel_id = cred.metadata.get("channel_id")
                channel_title = cred.metadata.get("channel_title")
        except Exception:                                     # pragma: no cover
            # Decrypt failures are surfaced loudly elsewhere; the
            # dashboard treats them as "not connected" so the rest
            # of the panel still renders.
            logger.exception("dashboard credential lookup failed for org_id=%s", org_id)

        return {
            "total_videos": total_videos,
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "last_synced_at": last_synced,
            "channel_id": channel_id,
            "channel_title": channel_title,
        }

    # ─── Top-N by views ────────────────────────────────────────────────
    def top_videos(self, *, org_id: UUID, limit: int = 5) -> list[dict[str, Any]]:
        """Top-N cached videos ordered by view count, descending. Cheap
        because PostgREST applies the ORDER BY server-side."""
        response = (
            self._user
            .schema(_SCHEMA)
            .table("video_cache")
            .select(
                "youtube_video_id, title, thumbnail_url, "
                "view_count, like_count, comment_count, "
                "published_at, duration, uploaded_via_app"
            )
            .eq("org_id", str(org_id))
            .order("view_count", desc=True)
            .limit(limit)
            .execute()
        )
        return list(response.data or [])

    # ─── Recent uploads + delivery status ──────────────────────────────
    def recent_uploads(self, *, org_id: UUID, limit: int = 10) -> list[dict[str, Any]]:
        """Last N upload_jobs + per-job notification dispatch summary.

        Two queries: the jobs themselves, then a single batched
        notification_log lookup keyed on the jobs' IDs. Joining
        Python-side keeps the query simple and avoids PostgREST's
        embed-syntax fragility for cross-table aggregation."""
        jobs_resp = (
            self._user
            .schema(_SCHEMA)
            .table("upload_jobs")
            .select(
                "id, youtube_video_id, title, status, privacy_status, "
                "notify_recipients, error_message, created_at, updated_at"
            )
            .eq("org_id", str(org_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        jobs = list(jobs_resp.data or [])
        if not jobs:
            return []

        job_ids = [job["id"] for job in jobs]
        log_resp = (
            self._user
            .schema(_SCHEMA)
            .table("notification_log")
            .select("upload_job_id, status")
            .eq("org_id", str(org_id))
            .in_("upload_job_id", job_ids)
            .execute()
        )
        log_rows = list(log_resp.data or [])

        # Bucket the log rows by upload_job_id → counts of sent/failed.
        log_by_job: dict[str, dict[str, int]] = {}
        for log in log_rows:
            job_id = log["upload_job_id"]
            bucket = log_by_job.setdefault(job_id, {"sent": 0, "failed": 0, "pending": 0})
            status = log.get("status") or "pending"
            if status in bucket:
                bucket[status] += 1

        out: list[dict[str, Any]] = []
        for job in jobs:
            counts = log_by_job.get(job["id"], {"sent": 0, "failed": 0, "pending": 0})
            attempts = counts["sent"] + counts["failed"]
            recipients = job.get("notify_recipients") or []
            notif_status = self._classify_delivery(
                attempts=attempts,
                succeeded=counts["sent"],
                failed=counts["failed"],
                opted_in=bool(recipients),
            )
            out.append({
                "job_id": job["id"],
                "youtube_video_id": job.get("youtube_video_id"),
                "title": job["title"],
                "status": job["status"],
                "privacy_status": job.get("privacy_status"),
                "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "error_message": job.get("error_message"),
                "notification_status": notif_status,
                "notification_attempts": attempts,
                "notification_succeeded": counts["sent"],
                "notification_failed": counts["failed"],
            })
        return out

    @staticmethod
    def _classify_delivery(
        *, attempts: int, succeeded: int, failed: int, opted_in: bool
    ) -> str:
        """Rolls per-channel counts into the 4-state badge the UI shows.

        ``opted_in`` is True when the job had a non-empty
        ``notify_recipients[]`` — distinguishes 'opted out' from
        'opted in but nothing happened yet' (the latter is rare;
        usually the dispatcher fires synchronously at publish time)."""
        if not opted_in:
            return "none"
        if attempts == 0:
            return "none"          # opted in but no log rows yet (transient)
        if failed == 0:
            return "all_sent"
        if succeeded == 0:
            return "all_failed"
        return "partial"
