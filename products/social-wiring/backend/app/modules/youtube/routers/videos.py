"""Videos pipeline HTTP surface.

Endpoints:
    GET    /api/videos                                paginated list
    GET    /api/videos/{youtube_video_id}             single-row detail
    POST   /api/videos/sync                           force-refresh from YouTube

GET /api/videos now reads from ``youtube_videos`` (kind='video', default) or
``youtube_shorts`` (kind='short') — the new catalog tables populated by
SnapshotService. The read path is RLS-bounded by the user-scoped Supabase client.

POST /api/videos/sync now calls SnapshotService.run_for_account so the
"Sincronizar" button populates the new tables + records a daily snapshot.
Legacy ``video_cache`` is kept intact (deprecate separately).

Auth pattern: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import SocialWiringSettings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_settings,
    get_user_client,
)
from app.modules.youtube.schemas.video import VideoListResponse, VideoOut, VideoSyncResult
from app.services.credential_vault import (
    CredentialStore, EncryptionNotConfigured)
from app.services.account_credentials import build_youtube_service_for_org
from app.modules.youtube.services.video_cache import VideoCacheError, VideoCacheService
from app.modules.youtube.services.youtube import (
    YouTubeNotConnected,
    YouTubeServiceError,
)
from app.modules.youtube.services.snapshot_service import SnapshotService, SnapshotServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])


# ─── Helpers ───────────────────────────────────────────────────────────
# (`coerce_org_uuid` lifted to app.dependencies at the N=3 recurrence
# trigger — see its docstring there.)


def _build_video_cache_service(
    token: str,
    cfg: SocialWiringSettings,
    account_id: Optional[UUID] = None,
) -> VideoCacheService:
    """Wire the read+write split for the cache service.

    ``account_id`` pins the YouTube service to a specific account (the
    channel-switching seam). ``None`` (default) resolves the org's default.

    503 on encryption-key / youtube-credentials gaps — same shape as
    settings_router / upload_router. Operator-actionable error rather
    than a 500 trace.

    Config arrives via ``cfg`` (resolved by ``Depends(get_settings)`` at
    the endpoint) — the DI seam replacing direct ``app.config.settings``
    reads. See ``KB § PATTERNS/di-test-seam.md``."""
    user_supabase = get_user_client(token)
    admin_supabase = get_admin_client()

    try:
        youtube = build_youtube_service_for_org(
            admin_supabase, cfg, account_id=account_id
        )
    except (EncryptionNotConfigured, YouTubeServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return VideoCacheService(
        user_supabase=user_supabase,
        admin_supabase=admin_supabase,
        youtube_service=youtube,
    )


def _row_to_out(row: dict[str, Any], *, kind: str = "video") -> VideoOut:
    """Database row → VideoOut. Centralised so column-shape drift
    surfaces in one place.

    ``kind`` distinguishes youtube_videos ('video') from youtube_shorts
    ('short'). Shorts rows carry ``detected_via`` / ``is_short_confidence``;
    these are omitted for regular videos.

    Supports both the legacy ``video_cache`` shape (has ``duration``
    column) and the new youtube_videos/youtube_shorts shape (has
    ``duration_iso`` column).
    """
    # duration: legacy cache uses 'duration', new tables use 'duration_iso'.
    duration = row.get("duration") or row.get("duration_iso")
    return VideoOut(
        id=UUID(row["id"]),
        youtube_video_id=row["youtube_video_id"],
        title=row.get("title"),
        description=row.get("description"),
        thumbnail_url=row.get("thumbnail_url"),
        published_at=row.get("published_at"),
        duration=duration,
        privacy_status=row.get("privacy_status"),
        view_count=row.get("view_count", 0),
        like_count=row.get("like_count", 0),
        comment_count=row.get("comment_count", 0),
        favorite_count=row.get("favorite_count", 0),
        tags=row.get("tags") or [],
        category_id=row.get("category_id"),
        uploaded_via_app=row.get("uploaded_via_app", False),
        synced_at=row["synced_at"],
        kind=kind,
        is_short=(kind == "short") if kind else None,
        detected_via=row.get("detected_via") if kind == "short" else None,
    )


# ─── GET /api/videos — paginated list ──────────────────────────────────
_SCHEMA = "social_wiring"
_KIND_TABLE: dict[str, str] = {
    "video": "youtube_videos",
    "short": "youtube_shorts",
}


@router.get("", response_model=VideoListResponse)
def list_videos(
    auth: tuple = Depends(get_current_user_org),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor."),
    limit: int = Query(default=50, ge=1, le=100),
    uploaded_via_app: bool | None = Query(default=None, alias="uploaded_via_app"),
    account_id: Optional[UUID] = Query(default=None),
    kind: Literal["video", "short"] = Query(default="video"),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> VideoListResponse:
    """Paginated list from the new catalog tables.

    ``kind='video'`` (default) reads from ``youtube_videos``;
    ``kind='short'`` reads from ``youtube_shorts``.

    Cursor is ``"<published_at>|<id>"`` (same shape as video_cache).
    ``account_id`` (optional) scopes to a specific YouTube account.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    table_name = _KIND_TABLE.get(kind, "youtube_videos")
    user_sb = get_user_client(token)

    # Resolve account_id filter. If provided, filter directly; else filter
    # by org_id only (covers the default account case via RLS + org_id scope).
    builder = (
        user_sb
        .schema(_SCHEMA)
        .table(table_name)
        .select("*", count="exact")
        .eq("org_id", str(org_id))
        .order("published_at", desc=True)
        .order("id", desc=True)
        .limit(limit + 1)
    )
    if account_id is not None:
        builder = builder.eq("account_id", str(account_id))
    if uploaded_via_app is not None:
        builder = builder.eq("uploaded_via_app", uploaded_via_app)
    if cursor:
        ts_part, _, id_part = cursor.partition("|")
        if ts_part:
            if id_part:
                builder = builder.or_(
                    f"published_at.lt.{ts_part},"
                    f"and(published_at.eq.{ts_part},id.lt.{id_part})"
                )
            else:
                builder = builder.lt("published_at", ts_part)

    response = builder.execute()
    rows = list(response.data or [])
    total_known = getattr(response, "count", None) or len(rows)

    next_cursor: str | None = None
    if len(rows) > limit:
        tail = rows[limit - 1]
        next_cursor = f"{tail.get('published_at') or ''}|{tail['id']}"
        rows = rows[:limit]

    return VideoListResponse(
        items=[_row_to_out(row, kind=kind) for row in rows],
        next_cursor=next_cursor,
        total_known=total_known,
    )


# ─── GET /api/videos/{youtube_video_id} — single ───────────────────────
@router.get("/{youtube_video_id}", response_model=VideoOut)
def get_video(
    youtube_video_id: str,
    account_id: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> VideoOut:
    """Single video by YouTube ID. Checks youtube_videos then youtube_shorts.
    Returns 404 if not in the catalog — trigger POST /api/videos/sync to populate.

    ``account_id`` (optional) scopes to a specific YouTube account.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_sb = get_user_client(token)

    for table_name, kind in [("youtube_videos", "video"), ("youtube_shorts", "short")]:
        builder = (
            user_sb
            .schema(_SCHEMA)
            .table(table_name)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("youtube_video_id", youtube_video_id)
            .limit(1)
        )
        if account_id is not None:
            builder = builder.eq("account_id", str(account_id))
        resp = builder.execute()
        if resp.data:
            return _row_to_out(resp.data[0], kind=kind)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"video {youtube_video_id!r} not in catalog. "
            "Run POST /api/videos/sync to refresh from YouTube."
        ),
    )


# ─── POST /api/videos/sync — refresh from YouTube ──────────────────────
@router.post("/sync", response_model=VideoSyncResult)
def sync_videos(
    account_id: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> VideoSyncResult:
    """Walk the channel's full video list (multi-page) and populate the new
    catalog tables (youtube_videos / youtube_shorts / youtube_video_snapshots
    / youtube_channel_snapshots). Synchronous — the response includes summary
    counts.

    Internally delegates to SnapshotService.run_for_account (which also
    records a daily snapshot). The legacy video_cache table is NOT written
    here; it remains intact for backward compatibility until deprecated.

    ``account_id`` (optional) scopes to a specific YouTube account.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    admin = get_admin_client()

    # Resolve account_id if not provided.
    resolved_account_id = _resolve_sync_account(
        admin=admin, cfg=cfg, org_id=org_id, account_id=account_id
    )

    svc = SnapshotService(admin_supabase=admin, cfg=cfg)
    try:
        outcome = svc.run_for_account(
            org_id=org_id,
            account_id=resolved_account_id,
            force=True,   # Sincronizar button always refreshes
        )
    except YouTubeNotConnected as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{exc} Connect via Settings → YouTube before syncing.",
        ) from exc
    except YouTubeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"YouTube API failed: {exc}",
        ) from exc
    except SnapshotServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    from datetime import datetime as _dt, timezone as _tz
    return VideoSyncResult(
        inserted=outcome.videos_upserted + outcome.shorts_upserted,
        updated=0,
        fetched=outcome.videos_upserted + outcome.shorts_upserted,
        pages=0,
        quota_units_estimated=3,  # uploads-playlist path: ~3 units/page
        last_synced_at=_dt.now(_tz.utc),
    )


def _resolve_sync_account(
    *, admin: Any, cfg: Any, org_id: UUID, account_id: Optional[UUID]
) -> UUID:
    if account_id is not None:
        return account_id
    from app.services.account_credentials import resolve_default_account
    from app.services.integration_account_service import build_integration_account_service
    try:
        ia_svc = build_integration_account_service(
            admin, encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    account = resolve_default_account(ia_svc, org_id, "youtube")
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No YouTube account connected. Connect via Settings → YouTube.",
        )
    return account.id


__all__ = ["router"]
