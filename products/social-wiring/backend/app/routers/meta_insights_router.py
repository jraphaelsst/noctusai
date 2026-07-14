"""Instagram + Facebook insights — account-scoped (Wave 3).

Every endpoint resolves its Meta adapter via the account-scoped DI seam
``Depends(get_account_adapter)`` (``account_id`` query, required — the
per-client ``integration_accounts`` row, Wave 2's
``get_meta_adapter_for_account``), never the org-level
``get_meta_adapter`` Store-A adapter ``meta_router``/``meta_status``
use. The Instagram user id is resolved FROM the account (via
:func:`app.routers._meta_common.resolve_primary_ig_user_id`) instead of
being taken as a path/query param — Wave 2's per-client Meta connection
is expected to see exactly one linked IG account.

``MetaGraphError`` handling is the uniform Wave 3 contract (shared
``handle_meta_graph_error`` in ``_meta_common``): ``requires_app_review``
→ 200 structured, any other error → 502 structured. Per-item insight
enrichment (one bad media item, one retired FB Page metric) still
degrades to ``None`` / drops itself rather than failing the whole list
— a narrower, additive degrade UNDER the top-level uniform gate, not a
replacement for it.

Pre-Wave-3 shape (org_id query + ``{ig_user_id}`` path param, non-raising
``error``-field responses) is superseded by this file — see
``tests/services/test_ig_insights.py`` for the account-scoped rewrite.

SECURITY (``sw-meta-org-auth-wiring``): the snapshot endpoints below used
to take their OWN ``org_id`` query param (independent of
``get_account_adapter``'s, and separately vulnerable to the same
cross-tenant IDOR) to scope the ``ig_metric_snapshots`` read/write. Both
now derive ``org_id`` from the SAME authenticated session
``get_account_adapter`` already resolves via ``Depends(get_current_user_org)``
— no second, query-param-driven org resolution left on this surface.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.routers._meta_common import (
    get_account_adapter,
    handle_meta_graph_error,
    resolve_primary_ig_user_id,
)
from app.services.meta import MetaAdapter, MetaGraphError
from app.services.meta.snapshots import (
    IGAccountNotFoundError,
    capture_ig_snapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-insights"])

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


class IGInsightsResponse(BaseModel):
    object_id: str
    metrics: dict[str, int] = {}
    series: list[dict[str, Any]] = []


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


class FBPageInsightsResponse(BaseModel):
    object_id: str
    metrics: dict[str, int] = {}
    series: list[dict[str, Any]] = []


def ig_account_to_out(account: Any) -> IGAccountOut:
    """Map a seed ``InstagramAccount`` onto the router's response DTO.

    Public (not underscore-prefixed) — ``meta_context_router`` reuses
    this exact mapper so the ``instagram`` field of ``GET
    /api/meta/context`` and every insights-router account shape stay in
    lockstep (DRY, not a second copy)."""
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


# ─── GET /instagram/insights ────────────────────────────────────────────
@router.get("/api/meta/instagram/insights", response_model=IGInsightsResponse)
def get_ig_account_insights(
    period: str = Query(default="day"),
    days: int = Query(default=30, ge=0, le=365),
    adapter: MetaAdapter = Depends(get_account_adapter),
) -> Any:
    """Account-level insight metrics for the last ``days`` days.

    ``days=0`` omits the ``since``/``until`` window (the adapter's own
    default window applies). ``ig_user_id`` is resolved from the
    account (no path param) — see module docstring.
    """
    since: int | None = None
    until: int | None = None
    if days > 0:
        until = int(time.time())
        since = until - days * 86400

    try:
        ig_user_id = resolve_primary_ig_user_id(adapter)
        insights = adapter.get_instagram_account_insights(
            ig_user_id, period=period, since=since, until=until
        )
    except MetaGraphError as exc:
        logger.warning("ig insights: account-insights fetch failed: %s", exc)
        return handle_meta_graph_error(exc)

    return IGInsightsResponse(
        object_id=insights.object_id,
        metrics=dict(insights.metrics),
        series=list(insights.raw),
    )


# ─── GET /instagram/media ────────────────────────────────────────────────
@router.get("/api/meta/instagram/media", response_model=IGMediaResponse)
def list_ig_media(
    limit: int = Query(default=25, ge=1, le=100),
    with_insights: bool = Query(default=True),
    adapter: MetaAdapter = Depends(get_account_adapter),
) -> Any:
    """Recent Instagram media for this account. When ``with_insights``,
    each item's per-media insight metrics are fetched individually — a
    ``MetaGraphError`` on ONE item degrades that item's ``insights`` to
    ``null``, never the whole list (a bad/expired post never fails the
    page). A failure resolving the account itself, or listing media at
    all, still goes through the uniform gate."""
    try:
        ig_user_id = resolve_primary_ig_user_id(adapter)
        items = adapter.list_instagram_media(ig_user_id, limit)
    except MetaGraphError as exc:
        logger.warning("ig insights: media list fetch failed: %s", exc)
        return handle_meta_graph_error(exc)

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


# ─── GET /instagram/snapshots ────────────────────────────────────────────
@router.get("/api/meta/instagram/snapshots", response_model=IGSnapshotsResponse)
def list_ig_snapshots(
    days: int = Query(default=90, ge=1, le=3650),
    adapter: MetaAdapter = Depends(get_account_adapter),
    auth: tuple = Depends(get_current_user_org),
) -> Any:
    """Metric-snapshot history for this account, ascending by
    ``captured_at``, over the last ``days`` days.

    ``ig_metric_snapshots`` is keyed ``(org_id, ig_user_id)`` (pre-Wave-3
    schema, no ``account_id`` column) — ``ig_user_id`` is resolved from
    the account-scoped adapter (module docstring); ``org_id`` resolves
    from the SAME authenticated session ``get_account_adapter`` uses
    (no caller-supplied ``org_id`` — see module docstring)."""
    try:
        ig_user_id = resolve_primary_ig_user_id(adapter)
    except MetaGraphError as exc:
        return handle_meta_graph_error(exc)

    _, _token, raw_org = auth
    resolved_org = coerce_org_uuid(raw_org)
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


# ─── POST /instagram/snapshot ────────────────────────────────────────────
@router.post("/api/meta/instagram/snapshot", response_model=IGSnapshotOut)
def create_ig_snapshot(
    adapter: MetaAdapter = Depends(get_account_adapter),
    auth: tuple = Depends(get_current_user_org),
) -> Any:
    """Capture this account's current numbers now and persist a row.

    ``ig_user_id`` is resolved from the account-scoped adapter (module
    docstring) — always among ``adapter.list_instagram_accounts()``
    since it came from that very call, so
    :class:`IGAccountNotFoundError` is defensive rather than an expected
    path here (unlike the pre-Wave-3 path-param shape, which took an
    arbitrary caller-supplied id). ``org_id`` resolves from the SAME
    authenticated session ``get_account_adapter`` uses (no caller-
    supplied ``org_id`` — see module docstring)."""
    try:
        ig_user_id = resolve_primary_ig_user_id(adapter)
    except MetaGraphError as exc:
        return handle_meta_graph_error(exc)

    _, _token, raw_org = auth
    resolved_org = coerce_org_uuid(raw_org)
    admin = get_admin_client()

    try:
        row = capture_ig_snapshot(admin, resolved_org, ig_user_id, adapter)
    except IGAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return IGSnapshotOut(**row)


# ─── GET /facebook/insights ──────────────────────────────────────────────
@router.get("/api/meta/facebook/insights", response_model=FBPageInsightsResponse)
def get_facebook_page_insights(
    page_id: str = Query(...),
    period: str = Query(default="day"),
    days: int = Query(default=30, ge=0, le=365),
    adapter: MetaAdapter = Depends(get_account_adapter),
) -> Any:
    """Facebook Page-level insight metrics.

    Meta has been retiring individual Page Insights metrics on a rolling
    basis (many 2026-06-15) — the adapter (``get_facebook_page_insights``)
    already degrades PER METRIC (a retired name drops itself, logged,
    never raised); this endpoint's uniform gate only fires for a
    connection-level failure (bad token / page not visible to this
    identity), never a single stale metric name.
    """
    since: int | None = None
    until: int | None = None
    if days > 0:
        until = int(time.time())
        since = until - days * 86400

    try:
        insights = adapter.get_facebook_page_insights(
            page_id, period=period, since=since, until=until
        )
    except MetaGraphError as exc:
        logger.warning(
            "facebook insights: page-insights fetch failed for %s: %s",
            page_id, exc,
        )
        return handle_meta_graph_error(exc)

    return FBPageInsightsResponse(
        object_id=insights.object_id,
        metrics=dict(insights.metrics),
        series=list(insights.raw),
    )


__all__ = [
    "router",
    "IGAccountOut",
    "ig_account_to_out",
    "IGInsightsResponse",
    "IGMediaResponse",
    "IGSnapshotsResponse",
    "FBPageInsightsResponse",
]
