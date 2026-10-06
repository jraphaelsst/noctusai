"""Instagram insights HTTP surface (Instagram Business Login accounts).

Contract: ``products/social-wiring/projects/core-studio/specs/instagram-insights-api.md``.

    GET  /api/instagram/accounts/{account_id}/profile
    GET  /api/instagram/accounts/{account_id}/profile/trend?days=30
    GET  /api/instagram/accounts/{account_id}/media?cursor=&limit=24
    GET  /api/instagram/accounts/{account_id}/media/{media_id}/insights/history?days=90
    POST /api/instagram/accounts/{account_id}/sync?force=false

Every route: authenticated (``get_current_user_org`` → 401), org from the
SESSION (never a param), account resolved org-scoped and required to be a
``provider="instagram"`` row (else 404 — also the cross-tenant answer); an
optional ``marca_id`` query pins the account to a marca (mismatch → 404).
Reads come from OUR stored catalog/snapshots — no Graph call on a GET.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from noctusai_lib.integrations.meta import MetaGraphError

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.instagram.metrics import (
    PROFILE_METRIC_META,
    media_metric_descriptors,
    profile_metric_descriptors,
)
from app.modules.instagram.repository import (
    INSTAGRAM_PROVIDER,
    MEDIA_TYPED_METRICS,
    PROFILE_FIELD_COLUMNS,
    PROFILE_TYPED_METRICS,
    IgInsightsRepository,
    InvalidCursor,
    row_metrics,
)
from app.modules.instagram.sync_service import (
    REQUIRED_SCOPE,
    TZ_BR,
    IgSyncError,
    IgSyncService,
    missing_insights_scope,
)
from app.routers._meta_common import handle_meta_graph_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instagram", tags=["instagram-insights"])


# ─── DI seams (tests override via app.dependency_overrides) ──────────────
def get_ig_repository() -> IgInsightsRepository:
    return IgInsightsRepository(get_admin_client())


def get_ig_adapter_builder():
    """``(account_id, org_id) -> InstagramLoginAdapter`` for the account."""
    from app.services.meta import get_instagram_login_adapter_for_account

    return get_instagram_login_adapter_for_account


# ─── Response models ─────────────────────────────────────────────────────
class MetricDescriptor(BaseModel):
    key: str
    label: str
    format: Literal["int", "duration_ms", "percent"] = "int"
    priority: int


class ProfileOut(BaseModel):
    account_id: UUID
    marca_id: Optional[UUID] = None
    ig_user_id: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None
    profile_picture_url: Optional[str] = None
    followers_count: Optional[int] = None
    follows_count: Optional[int] = None
    media_count: Optional[int] = None
    biography: Optional[str] = None
    website: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    insights_scope_granted: Optional[bool] = None


class ProfileTrendOut(BaseModel):
    points: list[dict[str, Any]]
    metrics: list[MetricDescriptor]


class MediaItemOut(BaseModel):
    id: str
    media_type: Optional[str] = None
    media_product_type: Optional[str] = None
    caption: Optional[str] = None
    permalink: Optional[str] = None
    thumbnail_url: Optional[str] = None
    media_url: Optional[str] = None
    timestamp: datetime
    like_count: Optional[int] = None
    comments_count: Optional[int] = None
    latest: Optional[dict[str, Any]] = None
    latest_snapshot_date: Optional[date] = None
    synced_at: Optional[datetime] = None


class MediaPageOut(BaseModel):
    items: list[MediaItemOut]
    next_cursor: Optional[str] = None


class MediaHistoryOut(BaseModel):
    media: MediaItemOut
    points: list[dict[str, Any]]
    metrics: list[MetricDescriptor]


class SyncOut(BaseModel):
    status: str
    snapshot_date: date
    media_synced: int
    stories_synced: int
    snapshots_written: int
    profile_snapshot_written: bool
    media_failed: int
    media_skipped: int
    media_outside_window: int
    insights_window_days: int
    errors: list[str]


# ─── Account guard ───────────────────────────────────────────────────────
def resolve_ig_account(
    account_id: str,
    marca_id: Optional[UUID] = Query(default=None, description="optional marca pin"),
    auth: tuple = Depends(get_current_user_org),
    repo: IgInsightsRepository = Depends(get_ig_repository),
) -> dict[str, Any]:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        account_uuid = UUID(account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid account_id") from exc
    account = repo.get_account(account_uuid, org_id)
    if account is None or account.get("provider") != INSTAGRAM_PROVIDER:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"instagram account {account_uuid} not found for this org",
        )
    if marca_id is not None and str(account.get("marca_id") or "") != str(marca_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"instagram account {account_uuid} not found for marca {marca_id}",
        )
    return {**account, "_org_uuid": org_id, "_account_uuid": account_uuid}


def _media_out(row: dict[str, Any]) -> MediaItemOut:
    return MediaItemOut(
        id=str(row["ig_media_id"]),
        media_type=row.get("media_type"),
        media_product_type=row.get("media_product_type"),
        caption=row.get("caption"),
        permalink=row.get("permalink"),
        thumbnail_url=row.get("thumbnail_url"),
        media_url=row.get("media_url"),
        timestamp=row["published_at"],
        like_count=row.get("like_count"),
        comments_count=row.get("comments_count"),
        latest=row.get("latest_metrics"),
        latest_snapshot_date=row.get("latest_snapshot_date"),
        synced_at=row.get("synced_at"),
    )


def _today_br() -> date:
    return datetime.now(timezone.utc).astimezone(TZ_BR).date()


# ─── Routes ──────────────────────────────────────────────────────────────
@router.get("/accounts/{account_id}/profile", response_model=ProfileOut)
def get_profile(account: dict = Depends(resolve_ig_account)) -> ProfileOut:
    """The profile as of the last sync (``integration_accounts.channel_info``,
    written by every sync). Before the first sync only ``username`` (the
    OAuth-time label) is known — every other field is null, never 0."""
    info = account.get("channel_info") or {}
    meta = account.get("metadata") or {}
    return ProfileOut(
        account_id=account["_account_uuid"],
        marca_id=account.get("marca_id"),
        ig_user_id=info.get("channel_id") or meta.get("channel_id"),
        username=info.get("username") or info.get("title") or meta.get("channel_title"),
        name=info.get("name"),
        profile_picture_url=info.get("profile_picture_url"),
        followers_count=info.get("followers_count"),
        follows_count=info.get("follows_count"),
        media_count=info.get("media_count"),
        biography=info.get("biography"),
        website=info.get("website"),
        last_synced_at=account.get("last_synced_at"),
        insights_scope_granted=not missing_insights_scope(account),
    )


@router.get("/accounts/{account_id}/profile/trend", response_model=ProfileTrendOut)
def get_profile_trend(
    days: int = Query(default=30, ge=1, le=730),
    account: dict = Depends(resolve_ig_account),
    repo: IgInsightsRepository = Depends(get_ig_repository),
) -> ProfileTrendOut:
    """Daily account rows from ``ig_profile_snapshots`` (ascending). A metric
    Meta did not serve that day is null."""
    since = _today_br() - timedelta(days=days - 1)
    rows = repo.profile_trend(account["_account_uuid"], account["_org_uuid"], since=since)
    points = []
    for r in rows:
        vals = row_metrics(r, PROFILE_FIELD_COLUMNS + PROFILE_TYPED_METRICS)
        points.append(
            {"date": str(r["snapshot_date"]), **{k: vals.get(k) for k in PROFILE_METRIC_META}}
        )
    return ProfileTrendOut(
        points=points,
        metrics=[MetricDescriptor(**d) for d in profile_metric_descriptors()],
    )


@router.get("/accounts/{account_id}/media", response_model=MediaPageOut)
def list_media(
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=24, ge=1, le=100),
    account: dict = Depends(resolve_ig_account),
    repo: IgInsightsRepository = Depends(get_ig_repository),
) -> MediaPageOut:
    """The stored catalog, ``timestamp DESC, id DESC``, keyset-paginated."""
    try:
        rows, next_cursor = repo.list_media_page(
            account["_account_uuid"], account["_org_uuid"], limit=limit, cursor=cursor
        )
    except InvalidCursor as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MediaPageOut(items=[_media_out(r) for r in rows], next_cursor=next_cursor)


@router.get(
    "/accounts/{account_id}/media/{media_id}/insights/history",
    response_model=MediaHistoryOut,
)
def get_media_history(
    media_id: str,
    days: int = Query(default=90, ge=1, le=730),
    account: dict = Depends(resolve_ig_account),
    repo: IgInsightsRepository = Depends(get_ig_repository),
) -> MediaHistoryOut:
    """Daily snapshots of one post (ascending) + its metric descriptors,
    most relevant first for its media type."""
    row = repo.get_media(account["_account_uuid"], account["_org_uuid"], media_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"media {media_id} not found")
    descriptors = media_metric_descriptors(row.get("media_product_type"), row.get("media_type"))
    keys = [d["key"] for d in descriptors]
    since = _today_br() - timedelta(days=days - 1)
    history = repo.media_history(
        account["_account_uuid"], account["_org_uuid"], media_id, since=since
    )
    points = []
    for r in history:
        vals = row_metrics(r, MEDIA_TYPED_METRICS)
        points.append({"date": str(r["snapshot_date"]), **{k: vals.get(k) for k in keys}})
    return MediaHistoryOut(
        media=_media_out(row),
        points=points,
        metrics=[MetricDescriptor(**d) for d in descriptors],
    )


@router.post("/accounts/{account_id}/sync", response_model=SyncOut)
def sync_account(
    force: bool = Query(default=False),
    account: dict = Depends(resolve_ig_account),
    repo: IgInsightsRepository = Depends(get_ig_repository),
    adapter_builder=Depends(get_ig_adapter_builder),
) -> Any:
    """Run today's catalog + snapshot capture now (the daily job's body).
    Already done today → ``status="skipped"`` unless ``force``. A connection
    missing the insights scope → 409 ``{requires_reconnect: true}``; Graph
    failures follow the shared Meta mapping (``handle_meta_graph_error``)."""
    if missing_insights_scope(account):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "requires_reconnect": True,
                "missing_scopes": [REQUIRED_SCOPE],
                "error": (
                    "Esta conta do Instagram foi conectada sem a permissão de "
                    "insights — reconecte a conta para conceder o acesso."
                ),
            },
        )
    if account.get("status") != "validated":
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "requires_reconnect": True,
                "error": f"account status is {account.get('status')!r}, expected 'validated'",
            },
        )
    svc = IgSyncService(repo=repo, adapter_builder=adapter_builder)
    try:
        outcome = svc.run_for_account(
            org_id=account["_org_uuid"], account_id=account["_account_uuid"], force=force
        )
    except IgSyncError as exc:
        cause = exc.__cause__
        if isinstance(cause, MetaGraphError):
            return handle_meta_graph_error(cause)
        if isinstance(cause, ValueError):  # e.g. no stored token → reconnect
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"requires_reconnect": True, "error": str(cause)},
            )
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc
    return SyncOut(
        status=outcome.status,
        snapshot_date=outcome.snapshot_date,
        media_synced=outcome.media_synced,
        stories_synced=outcome.stories_synced,
        snapshots_written=outcome.snapshots_written,
        profile_snapshot_written=outcome.profile_snapshot_written,
        media_failed=outcome.media_failed,
        media_skipped=outcome.media_skipped,
        media_outside_window=outcome.media_outside_window,
        insights_window_days=outcome.insights_window_days,
        errors=outcome.errors,
    )


__all__ = ["router", "get_ig_repository", "get_ig_adapter_builder", "resolve_ig_account"]
