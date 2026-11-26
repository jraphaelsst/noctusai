"""Meta ad-analytics engine — pure KPI computations over insights rows (no I/O).

ONE implementation for every consumer: social-wiring's campaigns API (S2b) and
the noctus MCP "property report" tool (S3) both call this module, so the app
and the agent read identical numbers. Ported from the validated dev-phase
`products/social-wiring/projects/meta-ads-snapshots/kpi_pack.py`; definitions
in `.claude/skills/noc-meta-ads-report/kpis.md`, field traps in
`KB § PRODUCTS/social-wiring/META-ADS-MANAGER-MAP.md` §5.

Input rows are `AdAnalyticsRow` (from `MetaAdapter.ad_account_insights`) OR
plain Graph-shaped dicts (one `act_{id}/insights` row, e.g. stored JSON) —
dicts go through the same mapper (`ad_analytics_row_from_body`), so there is
one parse.

Definitions (never blend objectives; every rate is `None` when its
denominator is 0 or its numerator is absent):

- form leads = `actions[onsite_conversion.lead_grouped]` (own attribution
  setting; Graph omits zero actions, so absent = 0). Never `lead` (2x).
- qualified = `results` whose indicator starts with `conversion_leads`
  (CRM events sent back to Meta; only ad sets optimised for it report it, so
  `None` = not measured, not 0). Objective cost/qualified divides the WHOLE
  objective spend (a lower bound on quality — kpi_pack's rule).
- link CTR = inline_link_clicks / impressions; click->lead = leads / link
  clicks; CPL = spend / leads; CPM = 1000 x spend / impressions; frequency =
  impressions / reach (recomputed, never averaged; reach is not additive).
- hook = 3 s views (`actions[video_view]`) / impressions; hold = ThruPlay /
  3 s views; 6s/3s = 6 s views / 3 s views.
- curve = `video_play_curve_actions` (22 ints, % of plays reaching a bucket):
  idx 0-14 = second 0-14; 15-17 = 15-20 / 20-25 / 25-30 s; 18-20 = 30-40 /
  40-50 / 50-60 s; 21 = >60 s. Headline points: 1, 3, 5, 10, 14 s.
- fatigue = the ad's own daily series, recent `recent_days` vs its first
  `baseline_days` of delivery: frequency up, link CTR down, CPM up, CPL up,
  each past `threshold_pct`. Period frequency = sum(impr) / sum(DAILY reach)
  — an average daily frequency, comparable between periods, NOT the window's
  unique-reach frequency (which needs its own pull).

Percentages are 0-100 floats (`*_pct`); money is major units; nothing is
rounded (formatting is the consumer's job).

## The `to_dict()` contract — `noctus.meta-ads-kpis/v1`

`PropertyReport.to_dict()` (what S2b serves and S3 returns)::

    {
      "schema": "noctus.meta-ads-kpis/v1",
      "property_code": "ONE10449" | null,
      "window": {"since": "YYYY-MM-DD", "until": "YYYY-MM-DD" | null} | null,
      "ads": [AdKpis],                       # lifetime rows, spend desc
      "objectives_lifetime": [ObjectiveFunnel],
      "objectives_window": [ObjectiveFunnel], # [] without a window
      "daily": [DayPoint],                   # all property ads, date asc
      "breakdowns": {"<dims>": [BreakdownBucket]},  # e.g. "age,gender"
      "fatigue": [FatigueReport],
      "pools": {"<adset_id>": PoolStatus}
    }

    AdKpis = {
      "ad_id", "ad_name", "property_code", "variant", "campaign_id",
      "adset_id", "objective", "date_start", "date_stop",
      "spend", "impressions", "reach", "frequency", "cpm",
      "clicks", "ctr_pct", "link_clicks", "link_ctr_pct",
      "cost_per_link_click", "outbound_clicks",
      "form_leads", "cpl", "click_to_lead_pct",
      "qualified", "cost_per_qualified",
      "result": {"indicator", "value", "cost"} | null,
      "rankings": {"quality", "engagement_rate", "conversion_rate"},
      "video": {
        "views_3s", "plays", "thruplay", "views_6s", "views_30s",
        "hook_rate_pct", "hold_rate_pct", "six_to_three_pct",
        "avg_watch_s", "cost_per_thruplay",
        "quartiles": {"p25", "p50", "p75", "p95", "p100"},
        "curve_points": {"1": int, "3", "5", "10", "14"} | null,
        "curve": [22 ints] | null
      } | null                               # null = no video data at all
    }

    ObjectiveFunnel = {
      "objective", "ads", "spend", "impressions", "cpm", "link_clicks",
      "link_ctr_pct", "form_leads", "cpl", "click_to_lead_pct",
      "qualified", "cost_per_qualified", "qualified_share_pct",
      "other_results"
    }
    DayPoint = {"date", "spend", "impressions", "link_clicks", "form_leads", "cpm"}
    BreakdownBucket = {
      "bucket", "dims": {dim: value}, "spend", "share_pct", "impressions",
      "link_clicks", "form_leads", "cpm"
    }
    FatigueReport = {
      "ad_id", "ad_name", "sufficient_history",
      "baseline": Period, "recent": Period,
      "change_pct": {"frequency", "link_ctr", "cpm", "cpl"},
      "signals": ["frequency_up" | "link_ctr_down" | "cpm_up" | "cpl_up"]
    }
    Period = {"start", "end", "days_with_delivery", "spend", "impressions",
              "frequency", "link_ctr_pct", "cpm", "form_leads", "cpl"}
    PoolStatus = {"kind": "exclusive" | "shared" | "unknown", "ads",
                  "other_ads", "other_active"}

Every key is always present; a value that cannot be computed is `null`.
Adding a key is a minor change; renaming/removing one bumps the schema.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from noctusai_lib.integrations.meta.mappers import (
    ad_analytics_row_from_body,
    split_breakdowns,
)
from noctusai_lib.integrations.meta.types import AdAnalyticsRow

SCHEMA = "noctus.meta-ads-kpis/v1"
LEAD_ACTION = "onsite_conversion.lead_grouped"
QUALIFIED_INDICATOR_PREFIX = "conversion_leads"
VIEW_3S_ACTION = "video_view"
CURVE_POINTS: tuple[int, ...] = (1, 3, 5, 10, 14)
CURVE_BUCKET_LABELS: tuple[str, ...] = tuple(f"{s}s" for s in range(15)) + (
    "15-20s", "20-25s", "25-30s", "30-40s", "40-50s", "50-60s", ">60s",
)
FATIGUE_SIGNALS = ("frequency_up", "link_ctr_down", "cpm_up", "cpl_up")
PROPERTY_CODE_RE = re.compile(r"\b(ONE\d{3,6})\b\s*(.*)$", re.IGNORECASE)

RowLike = AdAnalyticsRow | Mapping[str, Any]


# ─── small pure helpers ───────────────────────────────────────────────────


def pct(n: float | None, d: float | None) -> float | None:
    """100 x n / d; `None` when d is 0/absent or n is absent."""
    if not d or n is None:
        return None
    return 100.0 * n / d


def ratio(n: float | None, d: float | None) -> float | None:
    if not d or n is None:
        return None
    return n / d


def _change_pct(new: float | None, old: float | None) -> float | None:
    if new is None or not old:
        return None
    return 100.0 * (new - old) / old


def parse_property(name: str | None) -> tuple[str | None, str | None]:
    """`"ONE10449 Larissa v2"` -> `("ONE10449", "Larissa v2")`. Exact code
    token (`\\bONE\\d{3,6}\\b`), so `ONE1044` never matches `ONE10449`."""
    m = PROPERTY_CODE_RE.search(name or "")
    if not m:
        return None, None
    return m.group(1).upper(), (m.group(2).strip() or None)


def parse_property_code(name: str | None) -> str | None:
    return parse_property(name)[0]


def _infer_level(row: Mapping[str, Any]) -> str:
    if row.get("ad_id"):
        return "ad"
    if row.get("adset_id"):
        return "adset"
    return "campaign"


def as_row(row: RowLike, *, breakdown_keys: Sequence[str] | None = None) -> AdAnalyticsRow:
    """Normalise one input row (typed or Graph-shaped dict) to `AdAnalyticsRow`."""
    if isinstance(row, AdAnalyticsRow):
        return row
    return ad_analytics_row_from_body(
        dict(row), level=_infer_level(row), breakdown_keys=breakdown_keys
    )


def as_rows(rows: Iterable[RowLike], *, breakdown_keys: Sequence[str] | None = None) -> list[AdAnalyticsRow]:
    return [as_row(r, breakdown_keys=breakdown_keys) for r in rows]


def filter_property_rows(rows: Iterable[RowLike], property_code: str) -> list[AdAnalyticsRow]:
    """Keep rows whose `ad_name` carries EXACTLY `property_code` (Graph's
    `CONTAIN '10449'` also returns `ONE104490`)."""
    code = property_code.upper()
    return [r for r in as_rows(rows) if parse_property_code(r.ad_name) == code]


def form_leads(row: AdAnalyticsRow) -> float:
    return row.action(LEAD_ACTION) or 0.0


def qualified(row: AdAnalyticsRow) -> float | None:
    """CRM-qualified result, `None` when the row does not report it."""
    res = row.result
    if res is None or not (res.indicator or "").startswith(QUALIFIED_INDICATOR_PREFIX):
        return None
    return res.value or 0.0


def _other_result(row: AdAnalyticsRow) -> float:
    res = row.result
    if res is None or (res.indicator or "").startswith(QUALIFIED_INDICATOR_PREFIX):
        return 0.0
    return res.value or 0.0


def _f(v: float | None) -> float:
    return v or 0.0


# ─── per ad ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VideoKpis:
    views_3s: float | None
    plays: float | None
    thruplay: float | None
    views_6s: float | None
    views_30s: float | None
    hook_rate_pct: float | None
    hold_rate_pct: float | None
    six_to_three_pct: float | None
    avg_watch_s: float | None
    cost_per_thruplay: float | None
    quartiles: dict[str, float | None]
    curve_points: dict[str, int] | None
    curve: tuple[int, ...] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "views_3s": self.views_3s,
            "plays": self.plays,
            "thruplay": self.thruplay,
            "views_6s": self.views_6s,
            "views_30s": self.views_30s,
            "hook_rate_pct": self.hook_rate_pct,
            "hold_rate_pct": self.hold_rate_pct,
            "six_to_three_pct": self.six_to_three_pct,
            "avg_watch_s": self.avg_watch_s,
            "cost_per_thruplay": self.cost_per_thruplay,
            "quartiles": dict(self.quartiles),
            "curve_points": dict(self.curve_points) if self.curve_points is not None else None,
            "curve": list(self.curve) if self.curve is not None else None,
        }


def curve_points(curve: Sequence[int] | None, points: Sequence[int] = CURVE_POINTS) -> dict[str, int] | None:
    """Pick headline seconds off the 22-bucket curve (idx = second for 0-14)."""
    if not curve:
        return None
    return {str(s): int(curve[s]) for s in points if 0 <= s < 15 and s < len(curve)}


def video_kpis(row: AdAnalyticsRow) -> VideoKpis | None:
    v = row.video
    has_any = any(
        x is not None
        for x in (v.views_3s, v.plays, v.thruplay, v.p25, v.avg_time_s, v.views_6s, v.play_curve)
    )
    if not has_any:
        return None
    return VideoKpis(
        views_3s=v.views_3s,
        plays=v.plays,
        thruplay=v.thruplay,
        views_6s=v.views_6s,
        views_30s=v.views_30s,
        hook_rate_pct=pct(v.views_3s, row.impressions),
        hold_rate_pct=pct(v.thruplay, v.views_3s),
        six_to_three_pct=pct(v.views_6s, v.views_3s),
        avg_watch_s=v.avg_time_s,
        cost_per_thruplay=v.cost_per_thruplay,
        quartiles={"p25": v.p25, "p50": v.p50, "p75": v.p75, "p95": v.p95, "p100": v.p100},
        curve_points=curve_points(v.play_curve),
        curve=v.play_curve,
    )


@dataclass(frozen=True)
class AdKpis:
    ad_id: str | None
    ad_name: str | None
    property_code: str | None
    variant: str | None
    campaign_id: str | None
    adset_id: str | None
    objective: str | None
    date_start: str | None
    date_stop: str | None
    spend: float | None
    impressions: float | None
    reach: float | None
    frequency: float | None
    cpm: float | None
    clicks: float | None
    ctr_pct: float | None
    link_clicks: float | None
    link_ctr_pct: float | None
    cost_per_link_click: float | None
    outbound_clicks: float | None
    form_leads: float
    cpl: float | None
    click_to_lead_pct: float | None
    qualified: float | None
    cost_per_qualified: float | None
    result: dict[str, Any] | None
    rankings: dict[str, str | None]
    video: VideoKpis | None

    def to_dict(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in ("video", "result", "rankings")}
        out["result"] = dict(self.result) if self.result is not None else None
        out["rankings"] = dict(self.rankings)
        out["video"] = self.video.to_dict() if self.video is not None else None
        return out


def _objective(r: AdAnalyticsRow, campaign_objectives: Mapping[str, str] | None) -> str | None:
    """The campaign's objective when known. The insights row's own `objective`
    can be a LEGACY name (`LINK_CLICKS` for an `OUTCOME_TRAFFIC` campaign), so
    callers holding the campaign list pass `campaign_objectives`."""
    if campaign_objectives and r.campaign_id in campaign_objectives:
        return campaign_objectives[r.campaign_id]
    return r.objective


def ad_kpis(row: RowLike, *, campaign_objectives: Mapping[str, str] | None = None) -> AdKpis:
    """Every per-ad number of the report for ONE row (lifetime or a window)."""
    r = as_row(row)
    leads = form_leads(r)
    q = qualified(r)
    code, variant = parse_property(r.ad_name)
    return AdKpis(
        ad_id=r.ad_id,
        ad_name=r.ad_name,
        property_code=code,
        variant=variant,
        campaign_id=r.campaign_id,
        adset_id=r.adset_id,
        objective=_objective(r, campaign_objectives),
        date_start=r.date_start,
        date_stop=r.date_stop,
        spend=r.spend,
        impressions=r.impressions,
        reach=r.reach,
        frequency=ratio(r.impressions, r.reach),
        cpm=ratio(1000.0 * r.spend if r.spend is not None else None, r.impressions),
        clicks=r.clicks,
        ctr_pct=pct(r.clicks, r.impressions),
        link_clicks=r.inline_link_clicks,
        link_ctr_pct=pct(r.inline_link_clicks, r.impressions),
        cost_per_link_click=(
            r.cost_per_inline_link_click
            if r.cost_per_inline_link_click is not None
            else ratio(r.spend, r.inline_link_clicks)
        ),
        outbound_clicks=r.outbound_clicks,
        form_leads=leads,
        cpl=ratio(r.spend, leads),
        click_to_lead_pct=pct(leads, r.inline_link_clicks),
        qualified=q,
        cost_per_qualified=ratio(r.spend, q),
        result=(
            {"indicator": r.result.indicator, "value": r.result.value, "cost": r.result.cost}
            if r.result is not None
            else None
        ),
        rankings={
            "quality": r.quality_ranking,
            "engagement_rate": r.engagement_rate_ranking,
            "conversion_rate": r.conversion_rate_ranking,
        },
        video=video_kpis(r),
    )


# ─── per objective (lifetime + window) ────────────────────────────────────


@dataclass(frozen=True)
class ObjectiveFunnel:
    objective: str
    ads: int
    spend: float
    impressions: float
    cpm: float | None
    link_clicks: float
    link_ctr_pct: float | None
    form_leads: float
    cpl: float | None
    click_to_lead_pct: float | None
    qualified: float | None
    cost_per_qualified: float | None
    qualified_share_pct: float | None
    other_results: float

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _funnel(objective: str, rows: list[AdAnalyticsRow]) -> ObjectiveFunnel:
    spend = sum(_f(r.spend) for r in rows)
    impr = sum(_f(r.impressions) for r in rows)
    lc = sum(_f(r.inline_link_clicks) for r in rows)
    leads = sum(form_leads(r) for r in rows)
    qs = [q for q in (qualified(r) for r in rows) if q is not None]
    q = sum(qs) if qs else None
    return ObjectiveFunnel(
        objective=objective,
        ads=len({r.object_id for r in rows}),
        spend=spend,
        impressions=impr,
        cpm=ratio(1000.0 * spend, impr),
        link_clicks=lc,
        link_ctr_pct=pct(lc, impr),
        form_leads=leads,
        cpl=ratio(spend, leads),
        click_to_lead_pct=pct(leads, lc),
        qualified=q,
        cost_per_qualified=ratio(spend, q),
        qualified_share_pct=pct(q, leads),
        other_results=sum(_other_result(r) for r in rows),
    )


def _by_objective(
    rows: list[AdAnalyticsRow], campaign_objectives: Mapping[str, str] | None
) -> list[ObjectiveFunnel]:
    groups: dict[str, list[AdAnalyticsRow]] = defaultdict(list)
    for r in rows:
        groups[_objective(r, campaign_objectives) or "?"].append(r)
    return [_funnel(k, v) for k, v in sorted(groups.items())]


def objective_rollup(
    lifetime_rows: Iterable[RowLike], *, campaign_objectives: Mapping[str, str] | None = None
) -> list[ObjectiveFunnel]:
    """Lifetime funnel per objective (never blend objectives)."""
    return _by_objective(as_rows(lifetime_rows), campaign_objectives)


def _in_window(r: AdAnalyticsRow, since: str | None, until: str | None) -> bool:
    d = r.date_start or ""
    return (since is None or d >= since) and (until is None or d <= until)


def window_funnel(
    daily_rows: Iterable[RowLike],
    since: str,
    until: str | None = None,
    *,
    campaign_objectives: Mapping[str, str] | None = None,
) -> list[ObjectiveFunnel]:
    """Funnel per objective over the ads that DELIVERED (spend > 0) in
    [since, until], summed from their daily rows (daily sums reconcile to
    lifetime exactly; zero-delivery days have no row)."""
    rows = [r for r in as_rows(daily_rows) if _in_window(r, since, until)]
    delivered = {r.object_id for r in rows if _f(r.spend) > 0}
    return _by_objective([r for r in rows if r.object_id in delivered], campaign_objectives)


# ─── daily series ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DayPoint:
    date: str
    spend: float
    impressions: float
    link_clicks: float
    form_leads: float
    cpm: float | None

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def daily_series(
    daily_rows: Iterable[RowLike], since: str | None = None, until: str | None = None
) -> list[DayPoint]:
    """Spend / impressions / link clicks / leads per day across the rows."""
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for r in as_rows(daily_rows):
        if not r.date_start or not _in_window(r, since, until):
            continue
        a = acc[r.date_start]
        a[0] += _f(r.spend)
        a[1] += _f(r.impressions)
        a[2] += _f(r.inline_link_clicks)
        a[3] += form_leads(r)
    return [
        DayPoint(date=d, spend=a[0], impressions=a[1], link_clicks=a[2], form_leads=a[3],
                 cpm=ratio(1000.0 * a[0], a[1]))
        for d, a in sorted(acc.items())
    ]


# ─── breakdowns ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BreakdownBucket:
    bucket: str
    dims: dict[str, str]
    spend: float
    share_pct: float | None
    impressions: float
    link_clicks: float
    form_leads: float
    cpm: float | None

    def to_dict(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in self.__dataclass_fields__}
        out["dims"] = dict(self.dims)
        return out


def breakdown_aggregate(
    rows: Iterable[RowLike],
    breakdowns: Sequence[str],
    *,
    ad_ids: Iterable[str] | None = None,
    min_spend: float = 0.0,
) -> list[BreakdownBucket]:
    """Sum breakdown rows per bucket (e.g. `["age,gender"]` -> "25-34|female"),
    optionally restricted to `ad_ids`; spend desc. `share_pct` is over ALL
    buckets; `min_spend` only hides buckets (kpi_pack displayed > 0.5)."""
    dims = split_breakdowns(breakdowns)
    keep = set(ad_ids) if ad_ids is not None else None
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    labels: dict[str, dict[str, str]] = {}
    for r in as_rows(rows, breakdown_keys=dims):
        if keep is not None and r.ad_id not in keep:
            continue
        values = {d: r.breakdown.get(d, "unknown") for d in dims}
        key = "|".join(values[d] for d in dims)
        labels[key] = values
        a = acc[key]
        a[0] += _f(r.spend)
        a[1] += _f(r.impressions)
        a[2] += _f(r.inline_link_clicks)
        a[3] += form_leads(r)
    total = sum(a[0] for a in acc.values())
    return [
        BreakdownBucket(bucket=k, dims=labels[k], spend=a[0], share_pct=pct(a[0], total),
                        impressions=a[1], link_clicks=a[2], form_leads=a[3],
                        cpm=ratio(1000.0 * a[0], a[1]))
        for k, a in sorted(acc.items(), key=lambda kv: (-kv[1][0], kv[0]))
        if min_spend == 0.0 or a[0] > min_spend
    ]


# ─── fatigue ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Period:
    start: str | None
    end: str | None
    days_with_delivery: int
    spend: float
    impressions: float
    frequency: float | None
    link_ctr_pct: float | None
    cpm: float | None
    form_leads: float
    cpl: float | None

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass(frozen=True)
class FatigueReport:
    ad_id: str | None
    ad_name: str | None
    sufficient_history: bool
    baseline: Period
    recent: Period
    change_pct: dict[str, float | None]
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ad_id": self.ad_id,
            "ad_name": self.ad_name,
            "sufficient_history": self.sufficient_history,
            "baseline": self.baseline.to_dict(),
            "recent": self.recent.to_dict(),
            "change_pct": dict(self.change_pct),
            "signals": list(self.signals),
        }


def _period(rows: list[AdAnalyticsRow], start: str, end: str) -> Period:
    sel = [r for r in rows if start <= (r.date_start or "") <= end]
    spend = sum(_f(r.spend) for r in sel)
    impr = sum(_f(r.impressions) for r in sel)
    reach = sum(_f(r.reach) for r in sel)
    lc = sum(_f(r.inline_link_clicks) for r in sel)
    leads = sum(form_leads(r) for r in sel)
    return Period(
        start=start, end=end,
        days_with_delivery=sum(1 for r in sel if _f(r.impressions) > 0),
        spend=spend, impressions=impr, frequency=ratio(impr, reach),
        link_ctr_pct=pct(lc, impr), cpm=ratio(1000.0 * spend, impr),
        form_leads=leads, cpl=ratio(spend, leads),
    )


def fatigue(
    daily_rows: Iterable[RowLike],
    *,
    baseline_days: int = 7,
    recent_days: int = 7,
    threshold_pct: float = 20.0,
) -> list[FatigueReport]:
    """Per ad: last `recent_days` vs the first `baseline_days` of delivery.
    A signal fires when the change passes `threshold_pct` in the bad
    direction. Periods that overlap (history shorter than both windows) give
    `sufficient_history=False` and no signals."""
    by_ad: dict[str | None, list[AdAnalyticsRow]] = defaultdict(list)
    for r in as_rows(daily_rows):
        if r.date_start:
            by_ad[r.ad_id].append(r)
    out: list[FatigueReport] = []
    for ad_id, rows in sorted(by_ad.items(), key=lambda kv: str(kv[0])):
        delivered = sorted(r.date_start for r in rows if _f(r.impressions) > 0)
        if not delivered:
            continue
        first, last = date.fromisoformat(delivered[0]), date.fromisoformat(delivered[-1])
        b_end = first + timedelta(days=baseline_days - 1)
        r_start = last - timedelta(days=recent_days - 1)
        base = _period(rows, first.isoformat(), b_end.isoformat())
        rec = _period(rows, r_start.isoformat(), last.isoformat())
        sufficient = r_start > b_end
        change = {
            "frequency": _change_pct(rec.frequency, base.frequency),
            "link_ctr": _change_pct(rec.link_ctr_pct, base.link_ctr_pct),
            "cpm": _change_pct(rec.cpm, base.cpm),
            "cpl": _change_pct(rec.cpl, base.cpl),
        }
        signals: list[str] = []
        if sufficient:
            if (change["frequency"] or 0) > threshold_pct:
                signals.append("frequency_up")
            if (change["link_ctr"] or 0) < -threshold_pct:
                signals.append("link_ctr_down")
            if (change["cpm"] or 0) > threshold_pct:
                signals.append("cpm_up")
            if (change["cpl"] or 0) > threshold_pct:
                signals.append("cpl_up")
        out.append(FatigueReport(
            ad_id=ad_id, ad_name=rows[0].ad_name, sufficient_history=sufficient,
            baseline=base, recent=rec, change_pct=change, signals=tuple(signals),
        ))
    return out


# ─── shared pools ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PoolStatus:
    kind: str  # "exclusive" | "shared" | "unknown"
    ads: int
    other_ads: int
    other_active: int

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, Mapping) else getattr(obj, key, None)


def pool_status(property_code: str, sibling_ads: Iterable[Any] | None) -> PoolStatus:
    """Is the ad set exclusive to the property or a shared pool (e.g. *Público
    One* under one CBO budget)? `sibling_ads` = the ad set's ads (Graph
    `adset.ads{name,effective_status}` dicts or `Ad` objects). A shared pool's
    ad set numbers must never be attributed to one property."""
    if sibling_ads is None:
        return PoolStatus(kind="unknown", ads=0, other_ads=0, other_active=0)
    sibs = list(sibling_ads)
    code = property_code.upper()
    other = [s for s in sibs if parse_property_code(_get(s, "name")) != code]
    active = [s for s in other if _get(s, "effective_status") == "ACTIVE"]
    if not sibs:
        kind = "unknown"
    else:
        kind = "shared" if other else "exclusive"
    return PoolStatus(kind=kind, ads=len(sibs), other_ads=len(other), other_active=len(active))


# ─── the report ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PropertyReport:
    property_code: str | None
    window_since: str | None
    window_until: str | None
    ads: tuple[AdKpis, ...]
    objectives_lifetime: tuple[ObjectiveFunnel, ...]
    objectives_window: tuple[ObjectiveFunnel, ...]
    daily: tuple[DayPoint, ...]
    breakdowns: dict[str, tuple[BreakdownBucket, ...]] = field(default_factory=dict)
    fatigue: tuple[FatigueReport, ...] = ()
    pools: dict[str, PoolStatus] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "property_code": self.property_code,
            "window": (
                {"since": self.window_since, "until": self.window_until}
                if self.window_since else None
            ),
            "ads": [a.to_dict() for a in self.ads],
            "objectives_lifetime": [o.to_dict() for o in self.objectives_lifetime],
            "objectives_window": [o.to_dict() for o in self.objectives_window],
            "daily": [d.to_dict() for d in self.daily],
            "breakdowns": {k: [b.to_dict() for b in v] for k, v in self.breakdowns.items()},
            "fatigue": [f.to_dict() for f in self.fatigue],
            "pools": {k: v.to_dict() for k, v in self.pools.items()},
        }


def build_property_report(
    lifetime_rows: Iterable[RowLike],
    daily_rows: Iterable[RowLike] = (),
    *,
    property_code: str | None = None,
    window_since: str | None = None,
    window_until: str | None = None,
    breakdown_rows: Mapping[str, Iterable[RowLike]] | None = None,
    adset_siblings: Mapping[str, Iterable[Any]] | None = None,
    campaign_objectives: Mapping[str, str] | None = None,
) -> PropertyReport:
    """Assemble the whole report. With `property_code`, rows are first cut
    to the exact code. Breakdown buckets are restricted to the window's
    delivering ads when a window is given (pull the breakdowns over the window
    too — lifetime breakdowns silently mix in old delivery)."""
    life = as_rows(lifetime_rows)
    daily = as_rows(daily_rows)
    if property_code:
        life = filter_property_rows(life, property_code)
        daily = filter_property_rows(daily, property_code)
    window_ads: set[str | None] | None = None
    if window_since:
        window_ads = {
            r.object_id for r in daily if _in_window(r, window_since, window_until) and _f(r.spend) > 0
        }
    bds: dict[str, tuple[BreakdownBucket, ...]] = {}
    for dims, rows in (breakdown_rows or {}).items():
        brows = as_rows(rows, breakdown_keys=split_breakdowns([dims]))
        if property_code:
            brows = [r for r in brows if parse_property_code(r.ad_name) == property_code.upper()]
        bds[dims] = tuple(breakdown_aggregate(
            brows, [dims], ad_ids=[a for a in window_ads if a] if window_ads is not None else None,
        ))
    pools = {
        adset_id: pool_status(property_code, sibs)
        for adset_id, sibs in (adset_siblings or {}).items()
    } if property_code else {}
    return PropertyReport(
        property_code=property_code.upper() if property_code else None,
        window_since=window_since,
        window_until=window_until,
        ads=tuple(sorted(
            (ad_kpis(r, campaign_objectives=campaign_objectives) for r in life),
            key=lambda a: -_f(a.spend),
        )),
        objectives_lifetime=tuple(objective_rollup(life, campaign_objectives=campaign_objectives)),
        objectives_window=(
            tuple(window_funnel(daily, window_since, window_until, campaign_objectives=campaign_objectives))
            if window_since else ()
        ),
        daily=tuple(daily_series(daily, window_since, window_until)),
        breakdowns=bds,
        fatigue=tuple(fatigue(daily)),
        pools=pools,
    )


__all__ = [
    "AdKpis",
    "BreakdownBucket",
    "CURVE_BUCKET_LABELS",
    "CURVE_POINTS",
    "DayPoint",
    "FATIGUE_SIGNALS",
    "FatigueReport",
    "LEAD_ACTION",
    "ObjectiveFunnel",
    "Period",
    "PoolStatus",
    "PropertyReport",
    "QUALIFIED_INDICATOR_PREFIX",
    "SCHEMA",
    "VideoKpis",
    "ad_kpis",
    "as_row",
    "as_rows",
    "breakdown_aggregate",
    "build_property_report",
    "curve_points",
    "daily_series",
    "fatigue",
    "filter_property_rows",
    "form_leads",
    "objective_rollup",
    "parse_property",
    "parse_property_code",
    "pct",
    "pool_status",
    "qualified",
    "ratio",
    "video_kpis",
    "window_funnel",
]
