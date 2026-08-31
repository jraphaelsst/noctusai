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
from app.modules.meta_ads.services.leads import leads_from_actions
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


class AdsPacingRowOut(BaseModel):
    """One active campaign's budget-pacing row: the EFFECTIVE daily
    budget (campaign-level for CBO, or the summed active-ad-set budget
    for ABO) against the most recent day's spend. `budget_source` makes
    the rollup explicit so the UI can say "orçamento por conjunto" when
    it summed ad sets. All money is minor-unit (cents)."""

    object_id: str
    name: str | None = None
    effective_daily_budget_cents: int
    budget_source: Literal["campaign", "adset_rollup"]
    latest_spend_cents: int | None = None
    latest_date: str | None = None


class AdsPacingListOut(BaseModel):
    data: list[AdsPacingRowOut]


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
    # The requested breakdown dimension values for THIS row (e.g.
    # {"publisher_platform": "instagram"}) — populated only when a
    # `breakdown=` was requested (the live path), empty otherwise. Carries
    # the platform label the placement-split chart groups by.
    breakdown: dict[str, str] = {}


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


class AdsAccountDailyOut(BaseModel):
    date: str
    spend_cents: int = 0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    leads: float = 0.0


class AdsAccountInsightsOut(BaseModel):
    """Account-level period aggregate — sums EVERY campaign's daily
    snapshots server-side (one DB query), so the overview never fans out
    one request per campaign. `actions` carries the summed Meta
    action-type map (lead / link_click / messaging_* …) for the
    objective-aware KPI row; `daily` is the merged per-day series for the
    spend chart. Reach is summed across days (a v1 approximation — Meta
    reach is unique-per-window, not additive; same caveat as `_sum_totals`)."""

    since: str
    until: str
    totals: AdsTotalsOut
    actions: dict[str, float]
    daily: list[AdsAccountDailyOut]


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


# ─── Lead-ads (Instant Form) DTOs ─────────────────────────────────────────
class LeadgenQuestionOut(BaseModel):
    key: str | None = None
    label: str | None = None
    type: str | None = None
    options: list[dict[str, str]] = []


class LeadgenFormOut(BaseModel):
    form_id: str
    name: str | None = None
    status: str | None = None
    locale: str | None = None
    leads_count: int | None = None
    created_time: str | None = None
    page_id: str | None = None
    page_name: str | None = None
    questions: list[LeadgenQuestionOut] = []


class LeadFormsSummaryOut(BaseModel):
    """Form inventory + field schema + volume metrics. ``source`` is
    ``"db"`` when served from the persisted ``meta_ads_lead_forms`` table
    (the norm after a sync) or ``"live"`` on the pre-sync fallback read.
    ``records_available`` is True when the per-lead RECORDS are reachable —
    stored records exist (db) or the live ``leads_retrieval`` probe passed
    (live). ``stored_leads`` / ``last_synced_at`` describe the persisted
    state (both null/0 on a live read)."""

    total_leads: int
    forms_count: int
    active_forms: int
    forms_with_leads: int
    pages: list[dict[str, str]]
    records_available: bool
    forms: list[LeadgenFormOut]
    source: Literal["db", "live"] = "live"
    stored_leads: int = 0
    last_synced_at: str | None = None


class LeadFieldOut(BaseModel):
    name: str | None = None
    values: list[str] = []


class LeadRecordOut(BaseModel):
    id: str
    created_time: str | None = None
    ad_id: str | None = None
    ad_name: str | None = None
    campaign_id: str | None = None
    campaign_name: str | None = None
    platform: str | None = None
    is_organic: bool | None = None
    field_data: list[LeadFieldOut] = []


class LeadRecordsOut(BaseModel):
    """Per-form lead RECORDS. ``source`` is ``"db"`` when served from the
    persisted ``meta_ads_leads`` table, ``"live"`` on fallback. ``gated``
    is True (with ``data: []`` + a ``reason``) when a LIVE read hits the
    missing ``leads_retrieval`` scope — surfaced, never a 500 or faked
    empty."""

    form_id: str
    gated: bool = False
    reason: str | None = None
    data: list[LeadRecordOut] = []
    source: Literal["db", "live"] = "live"


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
    """The configured ad account — resolved DB-first (prod:
    ``app_integration_config`` Fernet) with env fallback (dev: root
    ``.env`` ``META_AD_ACCOUNT_ID``), per
    ``feedback_dev_prod_key_storage_model``. Distinct from the
    ``ads_read``-scope gate (a ``MetaGraphError.requires_app_review`` the
    adapter raises) — this is a LOCAL config gap: the account isn't
    configured. 503, mirroring the ``EncryptionNotConfigured`` → 503
    convention for an operator-actionable config gap."""
    from app.services.app_config_store import resolve_meta_ads_config

    _token, account_id, _org = resolve_meta_ads_config(settings=settings)
    if not account_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="meta ads not configured — set the ad account (META_AD_ACCOUNT_ID / app config)",
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
            leads=leads_from_actions(actions),
        )
    return AdsCampaignOut(
        object_id=camp.id,
        name=camp.name,
        objective=camp.objective,
        status=camp.status,
        effective_status=camp.effective_status,
        # Campaign-level budget is populated ONLY for CBO/Advantage
        # campaigns (the budget lives on the campaign). ABO campaigns
        # leave these `None` and carry the budget on their child ad
        # sets instead — the `/insights/pacing` endpoint sums those.
        # Both are already minor-unit (cents), like `AdSet.daily_budget`
        # — no major-unit conversion (contrast the insights money path).
        daily_budget_cents=camp.daily_budget,
        lifetime_budget_cents=camp.lifetime_budget,
        latest=latest,
    )


def _effective_daily_budget(
    camp: Any, ad_sets_by_campaign: dict[str, list[Any]]
) -> tuple[int, str] | None:
    """Resolve a campaign's EFFECTIVE daily budget (minor unit) +
    its source, or ``None`` when the campaign is genuinely unbudgeted.

    CBO/Advantage campaigns carry the budget on the campaign itself
    (``camp.daily_budget``) → source ``"campaign"``. ABO campaigns leave
    that ``None`` and put the budget on each child ad set → sum the
    daily budgets of the campaign's ACTIVE ad sets → source
    ``"adset_rollup"``. A paused ad set contributes nothing (its budget
    is not spending today). If neither yields a positive budget the
    campaign has no daily-pacing target and is excluded (``None``) —
    never surfaced as a misleading ``R$0,00`` budget."""
    if camp.daily_budget:
        return (int(camp.daily_budget), "campaign")
    rollup = 0
    for aset in ad_sets_by_campaign.get(camp.id, []):
        if aset.effective_status == "ACTIVE" and aset.daily_budget:
            rollup += int(aset.daily_budget)
    if rollup > 0:
        return (rollup, "adset_rollup")
    return None


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
        breakdown={str(k): str(v) for k, v in (row.breakdown or {}).items()},
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


def _aggregate_account_snapshots(
    *, org_id: UUID, since: date, until: date
) -> AdsAccountInsightsOut:
    """Sum every campaign's unbroken (no-breakdown) daily snapshots for the
    window into account totals + a merged daily series — ONE DB query, no
    per-campaign fan-out, no Meta call. Backs `GET /insights/account`."""
    admin = get_admin_client()
    resp = (
        admin
        .schema(_SCHEMA)
        .table("ads_insight_snapshots")
        .select("date,spend_cents,impressions,reach,clicks,actions")
        .eq("org_id", str(org_id))
        .eq("level", "campaign")
        .is_("breakdown_key", "null")
        .gte("date", since.isoformat())
        .lte("date", until.isoformat())
        .order("date", desc=False)
        .execute()
    )
    by_date: dict[str, AdsAccountDailyOut] = {}
    actions_total: dict[str, float] = {}
    tot_spend = tot_impr = tot_reach = tot_clicks = 0
    tot_leads = 0.0
    for row in resp.data or []:
        d = str(row.get("date"))
        spend = int(row.get("spend_cents") or 0)
        impr = int(row.get("impressions") or 0)
        reach = int(row.get("reach") or 0)
        clicks = int(row.get("clicks") or 0)
        actions = row.get("actions") or {}
        leads = leads_from_actions(actions) or 0.0

        tot_spend += spend
        tot_impr += impr
        tot_reach += reach
        tot_clicks += clicks
        tot_leads += leads
        for k, v in actions.items():
            try:
                actions_total[k] = actions_total.get(k, 0.0) + float(v)
            except (TypeError, ValueError):
                continue

        day = by_date.get(d)
        if day is None:
            by_date[d] = AdsAccountDailyOut(
                date=d, spend_cents=spend, impressions=impr, reach=reach,
                clicks=clicks, leads=leads,
            )
        else:
            day.spend_cents += spend
            day.impressions += impr
            day.reach += reach
            day.clicks += clicks
            day.leads += leads

    return AdsAccountInsightsOut(
        since=since.isoformat(),
        until=until.isoformat(),
        totals=AdsTotalsOut(
            spend_cents=tot_spend, impressions=tot_impr, reach=tot_reach,
            clicks=tot_clicks, leads=tot_leads,
        ),
        actions=actions_total,
        daily=[by_date[k] for k in sorted(by_date)],
    )


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

    🔴 A `breakdown=` request (e.g. `publisher_platform` for the
    placement-split chart) ALWAYS goes live, even at campaign level: the
    backfill stores only unbroken (breakdown-null) daily snapshots, so a
    breakdown read from the snapshot table would be empty. The live
    adapter returns the platform-split rows with `row.breakdown`
    populated. Propagates ``MetaGraphError`` on the live path — callers
    map it via ``handle_meta_graph_error``."""
    if level == "campaign" and not breakdown:
        return _read_campaign_snapshots(
            org_id=org_id, object_id=object_id, since=since, until=until,
            breakdown=None,
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
    leads = sum((leads_from_actions(r.actions) or 0.0) for r in rows)
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


# ─── GET /insights/pacing ─────────────────────────────────────────────────
@router.get("/insights/pacing", response_model=AdsPacingListOut)
def get_budget_pacing(
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """Budget pacing for ACTIVE campaigns: effective daily budget vs. the
    latest day's spend. Resolves the effective budget per campaign
    (campaign-level for CBO, or a one-call account-wide ad-set rollup for
    ABO — the common real-estate/lead-gen setup where the budget lives on
    the ad set, not the campaign). At most two live Graph calls (campaigns
    + all ad sets), both rate-limit-paced; the ad-set call is skipped
    entirely when every active campaign already has a campaign-level
    budget. Spend comes from the persisted daily snapshots (same source as
    the overview), so pacing never triggers a per-campaign insights fan-out."""
    org_id, adapter = org_and_adapter
    ad_account_id = _require_ad_account_id()
    try:
        campaigns = adapter.list_ad_campaigns(ad_account_id)
        active = [c for c in campaigns if c.effective_status == "ACTIVE"]

        # Only pull ad sets if at least one active campaign lacks a
        # campaign-level budget (ABO) — CBO-only accounts skip the call.
        ad_sets_by_campaign: dict[str, list[Any]] = {}
        if any(not c.daily_budget for c in active):
            for aset in adapter.list_ad_sets(ad_account_id):
                if aset.campaign_id:
                    ad_sets_by_campaign.setdefault(aset.campaign_id, []).append(aset)
    except MetaGraphError as exc:
        logger.warning("meta ads: pacing fetch failed: %s", exc)
        return handle_meta_graph_error(exc)

    latest_by_object = _latest_snapshot_by_object(
        org_id=org_id, object_ids=[c.id for c in active]
    )

    rows: list[AdsPacingRowOut] = []
    for camp in active:
        resolved = _effective_daily_budget(camp, ad_sets_by_campaign)
        if resolved is None:
            continue  # genuinely unbudgeted — not a R$0 pacing row
        budget_cents, source = resolved
        snap = latest_by_object.get(camp.id)
        rows.append(
            AdsPacingRowOut(
                object_id=camp.id,
                name=camp.name,
                effective_daily_budget_cents=budget_cents,
                budget_source=source,
                latest_spend_cents=(snap or {}).get("spend_cents"),
                latest_date=(snap or {}).get("date"),
            )
        )

    # Hottest pacing first: highest spend-vs-budget ratio at the top.
    rows.sort(
        key=lambda r: (
            (r.latest_spend_cents or 0) / r.effective_daily_budget_cents
        ),
        reverse=True,
    )
    return AdsPacingListOut(data=rows)


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


# ─── GET /insights/account ────────────────────────────────────────────────
@router.get("/insights/account", response_model=AdsAccountInsightsOut)
def get_account_insights(
    since: date = Query(...),
    until: date = Query(...),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """Account-level period aggregate for the overview — sums every
    campaign's daily snapshots server-side in ONE query (no per-campaign
    fan-out, no Meta call, so no rate-limit exposure). Call it twice
    (current + previous window) for the period-comparison deltas."""
    org_id, _adapter = org_and_adapter
    return _aggregate_account_snapshots(org_id=org_id, since=since, until=until)


# ─── GET /export ──────────────────────────────────────────────────────────
@router.get("/export")
def export_report(
    format: Literal["csv", "pdf"] = Query("csv"),
    since: date = Query(...),
    until: date = Query(...),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """Download a per-campaign period report as CSV or PDF. DB-only (reads
    the persisted snapshots + the stored account row) — no live Meta call,
    so an export can never be rate-limited."""
    from fastapi import Response

    from app.modules.meta_ads.services import ads_export_service as export

    org_id, _adapter = org_and_adapter
    admin = get_admin_client()
    acct_resp = (
        admin.schema(_SCHEMA).table("ads_accounts")
        .select("name,currency").eq("org_id", str(org_id)).limit(1).execute()
    )
    acct = (acct_resp.data or [{}])[0]
    report = export.build_report(
        admin, org_id=org_id,
        account_name=acct.get("name") or "Conta de anúncios",
        currency=acct.get("currency") or "BRL",
        since=since, until=until,
    )
    stamp = f"anuncios_{since.isoformat()}_{until.isoformat()}"
    if format == "pdf":
        return Response(
            content=export.to_pdf(report),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{stamp}.pdf"'},
        )
    return Response(
        content=export.to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stamp}.csv"'},
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


# ─── GET /leads/forms · GET /leads/records (Instant Form leads) ───────────
def _iso(dt: Any) -> str | None:
    return dt.isoformat() if isinstance(dt, datetime) else None


def _leadgen_form_out(form: Any, *, page_name: str | None) -> LeadgenFormOut:
    return LeadgenFormOut(
        form_id=form.id,
        name=form.name,
        status=form.status,
        locale=form.locale,
        leads_count=form.leads_count,
        created_time=_iso(form.created_time),
        page_id=form.page_id,
        page_name=page_name,
        questions=[
            LeadgenQuestionOut(
                key=q.key, label=q.label, type=q.type, options=list(q.options)
            )
            for q in form.questions
        ],
    )


def _lead_record_out(lead: Any) -> LeadRecordOut:
    return LeadRecordOut(
        id=lead.id,
        created_time=_iso(lead.created_time),
        ad_id=lead.ad_id,
        ad_name=lead.ad_name,
        campaign_id=lead.campaign_id,
        campaign_name=lead.campaign_name,
        platform=lead.platform,
        is_organic=lead.is_organic,
        field_data=[
            LeadFieldOut(name=fd.name, values=list(fd.values))
            for fd in lead.field_data
        ],
    )


_LEADS_RETRIEVAL_HINT = (
    "O acesso aos registros de leads (nome/telefone/e-mail) exige a "
    "permissão 'leads_retrieval', que este token ainda não possui. "
    "Gere um novo token do Usuário do Sistema com 'leads_retrieval' "
    "marcada (Configurações do Negócio → Usuários do Sistema) e "
    "atualize a credencial. Formulários e contagens já funcionam sem ela."
)


# ─── DB reads (persisted lead tables, migration 033) ─────────────────────
def _read_lead_forms_db(org_id: UUID) -> list[dict[str, Any]]:
    admin = get_admin_client()
    resp = (
        admin.schema(_SCHEMA)
        .table("meta_ads_lead_forms")
        .select(
            "id,page_id,name,status,locale,leads_count,questions,"
            "created_time,synced_at"
        )
        .eq("org_id", str(org_id))
        .order("leads_count", desc=True)
        .execute()
    )
    return resp.data or []


def _count_stored_leads(org_id: UUID) -> int:
    # Select ids and count — id-only rows are cheap even at this account's
    # ~1k leads, and it works identically on the real client and the test
    # mock (avoids relying on PostgREST `count='exact'` header support).
    admin = get_admin_client()
    resp = (
        admin.schema(_SCHEMA)
        .table("meta_ads_leads")
        .select("id")
        .eq("org_id", str(org_id))
        .execute()
    )
    return len(resp.data or [])


def _db_form_out(row: dict[str, Any]) -> LeadgenFormOut:
    return LeadgenFormOut(
        form_id=row["id"],
        name=row.get("name"),
        status=row.get("status"),
        locale=row.get("locale"),
        leads_count=row.get("leads_count"),
        created_time=row.get("created_time"),
        page_id=row.get("page_id"),
        page_name=None,
        questions=[
            LeadgenQuestionOut(
                key=q.get("key"), label=q.get("label"),
                type=q.get("type"), options=list(q.get("options") or []),
            )
            for q in (row.get("questions") or [])
        ],
    )


def _db_record_out(row: dict[str, Any]) -> LeadRecordOut:
    raw = row.get("raw") or []
    return LeadRecordOut(
        id=row["id"],
        created_time=row.get("created_time"),
        ad_id=row.get("ad_id"),
        campaign_id=row.get("campaign_id"),
        campaign_name=row.get("campaign_name"),
        platform=row.get("platform"),
        is_organic=row.get("is_organic"),
        field_data=[
            LeadFieldOut(name=fd.get("name"), values=list(fd.get("values") or []))
            for fd in raw
        ],
    )


def _live_lead_forms_summary(adapter: MetaAdapter) -> LeadFormsSummaryOut:
    """Pre-sync fallback: read forms + schema + metrics LIVE, probe records
    availability. Used only when nothing has been synced to the DB yet."""
    pages = adapter.list_facebook_pages()
    page_name_by_id = {p.id: p.name for p in pages}
    forms: list[Any] = []
    for p in pages:
        forms.extend(adapter.list_leadgen_forms(p.id, with_questions=True))
    forms.sort(key=lambda f: (f.leads_count or 0), reverse=True)
    with_leads = [f for f in forms if int(f.leads_count or 0) > 0]
    records_available = False
    if with_leads:
        top = with_leads[0]
        try:
            adapter.list_leads(top.id, page_id=top.page_id, limit=1)
            records_available = True
        except MetaGraphError as exc:
            if not exc.is_permission:
                logger.warning("meta ads: lead-records probe non-permission error: %s", exc)
    return LeadFormsSummaryOut(
        total_leads=sum(int(f.leads_count or 0) for f in forms),
        forms_count=len(forms),
        active_forms=sum(1 for f in forms if f.status == "ACTIVE"),
        forms_with_leads=len(with_leads),
        pages=[{"id": p.id, "name": p.name or ""} for p in pages],
        records_available=records_available,
        forms=[_leadgen_form_out(f, page_name=page_name_by_id.get(f.page_id))
               for f in forms],
        source="live",
    )


@router.get("/leads/forms", response_model=LeadFormsSummaryOut)
def list_lead_forms(
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """Lead-gen inventory + field schema + volume metrics. **DB-first**:
    served from the persisted ``meta_ads_lead_forms`` (migration 033) once
    a sync has run; falls back to a LIVE read before the first sync so the
    tab is never blank. ``records_available`` = stored records exist (db) OR
    the live ``leads_retrieval`` probe passed (live)."""
    org_id, adapter = org_and_adapter
    db_forms = _read_lead_forms_db(org_id)
    if not db_forms:
        try:
            return _live_lead_forms_summary(adapter)
        except MetaGraphError as exc:
            logger.warning("meta ads: live lead forms fetch failed: %s", exc)
            return handle_meta_graph_error(exc)

    stored = _count_stored_leads(org_id)
    with_leads = [f for f in db_forms if int(f.get("leads_count") or 0) > 0]
    synced_times = [f.get("synced_at") for f in db_forms if f.get("synced_at")]
    page_ids = {f.get("page_id") for f in db_forms if f.get("page_id")}
    return LeadFormsSummaryOut(
        total_leads=sum(int(f.get("leads_count") or 0) for f in db_forms),
        forms_count=len(db_forms),
        active_forms=sum(1 for f in db_forms if f.get("status") == "ACTIVE"),
        forms_with_leads=len(with_leads),
        pages=[{"id": pid, "name": ""} for pid in sorted(page_ids)],
        records_available=stored > 0,
        forms=[_db_form_out(f) for f in db_forms],
        source="db",
        stored_leads=stored,
        last_synced_at=max(synced_times) if synced_times else None,
    )


@router.get("/leads/records", response_model=LeadRecordsOut)
def list_lead_records(
    form_id: str = Query(...),
    page_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """The per-lead RECORDS for one form. **DB-first**: served from the
    persisted ``meta_ads_leads`` once synced; falls back to a LIVE read for
    a form with no stored records. On the live path a missing
    ``leads_retrieval`` scope returns a clean ``{gated:true, reason}`` (200)
    so the UI shows an actionable banner, never an error."""
    org_id, adapter = org_and_adapter
    admin = get_admin_client()
    resp = (
        admin.schema(_SCHEMA)
        .table("meta_ads_leads")
        .select(
            "id,created_time,ad_id,campaign_id,campaign_name,platform,"
            "is_organic,raw"
        )
        .eq("org_id", str(org_id))
        .eq("form_id", form_id)
        .order("created_time", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    if rows:
        return LeadRecordsOut(
            form_id=form_id, source="db",
            data=[_db_record_out(r) for r in rows],
        )

    # Live fallback — nothing stored for this form yet.
    try:
        leads = adapter.list_leads(form_id, page_id=page_id, limit=limit)
    except MetaGraphError as exc:
        if exc.is_permission:
            return LeadRecordsOut(
                form_id=form_id, gated=True, reason=_LEADS_RETRIEVAL_HINT,
                source="live",
            )
        logger.warning("meta ads: lead records fetch failed: %s", exc)
        return handle_meta_graph_error(exc)
    return LeadRecordsOut(
        form_id=form_id, gated=False, source="live",
        data=[_lead_record_out(lead) for lead in leads],
    )


def _run_lead_sync_job(job_id: str, *, org_id: UUID, adapter: MetaAdapter) -> None:
    from app.modules.meta_ads.services.leads_sync_service import LeadsSyncService
    try:
        svc = LeadsSyncService(admin_supabase=get_admin_client())
        result = svc.sync_all(org_id=org_id, adapter=adapter)
        detail = (
            f"forms={result['forms_upserted']} leads={result['leads_upserted']}"
            + (" (records gated: leads_retrieval)" if result["records_gated"] else "")
        )
        _set_job(job_id, status_="done", detail=detail)
    except MetaGraphError as exc:
        _set_job(job_id, status_="error", detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - job thread: never lose the error
        logger.exception("meta ads: lead sync job failed")
        _set_job(job_id, status_="error", detail=str(exc))


@router.post("/leads/sync", response_model=AdsSyncStartedOut, status_code=status.HTTP_202_ACCEPTED)
def start_lead_sync(
    org_and_adapter: tuple[UUID, MetaAdapter] = Depends(_resolve_ads_adapter),
):
    """Pull forms + leads from Meta and upsert them into the persisted lead
    tables (background job — the ingest makes ~70 rate-limit-paced Graph
    calls, too slow for a synchronous request). Returns a ``job_id``; poll
    ``GET /sync/{job_id}``. Records are skipped (surfaced in the job detail)
    when ``leads_retrieval`` is not granted — forms still sync."""
    org_id, adapter = org_and_adapter
    job_id = str(uuid.uuid4())
    _set_job(job_id, status_="running")
    threading.Thread(
        target=_run_lead_sync_job,
        kwargs={"job_id": job_id, "org_id": org_id, "adapter": adapter},
        daemon=True,
    ).start()
    return AdsSyncStartedOut(job_id=job_id)


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
