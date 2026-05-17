"""Dashboard HTTP surface — read-only aggregates over the local cache.

Endpoints:
    GET    /api/dashboard/stats              KPI totals + channel info
    GET    /api/dashboard/top-videos         Top N by view_count
    GET    /api/dashboard/recent-uploads     Last N upload_jobs + delivery summary

All read-only; all RLS-bounded by the user-scoped supabase client. No
YouTube API calls — the dashboard exists precisely to render channel
state without paying quota on every page load.

Auth pattern: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_user_client,
)
from app.schemas.dashboard import (
    KpiStats,
    QueueEntry,
    QueueState,
    RecentUploadItem,
    TopVideoItem,
)
from app.services.credential_store import (
    CredentialStore,
    EncryptionNotConfigured,
)
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _build_dashboard_service(token: str) -> DashboardService:
    """503-on-config-gap shape — same convention as upload + videos
    routers. Operator-actionable error rather than a 500 trace."""
    user_supabase = get_user_client(token)
    admin_supabase = get_admin_client()

    try:
        store = CredentialStore(admin_supabase, settings.encryption_key)
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return DashboardService(
        user_supabase=user_supabase,
        admin_supabase=admin_supabase,
        credential_store=store,
    )


@router.get("/stats", response_model=KpiStats)
def get_stats(auth: tuple = Depends(get_current_user_org)) -> KpiStats:
    """Top-row KPI tiles. Single RLS-bounded SUM aggregate plus the
    connected-channel metadata."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_dashboard_service(token)
    return KpiStats(**service.kpi_stats(org_id=org_id))


@router.get("/top-videos", response_model=list[TopVideoItem])
def get_top_videos(
    limit: int = Query(default=5, ge=1, le=20),
    auth: tuple = Depends(get_current_user_org),
) -> list[TopVideoItem]:
    """Top videos ordered by view count, descending. Default 5
    matches the dashboard panel's row count."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_dashboard_service(token)
    rows = service.top_videos(org_id=org_id, limit=limit)
    return [TopVideoItem(**_coerce_row(row)) for row in rows]


@router.get("/recent-uploads", response_model=list[RecentUploadItem])
def get_recent_uploads(
    limit: int = Query(default=10, ge=1, le=50),
    auth: tuple = Depends(get_current_user_org),
) -> list[RecentUploadItem]:
    """Last N upload jobs + per-job notification dispatch summary."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_dashboard_service(token)
    rows = service.recent_uploads(org_id=org_id, limit=limit)
    return [RecentUploadItem(**row) for row in rows]


@router.get("/queue-state", response_model=QueueState)
def get_queue_state(
    auth: tuple = Depends(get_current_user_org),
) -> QueueState:
    """Snapshot of the global upload queue — what's running + waiting.

    Lets the dashboard render a live "what's in the pipeline" panel:
    position number, title, product code, status. Read directly from
    Redis + the upload_jobs table (no cache layer in between, so the
    snapshot reflects the current state at call time).

    Returns an empty queue (entries=[], total=0) when Redis is
    unreachable rather than 500 — the dashboard degrades gracefully.
    """
    _user, _token, _ = auth
    max_concurrent = max(1, getattr(settings, "upload_max_concurrent", 1))

    # Build the Redis client locally. The dashboard endpoint is
    # request-scoped + Redis is sync; no constructor injection needed.
    try:
        import json as _json
        import redis as _redis

        from app.services.upload_queue import UploadQueue, _QUEUE_KEY  # type: ignore

        redis_client = _redis.from_url(settings.redis_url, decode_responses=True)
        redis_client.ping()
        raw_entries = redis_client.lrange(_QUEUE_KEY, 0, -1) or []
    except Exception:
        # Redis down → empty snapshot. Dashboard hides the panel.
        return QueueState(max_concurrent=max_concurrent, entries=[], total=0)

    entries: list[QueueEntry] = []
    admin = get_admin_client()
    for position, raw in enumerate(raw_entries, start=1):
        try:
            payload = _json.loads(
                raw if isinstance(raw, str) else raw.decode("utf-8")
            )
        except Exception:
            continue
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            continue
        title = None
        product_code = None
        job_status = None
        # Best-effort job-row lookup; failure here just leaves the
        # enrichment fields None.
        try:
            row = (
                admin
                .schema("youtube_crawler")
                .table("upload_jobs")
                .select("title,product_code,status")
                .eq("id", job_id)
                .limit(1)
                .execute()
            )
            if row.data:
                title = row.data[0].get("title")
                product_code = row.data[0].get("product_code")
                job_status = row.data[0].get("status")
        except Exception:
            pass
        entries.append(
            QueueEntry(
                position=position,
                job_id=job_id,
                enqueued_at=float(payload.get("enqueued_at") or 0),
                title=title,
                product_code=product_code,
                status=job_status,
            )
        )

    return QueueState(
        max_concurrent=max_concurrent,
        entries=entries,
        total=len(entries),
    )


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``view_count`` / ``like_count`` / ``comment_count`` arrive
    as ints. PostgREST returns them as ints in production; some test
    fixtures send strings ('1500'), so the schema normalisation lives
    here rather than at the Pydantic boundary."""
    out = dict(row)
    for key in ("view_count", "like_count", "comment_count"):
        if key in out:
            try:
                out[key] = int(out[key] or 0)
            except (TypeError, ValueError):
                out[key] = 0
    return out


__all__ = ["router"]
