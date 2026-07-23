"""Meta Ads console — router (W3.1 contract + W3.2 implementation).

Prefix ``/api/meta/ads``. Org-scoped via ``Depends(get_current_user_org)``
(the SAME authenticated-session auth dependency every other Meta router
in this product uses — ``KB § PATTERNS/backend/backend.md`` Auth —
canonical pattern) resolved through :func:`_resolve_ads_adapter`.

Distinct from the account-scoped ``get_account_adapter`` seam
(``app/routers/_meta_common.py``) every Wave-3 per-client Meta router
(insights/DMs/content/comments) uses: the Ads console reads a single
Business-Portfolio-owned ad account via the workspace-global System
User token (``settings.meta_system_user_token`` + the new
``settings.meta_ad_account_id``), not a per-client
``integration_accounts`` row — there is no ``account_id`` query param
on this surface. ``app.services.meta.get_meta_adapter`` already
resolves System-User-token Priority-1 without a ``credential_store``;
this router calls it with just ``org_id`` (kept for RLS-scoped table
reads/writes, the adapter itself is org-agnostic under Priority 1).

Money is ALWAYS integer cents in the API — every money field is
suffixed ``_cents`` (``KB`` roadmap "Money is always integer cents").
See ``app.modules.meta_ads.services.money`` for the two DISTINCT unit
conventions the Marketing API mixes (AdAccount/AdSet fields are already
minor-unit; Insights spend/cpc/cpm are major-unit and need ``* 100``).

``MetaGraphError`` handling reuses the SAME uniform Wave-3 contract
every other Meta router in this product honors
(``app.routers._meta_common.handle_meta_graph_error`` —
``requires_app_review``/``is_capability_missing`` → 200 structured,
any other Graph error → 502 structured) rather than inventing a second
error-mapping convention on this new surface.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from noctusai_lib.api import StrictHttpModel

from app.config import settings
from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.meta_ads.services.ads_sync_service import AdsSyncService
from app.modules.meta_ads.services.money import (
    cents_from_major_unit_float,
    cents_from_minor_unit_string,
)
from app.routers._meta_common import handle_meta_graph_error
from app.services.meta import MetaAdapter, MetaGraphError, get_meta_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meta/ads", tags=["meta-ads"])

_SCHEMA = "social_wiring"


# ─── Response / request DTOs ────────────────────────────────────────────
class AdsAccountOut(BaseModel):
    act_id: str
    name: str | None = None
    currency: str | None = None
    timezone_name: str | None = None
    amount_spent_cents: int | None = None
    balance_cents: int | None = None
    spend_cap_cents: int | None = None
    account_status: int | None = None


class AdsAccountsListOut(BaseModel):
    data: list[AdsAccountOut]


class AdsCampaignLatestOut(BaseModel):
    date: str
    spend_cents: int | None = None
    impressions: int | None = None
    clicks: int | None = None
    reach: int | None = None
    leads: float | None = None


class AdsCampaignOut(BaseModel):
    object_id: str
    name: str | None = None
    objective: str | None = None
    status: str | None = None
    effective_status: str | None = None
    daily_budget_cents: int | None = None
    lifetime_budget_cents: int | None = None
    latest: AdsCampaignLatestOut | None = None


class AdsCampaignsListOut(BaseModel):
    data: list[AdsCampaignOut]


class AdsObjectOut(BaseModel):
    object_id: str
    level: str
    parent_id: str | None = None
    name: str | None = None
    status: str | None = None
    effective_status: str | None = None
    daily_budget_cents: int | None = None
    optimization_goal: str | None = None
    creative_id: str | None = None
    creative_thumbnail_url: str | None = None


class AdsObjectsListOut(BaseModel):
    data: list[AdsObjectOut]


class AdsInsightsRowOut(BaseModel):
    date: str
    spend_cents: int | None = None
    impressions: int | None = None
    reach: int | None = None
    clicks: int | None = None
    cpc_cents: int | None = None
    cpm_cents: int | None = None
    ctr: float | None = None
    actions: dict[str, float] = {}
    action_values: dict[str, float] = {}


class AdsInsightsSeriesOut(BaseModel):
    object_id: str
    level: str
    rows: list[AdsInsightsRowOut]


class AdsTotalsOut(BaseModel):
    spend_cents: int = 0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    leads: float = 0.0


class DeltaOut(BaseModel):
    abs: float
    pct: float | None = None


class AdsInsightsCompareOut(BaseModel):
    current: AdsTotalsOut
    previous: AdsTotalsOut
    deltas: dict[str, DeltaOut]


class AdsActivityOut(BaseModel):
    object_id: str | None = None
    object_level: str | None = None
    event_type: str | None = None
    occurred_at: str
    actor_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class AdsActivitiesListOut(BaseModel):
    data: list[AdsActivityOut]


class AdsSyncIn(StrictHttpModel):
    mode: Literal["incremental", "backfill"] = "incremental"


class AdsSyncStartedOut(BaseModel):
    job_id: str


class AdsSyncStatusOut(BaseModel):
    job_id: str
    status: str
    detail: str | None = None


# ─── In-process sync-job registry ───────────────────────────────────────
# Simple in-memory dict — mirrors the "simple in-process job record" the
# brief allows (this product's YouTube upload jobs are Redis-queue
# backed, but that queue is tied to the upload pipeline; a low-frequency,
# single-account, read-only sync does not warrant standing up a second
# queue). Process-local: a restart loses in-flight job status (acceptable
# — the underlying sync itself is idempotent and safe to re-trigger).
_SYNC_JOBS: dict[str, dict[str, Any]] = {}
_SYNC_JOBS_LOCK = threading.Lock()


def _set_job(job_id: str, *, status_: str, detail: str | None = None) -> None:
    with _SYNC_JOBS_LOCK:
        _SYNC_JOBS[job_id] = {"status": status_, "detail": detail}


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _SYNC_JOBS_LOCK:
        job = _SYNC_JOBS.get(job_id)
        return dict(job) if job is not None else None


def _run_sync_job(
    job_id: str, *, org_id: UUID, adapter: MetaAdapter, ad_account_id: str, mode: str
) -> None:
    try:
        admin = get_admin_client()
        svc = AdsSyncService(admin_supabase=admin)
        if mode == "backfill":
            svc.backfill_campaign_insights(
                org_id=org_id, adapter=adapter, ad_account_id=ad_account_id
            )
            svc.backfill_activities(
                org_id=org_id, adapter=adapter, ad_account_id=ad_account_id
            )
        else:
            today = datetime.now(timezone.utc).date()
            yesterday = today - timedelta(days=1)
            svc.sync_accounts(org_id=org_id, adapter=adapter)
            svc.sync_hierarchy(org_id=org_id, adapter=adapter, ad_account_id=ad_account_id)
            svc.snapshot_campaign_insights(
                org_id=org_id, adapter=adapter, ad_account_id=ad_account_id,
                since=yesterday, until=today,
            )
            svc.ingest_activities(
                org_id=org_id, adapter=adapter, ad_account_id=ad_account_id,
                since=datetime.now(timezone.utc) - timedelta(days=2),
                until=datetime.now(timezone.utc),
            )
        _set_job(job_id, status_="done")
    except MetaGraphError as exc:
        logger.warning("meta ads sync job %s failed (graph): %s", job_id, exc)
        _set_job(job_id, status_="error", detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — job status IS the error surface
        logger.error("meta ads sync job %s failed: %s", job_id, exc, exc_info=True)
        _set_job(job_id, status_="error", detail=str(exc))


# ─── Adapter / config resolution ─────────────────────────────────────────
def _resolve_ads_adapter(
    auth: tuple = Depends(get_current_user_org),
) -> tuple[UUID, MetaAdapter]:
    """Org-scoped adapter resolution — the SAME
    ``Depends(get_current_user_org)`` auth every other Meta router uses.
    ``org_id`` is used for the RLS-scoped table reads/writes below; the
    adapter itself resolves via ``app.services.meta.get_meta_adapter``'s
    Priority-1 System-User-token path, which does not need
    ``credential_store``/``org_id`` to construct the live adapter."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    adapter = get_meta_adapter(org_id=str(org_id))
    return org_id, adapter


def _require_ad_account_id() -> str:
    """The configured ad account (``settings.meta_ad_account_id``,
    ``META_AD_ACCOUNT_ID`` env). Distinct from the ``ads_read``-scope
    gate (that's a ``MetaGraphError.requires_app_review`` the adapter
    itself raises) — this is a LOCAL config gap: the operator hasn't
    set ``META_AD_ACCOUNT_ID`` yet. 503, mirroring
    ``_meta_common.build_store``'s ``EncryptionNotConfigured`` → 503
    convention for an operator-actionable config gap."""
    account_id = getattr(settings, "meta_ad_account_id", "") or ""
    if not account_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="meta ads not configured — set META_AD_ACCOUNT_ID",
        )
    return account_id


# ─── Mappers ─────────────────────────────────────────────────────────────
def _account_out(acct: Any) -> AdsAccountOut:
    return AdsAccountOut(
        act_id=acct.id,
        name=acct.name,
        currency=acct.currency,
        timezone_name=acct.timezone_name,
        amount_spent_cents=cents_from_minor_unit_string(acct.amount_spent),
        balance_cents=cents_from_minor_unit_string(acct.balance),
        spend_cap_cents=cents_from_minor_unit_string(acct.spend_cap),
        account_status=acct.account_status,
    )


def _campaign_out(
    camp: Any, latest_row: dict[str, Any] | None
) -> AdsCampaignOut:
    latest = None
    if latest_row is not None:
        actions = latest_row.get("actions") or {}
        latest = AdsCampaignLatestOut(
            date=latest_row["date"],
            spend_cents=latest_row.get("spend_cents"),
            impressions=latest_row.get("impressions"),
            clicks=latest_row.get("clicks"),
            reach=latest_row.get("reach"),
            leads=actions.get("lead"),
        )
    return AdsCampaignOut(
        object_id=camp.id,
        name=camp.name,
        objective=camp.objective,
        status=camp.status,
        effective_status=camp.effective_status,
        # The live `AdCampaign` type carries no campaign-level budget
        # field (see `ads_sync_service._campaign_row`'s docstring) —
        # None here too, for the same honest reason.
        daily_budget_cents=None,
        lifetime_budget_cents=None,
        latest=latest,
    )


def _adset_out(aset: Any, *, parent_id: str) -> AdsObjectOut:
    return AdsObjectOut(
        object_id=aset.id,
        level="adset",
        parent_id=parent_id,
        name=aset.name,
        status=aset.status,
        effective_status=aset.effective_status,
        daily_budget_cents=aset.daily_budget,
        optimization_goal=aset.optimization_goal,
        creative_id=None,
        creative_thumbnail_url=None,
    )


def _ad_out(ad: Any, *, parent_id: str) -> AdsObjectOut:
    return AdsObjectOut(
        object_id=ad.id,
        level="ad",
        parent_id=parent_id,
        name=ad.name,
        status=ad.status,
        effective_status=ad.effective_status,
        daily_budget_cents=None,
        optimization_goal=None,
        creative_id=ad.creative_id,
        creative_thumbnail_url=ad.creative_thumbnail_url,
    )


def _insights_row_out(row: Any) -> AdsInsightsRowOut:
    """Map a LIVE ``AdInsightsRow`` (adset/ad drill-down path) onto the
    response DTO — applies the same major-unit-to-cents conversion the
    sync service applies when persisting a campaign row, so the two
    paths never disagree on what a "spend_cents" means."""
    return AdsInsightsRowOut(
        date=row.date_start or "",
        spend_cents=cents_from_major_unit_float(row.metrics.get("spend")),
        impressions=_int_or_none(row.metrics.get("impressions")),
        reach=_int_or_none(row.metrics.get("reach")),
        clicks=_int_or_none(row.metrics.get("clicks")),
        cpc_cents=cents_from_major_unit_float(row.metrics.get("cpc")),
        cpm_cents=cents_from_major_unit_float(row.metrics.get("cpm")),
        ctr=row.metrics.get("ctr"),
        actions=dict(row.actions),
        action_values=dict(row.action_values),
    )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _snapshot_row_out(row: dict[str, Any]) -> AdsInsightsRowOut:
    """Map a persisted ``ads_insight_snapshots`` row (campaign path) —
    already cents in the DB, no further conversion."""
    return AdsInsightsRowOut(
        date=row["date"],
        spend_cents=row.get("spend_cents"),
        impressions=row.get("impressions"),
        reach=row.get("reach"),
        clicks=row.get("clicks"),
        cpc_cents=row.get("cpc_cents"),
        cpm_cents=row.get("cpm_cents"),
        ctr=row.get("ctr"),
        actions=row.get("actions") or {},
        action_values=row.get("action_values") or {},
    )


# ─── DB reads ────────────────────────────────────────────────────────────
def _latest_snapshot_by_object(
    *, org_id: UUID, object_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not object_ids:
        return {}
    admin = get_admin_client()
    resp = (
        admin
        .schema(_SCHEMA)
        .table("ads_insight_snapshots")
        .select("object_id,date,spend_cents,impressions,clicks,reach,actions")
        .eq("org_id", str(org_id))
        .in_("object_id", object_ids)
        .is_("breakdown_key", "null")
        .order("date", desc=True)
        .execute()
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in resp.data or []:
        oid = row["object_id"]
        if oid not in latest:  # rows ordered date DESC -> first hit wins
            latest[oid] = row
    return latest


def _read_campaign_snapshots(
    *, org_id: UUID, object_id: str, since: date, until: date, breakdown: str | None
) -> list[AdsInsightsRowOut]:
    admin = get_admin_client()
    q = (
        admin
        .schema(_SCHEMA)
        .table("ads_insight_snapshots")
        .select(
            "date,breakdown_key,spend_cents,impressions,reach,clicks,"
            "cpc_cents,cpm_cents,ctr,actions,action_values"
        )
        .eq("org_id", str(org_id))
        .eq("object_id", object_id)
        .gte("date", since.isoformat())
        .lte("date", until.isoformat())
    )
    q = q.eq("breakdown_key", breakdown) if breakdown else q.is_("breakdown_key", "null")
    resp = q.order("date", desc=False).execute()
    return [_snapshot_row_out(row) for row in (resp.data or [])]


def _fetch_series_rows(
    *,
    org_id: UUID,
    adapter: MetaAdapter,
    object_id: str,
    level: str,
    since: date,
    until: date,
    breakdown: str | None,
) -> list[AdsInsightsRowOut]:
    """Shared by ``GET /insights/series`` and ``GET /insights/compare``:
    campaign level reads the persisted daily-snapshot table (the W2.3
    backfill target); adset/ad level pulls LIVE from the adapter (never
    backfilled — roadmap's explicit campaign-only-backfill decision).
    Propagates ``MetaGraphError`` on the live path — callers map it via
    ``handle_meta_graph_error``."""
    if level == "campaign":
        return _read_campaign_snapshots(
            org_id=org_id, object_id=object_id, since=since, until=until,
            breakdown=breakdown,
        )
    breakdowns = [breakdown] if breakdown else None
    series = adapter.ad_insights_series(
        object_id, level, time_range=(since, until), time_increment=1,
        breakdowns=breakdowns,
    )
    return [_insights_row_out(row) for row in series.rows]


def _sum_totals(rows: list[AdsInsightsRowOut]) -> AdsTotalsOut:
    """Sum a row window into period totals. NOTE: ``reach`` is summed
    across days as a simple v1 approximation — Meta's ``reach`` is
    unique-users-per-window, not additive across days, so a true
    period-reach would need a fresh account-level pull for the WHOLE
    window rather than summing daily rows. Flagged here rather than
    silently presented as exact; acceptable for a v1 relative-comparison
    tile (spend/leads deltas are the primary compare signal)."""
    spend = sum((r.spend_cents or 0) for r in rows)
    impressions = sum((r.impressions or 0) for r in rows)
    reach = sum((r.reach or 0) for r in rows)
    clicks = sum((r.clicks or 0) for r in rows)
    leads = sum((r.actions or {}).get("lead", 0.0) for r in rows)
    return AdsTotalsOut(
        spend_cents=spend, impressions=impressions, reach=reach,
        clicks=clicks, leads=leads,
    )


def _compute_deltas(current: AdsTotalsOut, previous: AdsTotalsOut) -> dict[str, DeltaOut]:
    deltas: dict[str, DeltaOut] = {}
    for field_name in ("spend_cents", "impressions", "reach", "clicks", "leads"):
        cur = getattr(current, field_name)
        prev = getattr(previous, field_name)
        abs_delta = cur - prev
        pct = (abs_delta / prev * 100) if prev else None
        deltas[field_name] = DeltaOut(abs=abs_delta, pct=pct)
    return deltas


# ─── GET /accounts ────────────────────────────────────────────────────────
@router.get("/accounts", response_model=AdsAccountsListOut)
def list_accounts(
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    _org_id, adapter = org_and_adapter
    try:
        accounts = adapter.list_ad_accounts()
    except MetaGraphError as exc:
        logger.warning("meta ads: list_accounts failed: %s", exc)
        return handle_meta_graph_error(exc)
    return AdsAccountsListOut(data=[_account_out(a) for a in accounts])


# ─── GET /campaigns ───────────────────────────────────────────────────────
@router.get("/campaigns", response_model=AdsCampaignsListOut)
def list_campaigns(
    status_filter: str | None = Query(default=None, alias="status"),
    objective: str | None = Query(default=None),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    org_id, adapter = org_and_adapter
    ad_account_id = _require_ad_account_id()
    try:
        campaigns = adapter.list_ad_campaigns(ad_account_id)
    except MetaGraphError as exc:
        logger.warning("meta ads: list_campaigns failed: %s", exc)
        return handle_meta_graph_error(exc)

    if status_filter:
        campaigns = [c for c in campaigns if c.status == status_filter]
    if objective:
        campaigns = [c for c in campaigns if c.objective == objective]

    latest_by_object = _latest_snapshot_by_object(
        org_id=org_id, object_ids=[c.id for c in campaigns]
    )
    return AdsCampaignsListOut(
        data=[_campaign_out(c, latest_by_object.get(c.id)) for c in campaigns]
    )


# ─── GET /campaigns/{object_id}/children ─────────────────────────────────
@router.get("/campaigns/{object_id}/children", response_model=AdsObjectsListOut)
def list_children(
    object_id: str,
    level: Literal["adset", "ad"] = Query(...),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """LIVE drill-down (never the snapshot table — the hierarchy is not
    time-series data): ``list_ad_sets``/``list_ads`` filtered
    server-side by the parent id."""
    _org_id, adapter = org_and_adapter
    ad_account_id = _require_ad_account_id()
    try:
        if level == "adset":
            rows = adapter.list_ad_sets(ad_account_id, campaign_id=object_id)
            data = [_adset_out(r, parent_id=object_id) for r in rows]
        else:
            rows = adapter.list_ads(ad_account_id, adset_id=object_id)
            data = [_ad_out(r, parent_id=object_id) for r in rows]
    except MetaGraphError as exc:
        logger.warning(
            "meta ads: children fetch failed for %s (%s): %s",
            object_id, level, exc,
        )
        return handle_meta_graph_error(exc)
    return AdsObjectsListOut(data=data)


# ─── GET /insights/series ─────────────────────────────────────────────────
@router.get("/insights/series", response_model=AdsInsightsSeriesOut)
def get_insights_series(
    object_id: str = Query(...),
    level: Literal["campaign", "adset", "ad"] = Query(...),
    since: date = Query(...),
    until: date = Query(...),
    breakdown: str | None = Query(default=None),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    org_id, adapter = org_and_adapter
    try:
        rows = _fetch_series_rows(
            org_id=org_id, adapter=adapter, object_id=object_id, level=level,
            since=since, until=until, breakdown=breakdown,
        )
    except MetaGraphError as exc:
        logger.warning(
            "meta ads: insights series failed for %s (%s): %s",
            object_id, level, exc,
        )
        return handle_meta_graph_error(exc)
    return AdsInsightsSeriesOut(object_id=object_id, level=level, rows=rows)


# ─── GET /insights/compare ────────────────────────────────────────────────
@router.get("/insights/compare", response_model=AdsInsightsCompareOut)
def get_insights_compare(
    object_id: str = Query(...),
    level: Literal["campaign", "adset", "ad"] = Query(...),
    since: date = Query(...),
    until: date = Query(...),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """``previous`` = the equally-long window immediately preceding
    ``[since, until]`` (e.g. a 7-day view compares against the prior 7
    days, ending the day before ``since``)."""
    org_id, adapter = org_and_adapter
    window_days = (until - since).days + 1
    prev_until = since - timedelta(days=1)
    prev_since = prev_until - timedelta(days=window_days - 1)

    try:
        current_rows = _fetch_series_rows(
            org_id=org_id, adapter=adapter, object_id=object_id, level=level,
            since=since, until=until, breakdown=None,
        )
        previous_rows = _fetch_series_rows(
            org_id=org_id, adapter=adapter, object_id=object_id, level=level,
            since=prev_since, until=prev_until, breakdown=None,
        )
    except MetaGraphError as exc:
        logger.warning(
            "meta ads: insights compare failed for %s (%s): %s",
            object_id, level, exc,
        )
        return handle_meta_graph_error(exc)

    current_totals = _sum_totals(current_rows)
    previous_totals = _sum_totals(previous_rows)
    return AdsInsightsCompareOut(
        current=current_totals,
        previous=previous_totals,
        deltas=_compute_deltas(current_totals, previous_totals),
    )


# ─── GET /activities ──────────────────────────────────────────────────────
@router.get("/activities", response_model=AdsActivitiesListOut)
def list_activities(
    since: date = Query(...),
    until: date = Query(...),
    object_id: str | None = Query(default=None),
    event_types: str | None = Query(default=None),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """Reads the persisted ``ads_activity_events`` change log — never a
    live Graph call (the daily job + backfill are the only writers)."""
    org_id, _adapter = org_and_adapter
    admin = get_admin_client()
    since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    until_dt = datetime(
        until.year, until.month, until.day, 23, 59, 59, tzinfo=timezone.utc
    )
    q = (
        admin
        .schema(_SCHEMA)
        .table("ads_activity_events")
        .select(
            "object_id,object_level,event_type,occurred_at,actor_name,"
            "old_value,new_value"
        )
        .eq("org_id", str(org_id))
        .gte("occurred_at", since_dt.isoformat())
        .lte("occurred_at", until_dt.isoformat())
    )
    if object_id:
        q = q.eq("object_id", object_id)
    if event_types:
        types = [t.strip() for t in event_types.split(",") if t.strip()]
        if types:
            q = q.in_("event_type", types)
    resp = q.order("occurred_at", desc=True).execute()
    return AdsActivitiesListOut(
        data=[AdsActivityOut(**row) for row in (resp.data or [])]
    )


# ─── POST /sync · GET /sync/{job_id} ──────────────────────────────────────
@router.post("/sync", response_model=AdsSyncStartedOut, status_code=status.HTTP_202_ACCEPTED)
def start_sync(
    payload: AdsSyncIn,
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    org_id, adapter = org_and_adapter
    ad_account_id = _require_ad_account_id()
    job_id = str(uuid.uuid4())
    _set_job(job_id, status_="running")
    thread = threading.Thread(
        target=_run_sync_job,
        kwargs={
            "job_id": job_id,
            "org_id": org_id,
            "adapter": adapter,
            "ad_account_id": ad_account_id,
            "mode": payload.mode,
        },
        daemon=True,
    )
    thread.start()
    return AdsSyncStartedOut(job_id=job_id)


@router.get("/sync/{job_id}", response_model=AdsSyncStatusOut)
def get_sync_status(job_id: str):
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="sync job not found"
        )
    return AdsSyncStatusOut(job_id=job_id, status=job["status"], detail=job.get("detail"))


__all__ = ["router"]
