"""Operação — the platform's routines, run ledger, model catalog and costs.

Read side of the scheduler run ledger (`public.scheduler_runs` /
`public.scheduler_jobs`, migration 090, written by every product through
`noctusai_lib.domain.scheduler_runs`) for core's admin "Operação" page and
the owner daily brief. Code only — no LLM call, no paid API.

Every function takes its client (and `now`) as arguments: the router passes
the trusted service-role client, tests pass `MockSupabaseClient`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from apscheduler.triggers.cron import CronTrigger

from noctusai_lib.domain.scheduler_runs import JOBS_TABLE, RUNS_TABLE
from noctusai_lib.integrations.llm.models import all_providers, is_priced, models_for
from noctusai_lib.primitives.timeutil import platform_timezone_name, platform_tz

logger = logging.getLogger(__name__)

CORE_SLUG = "core"
BRIEF_JOB = "core_owner_daily_brief"
#: the brief runs daily at 07:00; no ok run in this long = it is missing.
BRIEF_DEADMAN = timedelta(hours=26)
ROUTINES_WINDOW = timedelta(hours=24)
#: a run may legitimately start this late after its slot (misfire grace,
#: a busy loop) before it counts as missing.
MIN_LATENESS = timedelta(minutes=10)
_MAX_WINDOW_RUNS = 10000
_MAX_FIRE_STEPS = 3000

LlmSpendSource = Callable[[Any, datetime, datetime], dict]


def parse_ts(value: Any) -> Optional[datetime]:
    """An aware datetime from a PostgREST timestamp (or None)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_expected_fire(cron: str, tz: str, before: datetime, *, horizon: timedelta = timedelta(hours=25)) -> Optional[datetime]:
    """The latest fire time of `cron` (in `tz`) that is <= `before`, looking
    back at most `horizon`; None when the cron did not fire in that span (a
    weekly job between its slots)."""
    trigger = CronTrigger.from_crontab(cron, timezone=tz or platform_timezone_name())
    cursor = before - horizon
    last: Optional[datetime] = None
    nxt = trigger.get_next_fire_time(None, cursor)
    steps = 0
    while nxt is not None and nxt <= before and steps < _MAX_FIRE_STEPS:
        last = nxt
        nxt = trigger.get_next_fire_time(nxt, nxt + timedelta(seconds=1))
        steps += 1
    return last


def overdue_since(job: dict, last_started: Optional[datetime], now: datetime) -> Optional[datetime]:
    """When the run this job owes was due, if it never happened; else None.

    cron: the latest slot older than the lateness allowance has no run at or
    after it. interval: nothing ran within one interval (+ allowance) of the
    previous run (or of the product registering the job, if it never ran).
    A job registered AFTER its slot (a deploy at 07:05 for a 07:00 job) does
    not owe that slot."""
    grace = timedelta(seconds=int(job.get("misfire_grace_time") or 30))
    allowance = max(grace, MIN_LATENESS)
    seen = parse_ts(job.get("last_seen_at"))
    if job.get("cron"):
        try:
            due = last_expected_fire(job["cron"], job.get("timezone") or "", now - allowance)
        except ValueError:
            logger.warning("scheduler_jobs %s/%s has an unparseable cron %r", job.get("product"), job.get("job"), job["cron"])
            return None
        if due is None or (seen is not None and seen > due):
            return None
        if last_started is None or last_started < due - timedelta(seconds=5):
            return due
        return None
    interval = job.get("interval_seconds")
    if not interval:
        return None
    base = last_started or seen
    if base is None:
        return None
    due = base + timedelta(seconds=int(interval)) + allowance
    return due if due < now else None


def active_product_slugs(db: Any) -> set[str]:
    """Catalog-active products (`public.products.ativo`) plus core itself."""
    rows = db.table("products").select("slug, ativo").execute().data or []
    return {str(r["slug"]) for r in rows if r.get("ativo") and r.get("slug")} | {CORE_SLUG}


def _run_summary(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "status": row.get("status"),
        "error": row.get("error"),
        "duration_ms": row.get("duration_ms"),
    }


def _latest_run(db: Any, product: str, job: str, *, status: Optional[str] = None) -> Optional[dict]:
    query = db.table(RUNS_TABLE).select("*").eq("product", product).eq("job", job)
    if status:
        query = query.eq("status", status)
    rows = query.order("started_at", desc=True).limit(1).execute().data or []
    return rows[0] if rows else None


def brief_status(db: Any, now: datetime) -> dict:
    """The dead-man: when did the owner brief last finish ok, and is it missing?"""
    last_ok = _latest_run(db, CORE_SLUG, BRIEF_JOB, status="ok")
    last_ok_at = parse_ts(last_ok.get("started_at")) if last_ok else None
    briefs = (
        db.table("owner_briefs").select("id, generated_at").order("generated_at", desc=True).limit(1).execute().data
        or []
    )
    return {
        "job": BRIEF_JOB,
        "last_ok_at": last_ok_at.isoformat() if last_ok_at else None,
        "last_generated_at": briefs[0].get("generated_at") if briefs else None,
        "missing": last_ok_at is None or (now - last_ok_at) > BRIEF_DEADMAN,
        "deadman_hours": int(BRIEF_DEADMAN.total_seconds() // 3600),
    }


def list_routines(db: Any, now: datetime) -> dict:
    """Every registered job per product with its schedule, its last run, the
    last 24h counts and whether a run is missing — failures first."""
    since = (now - ROUTINES_WINDOW).isoformat()
    jobs = db.table(JOBS_TABLE).select("*").execute().data or []
    window = (
        db.table(RUNS_TABLE).select("*").gte("started_at", since)
        .order("started_at", desc=True).limit(_MAX_WINDOW_RUNS).execute().data
        or []
    )
    active = active_product_slugs(db)

    by_key: dict[tuple[str, str], dict] = {}
    for job in jobs:
        by_key[(job["product"], job["job"])] = {"spec": job, "runs": []}
    for run in window:
        by_key.setdefault((run["product"], run["job"]), {"spec": None, "runs": []})["runs"].append(run)

    products: dict[str, dict] = {}
    totals = {"jobs": 0, "runs_24h": 0, "errors_24h": 0, "overdue": 0}
    for (product, job_name), item in sorted(by_key.items()):
        runs = item["runs"]  # newest first
        last = runs[0] if runs else _latest_run(db, product, job_name)
        last_started = parse_ts(last.get("started_at")) if last else None
        spec = item["spec"] or {}
        is_active = product in active
        due = overdue_since(spec, last_started, now) if (spec and is_active) else None
        errors = sum(1 for r in runs if r.get("status") == "error")
        entry = {
            "job": job_name,
            "cron": spec.get("cron"),
            "interval_seconds": spec.get("interval_seconds"),
            "timezone": spec.get("timezone"),
            "last_seen_at": spec.get("last_seen_at"),
            "registered": bool(item["spec"]),
            "last_run": _run_summary(last),
            "runs_24h": len(runs),
            "errors_24h": errors,
            "overdue": due is not None,
            "expected_at": due.isoformat() if due else None,
        }
        bucket = products.setdefault(product, {"product": product, "active": is_active, "jobs": []})
        bucket["jobs"].append(entry)
        totals["jobs"] += 1
        totals["runs_24h"] += len(runs)
        totals["errors_24h"] += errors
        totals["overdue"] += 1 if due else 0

    def _severity(job: dict) -> tuple:
        failing = (job["last_run"] or {}).get("status") == "error"
        return (not (failing or job["overdue"]), -job["errors_24h"], job["job"])

    ordered = []
    for product in sorted(products, key=lambda p: (not products[p]["active"], p)):
        bucket = products[product]
        bucket["jobs"].sort(key=_severity)
        bucket["failing"] = sum(
            1 for j in bucket["jobs"] if j["overdue"] or (j["last_run"] or {}).get("status") == "error"
        )
        ordered.append(bucket)

    return {
        "generated_at": now.isoformat(),
        "timezone": platform_timezone_name(),
        "window_hours": int(ROUTINES_WINDOW.total_seconds() // 3600),
        "brief": brief_status(db, now),
        "products": ordered,
        "totals": totals,
    }


def list_runs(
    db: Any, *, product: Optional[str] = None, job: Optional[str] = None,
    status: Optional[str] = None, limit: int = 100,
) -> list[dict]:
    """Run history, newest first, optionally filtered."""
    query = db.table(RUNS_TABLE).select("*")
    if product:
        query = query.eq("product", product)
    if job:
        query = query.eq("job", job)
    if status:
        query = query.eq("status", status)
    return query.order("started_at", desc=True).limit(limit).execute().data or []


def model_catalog() -> list[dict]:
    """The EFFECTIVE seed model catalog (static rows + operator overlay)."""
    out: list[dict] = []
    for provider in all_providers():
        for m in models_for(provider):
            out.append({
                "id": m.id,
                "label": m.label,
                "provider": m.provider,
                "kind": m.kind,
                "stub": m.stub,
                "description": m.description,
                "cost_per_1m_input_tokens": m.cost_per_1m_input_tokens,
                "cost_per_1m_output_tokens": m.cost_per_1m_output_tokens,
                "cost_per_1m_image_input_tokens": m.cost_per_1m_image_input_tokens,
                "cost_per_1m_image_output_tokens": m.cost_per_1m_image_output_tokens,
                "supports_batch": m.supports_batch,
                "tag_performance": m.tag_performance,
                "priced": is_priced(m),
            })
    return out


def yesterday_window(now: datetime) -> tuple[datetime, datetime]:
    """[00:00, 24:00) of yesterday on the platform clock, as aware datetimes."""
    local = now.astimezone(platform_tz())
    start_today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_today - timedelta(days=1), start_today


def default_llm_spend(db: Any, start: datetime, end: datetime) -> dict:
    """LLM spend in [start, end) per product — read through the EXISTING
    platform-admin aggregation (`app.routers.admin_llm_usage`), so this
    module adds no product→schema map of its own.

    NOC-REMEDIATE[ops-brief-ai-usage-source]: switch to the public.ai_usage
    ledger (per org → product) once the seed ai-usage slice lands; until then
    the per-org split is not available here — 2026-10-29.
    """
    from app.routers.admin_llm_usage import aggregate_llm_usage

    result = aggregate_llm_usage(
        _=None, db=db, product=None, org_id=None,
        from_=start.isoformat(), to=end.isoformat(), limit_per_product=50000,
    )
    per_product = [
        {
            "product": slug,
            "calls": int(v.get("calls") or 0),
            "cost_usd": round(float(v.get("cost_estimate_usd") or 0), 6),
        }
        for slug, v in sorted((result.get("per_product") or {}).items())
    ]
    totals = result.get("totals") or {}
    return {
        "source": "admin_llm_usage",
        "per_product": per_product,
        "per_org": result.get("per_org"),
        "total_usd": round(float(totals.get("cost_estimate_usd") or 0), 6),
        "calls": int(totals.get("calls") or 0),
    }


def safe_llm_spend(source: LlmSpendSource, db: Any, start: datetime, end: datetime) -> dict:
    """`source` with its failure reported in the payload, never swallowed."""
    try:
        return {"available": True, "error": None, **source(db, start, end)}
    except Exception as exc:  # noqa: BLE001 — reported in the payload + logged
        logger.warning("LLM spend source failed: %s", exc, exc_info=True)
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "per_product": [],
                "per_org": None, "total_usd": None, "calls": None}


def cost_ledger_by_org(db: Any, start: datetime, end: datetime) -> dict:
    """`public.cost_ledger` in [start, end): BRL per org (+ fx-pending rows)."""
    rows = (
        db.table("cost_ledger").select("org_id, category, amount_brl, fx_pending, created_at")
        .gte("created_at", start.isoformat()).lt("created_at", end.isoformat())
        .limit(_MAX_WINDOW_RUNS).execute().data
        or []
    )
    orgs: dict[str, dict] = {}
    for r in rows:
        org = str(r.get("org_id") or "")
        bucket = orgs.setdefault(org, {"org_id": org, "amount_brl": 0.0, "pending_fx": 0, "by_category": {}})
        if r.get("fx_pending"):
            bucket["pending_fx"] += 1
            continue
        amount = float(r.get("amount_brl") or 0)
        bucket["amount_brl"] += amount
        cat = r.get("category") or "outros"
        bucket["by_category"][cat] = round(bucket["by_category"].get(cat, 0.0) + amount, 6)
    names = _org_names(db, [o for o in orgs if o])
    out = []
    for org, b in orgs.items():
        b["amount_brl"] = round(b["amount_brl"], 6)
        b["org_name"] = names.get(org) or org or "—"
        out.append(b)
    out.sort(key=lambda b: -b["amount_brl"])
    return {"per_org": out, "total_brl": round(sum(b["amount_brl"] for b in out), 6),
            "pending_fx": sum(b["pending_fx"] for b in out)}


def _org_names(db: Any, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.table("organizations").select("id, nome").in_("id", ids).execute().data or []
    return {str(r["id"]): r.get("nome") or "" for r in rows}


def costs_summary(db: Any, now: datetime, *, llm_source: LlmSpendSource = default_llm_spend) -> dict:
    """Yesterday's LLM spend per product and month-to-date cost ledger per org."""
    y_start, y_end = yesterday_window(now)
    local = now.astimezone(platform_tz())
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {
        "timezone": platform_timezone_name(),
        "yesterday": {"from": y_start.isoformat(), "to": y_end.isoformat()},
        "llm_yesterday": safe_llm_spend(llm_source, db, y_start, y_end),
        "cost_ledger_yesterday": cost_ledger_by_org(db, y_start, y_end),
        "cost_ledger_month": cost_ledger_by_org(db, month_start, now),
    }


__all__ = [
    "BRIEF_DEADMAN",
    "BRIEF_JOB",
    "CORE_SLUG",
    "active_product_slugs",
    "brief_status",
    "cost_ledger_by_org",
    "costs_summary",
    "default_llm_spend",
    "last_expected_fire",
    "list_routines",
    "list_runs",
    "model_catalog",
    "overdue_since",
    "parse_ts",
    "safe_llm_spend",
    "yesterday_window",
]
