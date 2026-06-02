"""YouTube snapshot HTTP surface — Phase 3.

Endpoints:
    POST   /api/youtube/snapshot/run?account_id=     trigger a snapshot run
    GET    /api/youtube/channel/trend                channel-level timeseries
    GET    /api/youtube/videos/{youtube_video_id}/trend  per-video timeseries

All endpoints are authenticated via ``Depends(get_current_user_org)``.
Write path (snapshot/run) uses the admin client (service role). Read paths
use the user client (RLS-bounded).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.config import SocialWiringSettings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_settings,
    get_user_client,
)
from app.modules.youtube.services.snapshot_service import (
    SnapshotOutcome,
    SnapshotService,
    SnapshotServiceError,
)
from app.services.account_credentials import build_youtube_service_for_org
from app.services.credential_vault import EncryptionNotConfigured
from app.modules.youtube.services.youtube import YouTubeNotConnected, YouTubeServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube", tags=["youtube-snapshot"])

_SCHEMA = "social_wiring"


# ─── Response schemas ───────────────────────────────────────────────────

class SnapshotRunResponse(BaseModel):
    """Response for POST /api/youtube/snapshot/run."""
    account_id: UUID
    snapshot_date: date
    skipped: bool = False
    videos_upserted: int = 0
    shorts_upserted: int = 0
    video_snapshots_upserted: int = 0
    backfilled: bool = False
    needs_probe_count: int = 0


class ChannelTrendPoint(BaseModel):
    snapshot_date: date
    subscriber_count: int = 0
    view_count: int = 0
    video_count: int = 0


class ChannelTrendResponse(BaseModel):
    points: list[ChannelTrendPoint]


class VideoTrendPoint(BaseModel):
    snapshot_date: date
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0


class VideoTrendResponse(BaseModel):
    points: list[VideoTrendPoint]


# ─── POST /api/youtube/snapshot/run ────────────────────────────────────

@router.post("/snapshot/run", response_model=SnapshotRunResponse)
def run_snapshot(
    account_id: Optional[UUID] = Query(default=None),
    force: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> SnapshotRunResponse:
    """Trigger a daily snapshot for the org's YouTube account.

    Idempotent: re-running the same day updates rows in-place.
    A 'done' run for today is a no-op (skipped=True) unless ``force=True``.
    ``account_id`` pins to a specific channel; omit for the default account.

    Used by the Sincronizar button, n8n automations, and the daily cron.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    admin = get_admin_client()

    # Resolve account_id if not provided.
    resolved_account_id = _resolve_account_id(
        admin=admin, cfg=cfg, org_id=org_id, account_id=account_id
    )

    svc = SnapshotService(admin_supabase=admin, cfg=cfg)
    try:
        outcome = svc.run_for_account(
            org_id=org_id,
            account_id=resolved_account_id,
            force=force,
        )
    except YouTubeNotConnected as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
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

    return SnapshotRunResponse(
        account_id=outcome.account_id,
        snapshot_date=outcome.snapshot_date,
        skipped=outcome.skipped,
        videos_upserted=outcome.videos_upserted,
        shorts_upserted=outcome.shorts_upserted,
        video_snapshots_upserted=outcome.video_snapshots_upserted,
        backfilled=outcome.backfilled,
        needs_probe_count=outcome.needs_probe_count,
    )


# ─── GET /api/youtube/channel/trend ────────────────────────────────────

@router.get("/channel/trend", response_model=ChannelTrendResponse)
def channel_trend(
    account_id: Optional[UUID] = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> ChannelTrendResponse:
    """Channel-level subscriber/view/video timeseries for the last N days.

    Returns points in ascending date order. ``account_id`` (optional) pins
    to a specific channel; omit for the default account.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    admin = get_admin_client()
    user_sb = get_user_client(token)

    resolved_account_id = _resolve_account_id(
        admin=admin, cfg=cfg, org_id=org_id, account_id=account_id
    )

    from datetime import timedelta
    cutoff = (datetime.utcnow().date() - timedelta(days=days - 1)).isoformat()

    resp = (
        user_sb
        .schema(_SCHEMA)
        .table("youtube_channel_snapshots")
        .select("snapshot_date, subscriber_count, view_count, video_count")
        .eq("account_id", str(resolved_account_id))
        .gte("snapshot_date", cutoff)
        .order("snapshot_date", desc=False)
        .execute()
    )
    rows = resp.data or []
    return ChannelTrendResponse(
        points=[
            ChannelTrendPoint(
                snapshot_date=r["snapshot_date"],
                subscriber_count=int(r.get("subscriber_count") or 0),
                view_count=int(r.get("view_count") or 0),
                video_count=int(r.get("video_count") or 0),
            )
            for r in rows
        ]
    )


# ─── GET /api/youtube/videos/{youtube_video_id}/trend ──────────────────

@router.get("/videos/{youtube_video_id}/trend", response_model=VideoTrendResponse)
def video_trend(
    youtube_video_id: str,
    account_id: Optional[UUID] = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> VideoTrendResponse:
    """Per-video view/like/comment timeseries for the last N days.

    Returns points in ascending date order. ``account_id`` (optional) pins
    to a specific channel; omit for the default account.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    admin = get_admin_client()
    user_sb = get_user_client(token)

    resolved_account_id = _resolve_account_id(
        admin=admin, cfg=cfg, org_id=org_id, account_id=account_id
    )

    from datetime import timedelta
    cutoff = (datetime.utcnow().date() - timedelta(days=days - 1)).isoformat()

    resp = (
        user_sb
        .schema(_SCHEMA)
        .table("youtube_video_snapshots")
        .select("snapshot_date, view_count, like_count, comment_count")
        .eq("account_id", str(resolved_account_id))
        .eq("youtube_video_id", youtube_video_id)
        .gte("snapshot_date", cutoff)
        .order("snapshot_date", desc=False)
        .execute()
    )
    rows = resp.data or []
    return VideoTrendResponse(
        points=[
            VideoTrendPoint(
                snapshot_date=r["snapshot_date"],
                view_count=int(r.get("view_count") or 0),
                like_count=int(r.get("like_count") or 0),
                comment_count=int(r.get("comment_count") or 0),
            )
            for r in rows
        ]
    )


# ─── Helpers ────────────────────────────────────────────────────────────

def _resolve_account_id(
    *, admin: Any, cfg: Any, org_id: UUID, account_id: Optional[UUID]
) -> UUID:
    """Resolve the account_id to use. Raises 404 / 503 on failures."""
    if account_id is not None:
        return account_id

    # Resolve the org's default YouTube account.
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

    from app.services.account_credentials import resolve_default_account as _rd
    account = _rd(ia_svc, org_id, "youtube")
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No YouTube account connected for this org. "
                "Connect via Settings → YouTube before running a snapshot."
            ),
        )
    return account.id


__all__ = ["router"]
