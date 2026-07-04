"""Instagram insights — accounts / account-level insights / media (with
per-item insights) / metric-snapshot history + capture.

Shape mirrors ``meta_router``: query-param ``org_id`` (no auth in front
of the Meta surface yet), adapter built via the product's
``get_meta_adapter`` seam, non-raising posture on ``MetaGraphError`` for
the read endpoints (mirrors ``meta_status`` — return a structured
``error`` field, never a 500).

Adapter construction / org resolution / adapter-label helpers are shared
with ``meta_router`` via ``app.routers._meta_common`` (DRY — the same
``_build_store()`` / ``_resolve_org_id()`` / ``_adapter_label()`` logic,
extracted rather than duplicated).

The adapter is resolved through the FastAPI dependency
:func:`get_ig_adapter` — a DI seam (not a bare module-level call) so
tests can override it with a pre-seeded ``FakeMetaAdapter`` via
``app.dependency_overrides`` instead of monkey-patching production code
(``KB § PATTERNS/backend/di-test-seam.md``, Class-B).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.dependencies import get_admin_client
from app.routers._meta_common import (
    adapter_label as _adapter_label,
    build_store as _build_store,
    resolve_org_id as _resolve_org_id,
)
from app.services.meta import MetaAdapter, MetaGraphError, get_meta_adapter
from app.services.meta.snapshots import (
    IGAccountNotFoundError,
    capture_ig_snapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meta/instagram", tags=["meta-insights"])

_SCHEMA = "social_wiring"
_SNAPSHOT_TABLE = "ig_metric_snapshots"


# ─── Response shapes ────────────────────────────────────────────────────
class IGAccountOut(BaseModel):
    id: str
    username: str
    name: str | None = None
    profile_picture_url: str | None = None
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None
    biography: str | None = None
    website: str | None = None
    page_id: str | None = None


class IGAccountsResponse(BaseModel):
    accounts: list[IGAccountOut]
    adapter: str


class IGInsightsResponse(BaseModel):
    object_id: str
    metrics: dict[str, int] = {}
    series: list[dict[str, Any]] = []
    error: str | None = None


class IGMediaItemOut(BaseModel):
    id: str
    caption: str | None = None
    media_type: str | None = None
    permalink: str | None = None
    thumbnail_url: str | None = None
    timestamp: datetime | None = None
    like_count: int = 0
    comments_count: int = 0
    insights: dict[str, int] | None = None


class IGMediaResponse(BaseModel):
    media: list[IGMediaItemOut]


class IGSnapshotOut(BaseModel):
    captured_at: datetime
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None
    reach: int | None = None
    profile_views: int | None = None


class IGSnapshotsResponse(BaseModel):
    snapshots: list[IGSnapshotOut]


# ─── Adapter DI seam ────────────────────────────────────────────────────
def get_ig_adapter(org_id: str | None = Query(default=None)) -> MetaAdapter:
    """Resolve the Meta adapter for this org — the exact construction
    ``meta_router`` uses (``store = _build_store(); get_meta_adapter(...)``),
    exposed as a FastAPI dependency so tests can override it with a
    pre-seeded ``FakeMetaAdapter`` instead of reaching for the live
    credential-store/env resolution path.
    """
    resolved_org = _resolve_org_id(org_id)
    try:
        store = _build_store()
    except HTTPException:
        store = None
    return get_meta_adapter(
        org_id=resolved_org if store else None,
        credential_store=store,
    )


def _account_out(account: Any) -> IGAccountOut:
    return IGAccountOut(
        id=account.id,
        username=account.username,
        name=account.name,
        profile_picture_url=account.profile_picture_url,
        followers_count=account.followers_count,
        follows_count=account.follows_count,
        media_count=account.media_count,
        biography=account.biography,
        website=account.website,
        page_id=account.page_id,
    )


# ─── GET /accounts ──────────────────────────────────────────────────────
@router.get("/accounts", response_model=IGAccountsResponse)
def list_ig_accounts(
    adapter: MetaAdapter = Depends(get_ig_adapter),
) -> IGAccountsResponse:
    """Instagram Business/Creator accounts linked to this org's Meta
    connection."""
    accounts = adapter.list_instagram_accounts()
    return IGAccountsResponse(
        accounts=[_account_out(a) for a in accounts],
        adapter=_adapter_label(adapter),
    )


# ─── GET /{ig_user_id}/insights ─────────────────────────────────────────
@router.get("/{ig_user_id}/insights", response_model=IGInsightsResponse)
def get_ig_account_insights(
    ig_user_id: str,
    period: str = Query(default="day"),
    days: int = Query(default=30, ge=0, le=365),
    adapter: MetaAdapter = Depends(get_ig_adapter),
) -> IGInsightsResponse:
    """Account-level insight metrics for the last ``days`` days.

    ``days=0`` omits the ``since``/``until`` window (the adapter's own
    default window applies). Non-raising on ``MetaGraphError`` — mirrors
    ``meta_status``'s posture: the caller gets a structured ``error``
    field back, never a 500.
    """
    since: int | None = None
    until: int | None = None
    if days > 0:
        until = int(time.time())
        since = until - days * 86400

    try:
        insights = adapter.get_instagram_account_insights(
            ig_user_id, period=period, since=since, until=until
        )
    except MetaGraphError as exc:
        logger.warning(
            "ig insights: account-insights fetch failed for %s: %s",
            ig_user_id, exc,
        )
        return IGInsightsResponse(object_id=ig_user_id, error=str(exc))

    return IGInsightsResponse(
        object_id=insights.object_id,
        metrics=dict(insights.metrics),
        series=list(insights.raw),
    )


# ─── GET /{ig_user_id}/media ────────────────────────────────────────────
@router.get("/{ig_user_id}/media", response_model=IGMediaResponse)
def list_ig_media(
    ig_user_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    with_insights: bool = Query(default=True),
    adapter: MetaAdapter = Depends(get_ig_adapter),
) -> IGMediaResponse:
    """Recent Instagram media for this account. When ``with_insights``,
    each item's per-media insight metrics are fetched individually — a
    ``MetaGraphError`` on ONE item degrades that item's ``insights`` to
    ``null``, never the whole list (a bad/expired post never fails the
    page)."""
    items = adapter.list_instagram_media(ig_user_id, limit)

    media_out: list[IGMediaItemOut] = []
    for item in items:
        item_insights: dict[str, int] | None = None
        if with_insights:
            try:
                item_insights = dict(
                    adapter.get_instagram_media_insights(item.id).metrics
                )
            except MetaGraphError as exc:
                logger.warning(
                    "ig insights: media-insights fetch failed for %s: %s",
                    item.id, exc,
                )
                item_insights = None
        media_out.append(
            IGMediaItemOut(
                id=item.id,
                caption=item.caption,
                media_type=item.media_type,
                permalink=item.permalink,
                thumbnail_url=item.thumbnail_url,
                timestamp=item.timestamp,
                like_count=item.like_count,
                comments_count=item.comments_count,
                insights=item_insights,
            )
        )

    return IGMediaResponse(media=media_out)


# ─── GET /{ig_user_id}/snapshots ────────────────────────────────────────
@router.get("/{ig_user_id}/snapshots", response_model=IGSnapshotsResponse)
def list_ig_snapshots(
    ig_user_id: str,
    org_id: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
) -> IGSnapshotsResponse:
    """Metric-snapshot history for this account, ascending by
    ``captured_at``, over the last ``days`` days."""
    resolved_org = _resolve_org_id(org_id)
    admin = get_admin_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    resp = (
        admin
        .schema(_SCHEMA)
        .table(_SNAPSHOT_TABLE)
        .select(
            "captured_at, followers_count, follows_count, media_count, "
            "reach, profile_views"
        )
        .eq("org_id", str(resolved_org))
        .eq("ig_user_id", ig_user_id)
        .gte("captured_at", cutoff)
        .order("captured_at", desc=False)
        .execute()
    )
    rows = resp.data or []
    return IGSnapshotsResponse(
        snapshots=[IGSnapshotOut(**row) for row in rows]
    )


# ─── POST /{ig_user_id}/snapshot ────────────────────────────────────────
@router.post("/{ig_user_id}/snapshot", response_model=IGSnapshotOut)
def create_ig_snapshot(
    ig_user_id: str,
    org_id: str | None = Query(default=None),
    adapter: MetaAdapter = Depends(get_ig_adapter),
) -> IGSnapshotOut:
    """Capture this account's current numbers now and persist a row.

    Also the unit the daily automation job calls (per-account, via
    ``app.services.meta.snapshots.capture_all_ig_snapshots``). 404 when
    ``ig_user_id`` isn't among this org's Meta-visible accounts.
    """
    resolved_org = _resolve_org_id(org_id)
    admin = get_admin_client()

    try:
        row = capture_ig_snapshot(admin, resolved_org, ig_user_id, adapter)
    except IGAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return IGSnapshotOut(**row)


__all__ = ["router", "get_ig_adapter"]
