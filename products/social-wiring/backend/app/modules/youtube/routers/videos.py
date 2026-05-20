"""Videos pipeline HTTP surface.

Endpoints:
    GET    /api/videos                                paginated cache list
    GET    /api/videos/{youtube_video_id}             single-row detail
    POST   /api/videos/sync                           force-refresh from YouTube

The list reads exclusively from the local cache (RLS-bound by the
user-scoped Supabase client); ``sync`` is the only operation that hits
YouTube's API. This split is the cache's whole point — Dashboard +
Videos page render free of YouTube quota.

Auth pattern: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern``. See
``upload_router`` / ``settings_router`` for the same shape.
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
from app.modules.youtube.schemas.video import VideoListResponse, VideoOut, VideoSyncResult
from app.services.credential_vault import (
    CredentialStore, EncryptionNotConfigured, build_credential_store)
from app.modules.youtube.services.video_cache import VideoCacheError, VideoCacheService
from app.modules.youtube.services.youtube import (
    YouTubeNotConnected,
    YouTubeService,
    YouTubeServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])


# ─── Helpers ───────────────────────────────────────────────────────────
# (`coerce_org_uuid` lifted to app.dependencies at the N=3 recurrence
# trigger — see its docstring there.)


def _build_video_cache_service(token: str) -> VideoCacheService:
    """Wire the read+write split for the cache service.

    503 on encryption-key / youtube-credentials gaps — same shape as
    settings_router / upload_router. Operator-actionable error rather
    than a 500 trace."""
    user_supabase = get_user_client(token)
    admin_supabase = get_admin_client()

    try:
        store = build_credential_store(admin_supabase)
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        youtube = YouTubeService(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            redirect_uri=settings.youtube_redirect_uri,
            credential_store=store,
        )
    except YouTubeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return VideoCacheService(
        user_supabase=user_supabase,
        admin_supabase=admin_supabase,
        youtube_service=youtube,
    )


def _row_to_out(row: dict[str, Any]) -> VideoOut:
    """Database row → VideoOut. Centralised so column-shape drift
    surfaces in one place."""
    return VideoOut(
        id=UUID(row["id"]),
        youtube_video_id=row["youtube_video_id"],
        title=row.get("title"),
        description=row.get("description"),
        thumbnail_url=row.get("thumbnail_url"),
        published_at=row.get("published_at"),
        duration=row.get("duration"),
        privacy_status=row.get("privacy_status"),
        view_count=row.get("view_count", 0),
        like_count=row.get("like_count", 0),
        comment_count=row.get("comment_count", 0),
        favorite_count=row.get("favorite_count", 0),
        tags=row.get("tags") or [],
        category_id=row.get("category_id"),
        uploaded_via_app=row.get("uploaded_via_app", False),
        synced_at=row["synced_at"],
    )


# ─── GET /api/videos — paginated list ──────────────────────────────────
@router.get("", response_model=VideoListResponse)
def list_videos(
    auth: tuple = Depends(get_current_user_org),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor."),
    limit: int = Query(default=50, ge=1, le=100),
    uploaded_via_app: bool | None = Query(default=None, alias="uploaded_via_app"),
) -> VideoListResponse:
    """Paginated list of cached videos. Cursor-based — the next_cursor
    in the response is opaque; pass it back as `?cursor=...` to fetch
    the next page."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_video_cache_service(token)

    rows, next_cursor, total_known = service.list(
        org_id=org_id,
        cursor=cursor,
        limit=limit,
        uploaded_via_app=uploaded_via_app,
    )
    return VideoListResponse(
        items=[_row_to_out(row) for row in rows],
        next_cursor=next_cursor,
        total_known=total_known,
    )


# ─── GET /api/videos/{youtube_video_id} — single ───────────────────────
@router.get("/{youtube_video_id}", response_model=VideoOut)
def get_video(
    youtube_video_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> VideoOut:
    """Single video by YouTube ID. Returns 404 if not in the cache —
    callers can trigger a sync to populate."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_video_cache_service(token)

    row = service.get(org_id=org_id, youtube_video_id=youtube_video_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"video {youtube_video_id!r} not in cache. "
                "Run POST /api/videos/sync to refresh from YouTube."
            ),
        )
    return _row_to_out(row)


# ─── POST /api/videos/sync — refresh from YouTube ──────────────────────
@router.post("/sync", response_model=VideoSyncResult)
def sync_videos(
    auth: tuple = Depends(get_current_user_org),
) -> VideoSyncResult:
    """Walk the channel's full video list (multi-page) + upsert into the
    local cache. Synchronous — the response includes the count summary
    so the UI doesn't need a separate status round-trip."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_video_cache_service(token)

    try:
        outcome = service.sync(org_id=org_id)
    except YouTubeNotConnected as exc:
        # 409 — the precondition (connected channel) isn't met.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{exc} Connect via Settings → YouTube before syncing."
            ),
        ) from exc
    except YouTubeServiceError as exc:
        # 502 — upstream API said no (auth invalid, quota, transient).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"YouTube API failed: {exc}",
        ) from exc
    except VideoCacheError as exc:
        # 500 — we couldn't persist what YouTube returned.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Video cache write failed: {exc}",
        ) from exc

    return VideoSyncResult(
        inserted=outcome.inserted,
        updated=outcome.updated,
        fetched=outcome.fetched,
        pages=outcome.pages,
        quota_units_estimated=outcome.quota_units_estimated,
        last_synced_at=outcome.last_synced_at,
    )


__all__ = ["router"]
