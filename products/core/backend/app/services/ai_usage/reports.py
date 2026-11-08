"""Read side of "Uso e custo de IA": validation, SourceStatus derivation and aggregation.

Read through the service-role client (the tables are RLS-on with no policy). Two sources, never summed:
`anthropic` (ai_anthropic_*) and `ledger` (dev_telemetry_claude + dev_deliveries). A field a source does not
record is None (null), never 0. An unavailable source yields empty arrays + its status, never an exception.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

COVERAGE_START = date(2026, 1, 1)
MAX_DAYS = 31
STALE_AFTER = timedelta(hours=24)
SOURCES = ("anthropic", "ledger")
UNAVAILABLE_FIELDS = ["spend_limit", "credit_balance", "invoices"]
TOKEN_TYPES = ("uncached_input", "cache_write_5m", "cache_write_1h", "cache_read", "output")

# group_by per source (public name -> normalized dimension). Usage and cost differ: the cost table has no
# service_tier / context_window, so those answer 422 on /cost.
USAGE_GROUPS = {
    "anthropic": {"model": "model", "token_type": "token_type", "service_tier": "service_tier",
                  "context_window": "context_window", "workspace": "workspace", "api_key": "api_key"},
    "ledger": {"model": "model", "agent": "agent", "ambiente": "ambiente", "origem": "origem"},
}
COST_GROUPS = {
    "anthropic": {"model": "model", "token_type": "token_type", "workspace": "workspace", "api_key": "api_key",
                  "cost_type": "cost_type"},
    "ledger": {"model": "model", "agent": "agent", "ambiente": "ambiente", "origem": "origem"},
}
FILTER_DIMS = {
    "anthropic": {"model": "model", "workspace_id": "workspace", "api_key_id": "api_key"},
    "ledger": {"model": "model", "ambiente": "ambiente", "origem": "origem", "agent": "agent"},
}
# normalized dimension -> physical column, per table
USAGE_COLS = {"model": "model", "workspace": "workspace_id", "api_key": "api_key_id", "service_tier": "service_tier",
              "context_window": "context_window"}
COST_COLS = {"model": "model", "workspace": "workspace_id", "api_key": "api_key_id", "cost_type": "cost_type",
             "token_type": "token_type"}
LEDGER_COLS = {"model": "model", "agent": "agent_id", "ambiente": "ambiente", "origem": "origem"}


class ReportError(Exception):
    """A typed 422 (`detail.code`)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ── validation ───────────────────────────────────────────────────────────────────────────────────────────
def parse_window(frm: Optional[str], to: Optional[str]) -> tuple[date, date]:
    try:
        d_from, d_to = date.fromisoformat(frm or ""), date.fromisoformat(to or "")
    except ValueError:
        raise ReportError("range_invalid", "from/to must be YYYY-MM-DD") from None
    if d_to < d_from:
        raise ReportError("range_invalid", "to is before from")
    if d_from < COVERAGE_START:
        raise ReportError("range_before_coverage", f"data starts at {COVERAGE_START.isoformat()}")
    if (d_to - d_from).days + 1 > MAX_DAYS:
        raise ReportError("range_too_long", f"at most {MAX_DAYS} days per call")
    return d_from, d_to


def parse_month(month: Optional[str]) -> tuple[date, date]:
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise ReportError("range_invalid", "month must be YYYY-MM") from None
    if first < COVERAGE_START:
        raise ReportError("range_before_coverage", f"data starts at {COVERAGE_START.isoformat()}")
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def check_filters(source: str, filters: dict[str, Optional[str]]) -> dict[str, str]:
    """Normalized-dimension -> value; a filter the source cannot honour is a typed 422."""
    allowed = FILTER_DIMS[source]
    out: dict[str, str] = {}
    for name, value in filters.items():
        if value is None:
            continue
        if name not in allowed:
            raise ReportError("filter_not_supported_by_source", f"filter {name!r} is not supported by {source}")
        out[allowed[name]] = value
    return out


def check_group_by(source: str, group_by: Optional[str], table: dict) -> Optional[str]:
    if group_by is not None and group_by not in table[source]:
        raise ReportError("group_by_not_supported_by_source", f"group_by {group_by!r} is not supported by {source}")
    return None if group_by is None else table[source][group_by]


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────────
def _ts(value: Any) -> Optional[datetime]:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc) if value else None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _sum(values: Iterable[Any]) -> Optional[Decimal]:
    """None when NOTHING was recorded; else the sum of what was (a missing field is never a fabricated 0)."""
    got = [Decimal(str(v)) for v in values if v is not None]
    return sum(got, Decimal(0)) if got else None


def _int(v: Optional[Decimal]) -> Optional[int]:
    return None if v is None else int(v)


def _bucket_start(day: date, bucket: str) -> date:
    return day - timedelta(days=day.weekday()) if bucket == "week" else day


def _all_rows(db: Any, table: str, columns: str, pk: tuple[str, ...], apply: Callable[[Any], Any]) -> list[dict]:
    """Every row of a filtered read (PostgREST caps an unbounded select at 1000 silently)."""

    def page(start: int, end: int):
        q = apply(db.table(table).select(columns))
        for col in pk:
            q = q.order(col)
        rows = q.range(start, end).execute().data or []
        for r in rows:
            r["_k"] = "|".join(str(r.get(c)) for c in pk)
        return rows

    return list(iter_paged_rows(page, id_key="_k", label=table))


def _edge(db: Any, table: str, column: str, desc: bool, where: Optional[Callable[[Any], Any]] = None) -> Optional[str]:
    q = db.table(table).select(column)
    if where:
        q = where(q)
    rows = q.order(column, desc=desc).limit(1).execute().data or []
    return rows[0][column] if rows else None


# ── SourceStatus ─────────────────────────────────────────────────────────────────────────────────────────
def _status(source: str, **kw: Any) -> dict:
    base = {"id": source, "status": "unavailable", "reason_code": None, "data_refreshed_at": None,
            "last_sync_at": None, "last_success_at": None, "coverage_from": None, "coverage_to": None,
            "final_through": None, "is_estimate": source == "ledger"}
    base.update(kw)
    return base


def anthropic_status(db: Any, *, key_configured: bool, now: datetime) -> dict:
    runs = (db.table("ai_source_sync_runs").select("*").eq("source", "anthropic")
            .order("id", desc=True).limit(50).execute().data or [])
    if not runs:
        return _status("anthropic", reason_code=None if key_configured else "no_admin_key")
    last = runs[0]
    ok = next((r for r in runs if r["status"] == "ok"), None)
    refreshed = _ts(ok.get("data_refreshed_at")) if ok else None
    common = dict(
        data_refreshed_at=_iso(refreshed), last_sync_at=last.get("finished_at"),
        last_success_at=ok.get("finished_at") if ok else None,
        coverage_from=_edge(db, "ai_anthropic_usage_daily", "day", False),
        coverage_to=_edge(db, "ai_anthropic_usage_daily", "day", True),
        final_through=_edge(db, "ai_anthropic_usage_daily", "day", True, lambda q: q.eq("is_final", True)),
    )
    if last["status"] in ("unavailable", "error"):
        return _status("anthropic", status=last["status"], reason_code=last.get("reason_code"), **common)
    stale = refreshed is None or now - refreshed > STALE_AFTER
    return _status("anthropic", status="stale" if stale else "ok", **common)


def ledger_status(db: Any, *, now: datetime) -> dict:
    stamps = [_ts(_edge(db, "dev_telemetry_claude", "synced_at", True)), _ts(_edge(db, "dev_deliveries", "ingested_at", True))]
    stamps = [s for s in stamps if s]
    if not stamps:
        return _status("ledger")
    last = max(stamps)
    lo, hi = _edge(db, "dev_telemetry_claude", "bucket", False), _edge(db, "dev_telemetry_claude", "bucket", True)
    return _status("ledger", status="stale" if now - last > STALE_AFTER else "ok", data_refreshed_at=_iso(last),
                   last_sync_at=_iso(last), last_success_at=_iso(last),
                   coverage_from=str(lo)[:10] if lo else None, coverage_to=str(hi)[:10] if hi else None)


def source_status(db: Any, source: str, *, key_configured: bool, now: datetime) -> dict:
    return anthropic_status(db, key_configured=key_configured, now=now) if source == "anthropic" else ledger_status(db, now=now)


def sources(db: Any, *, key_configured: bool, now: datetime) -> dict:
    return {s: source_status(db, s, key_configured=key_configured, now=now) for s in SOURCES}


# ── normalized fact rows ─────────────────────────────────────────────────────────────────────────────────
def _null(v: Any) -> Optional[str]:
    return None if v in (None, "") else str(v)


def _day_range(frm: date, to: date) -> tuple[str, str]:
    return f"{frm.isoformat()}T00:00:00+00:00", f"{(to + timedelta(days=1)).isoformat()}T00:00:00+00:00"


def _eq_filters(q: Any, flt: dict[str, str], cols: dict[str, str]) -> Any:
    for dim, val in flt.items():
        q = q.eq(cols[dim], "" if (dim == "agent" and val == "main") else val)
    return q


def usage_facts(db: Any, source: str, frm: date, to: date, flt: dict[str, str]) -> list[dict]:
    if source == "anthropic":
        cols = ("day,dims_key,model,workspace_id,api_key_id,service_tier,context_window,uncached_input,cache_write_5m,"
                "cache_write_1h,cache_read,output_tokens,web_search_requests,requests")
        rows = _all_rows(db, "ai_anthropic_usage_daily", cols, ("day", "dims_key"),
                         lambda q: _eq_filters(q.gte("day", frm.isoformat()).lte("day", to.isoformat()), flt, USAGE_COLS))
        return [{
            "day": date.fromisoformat(str(r["day"])[:10]),
            "dims": {"model": _null(r["model"]), "workspace": _null(r["workspace_id"]), "api_key": _null(r["api_key_id"]),
                     "service_tier": _null(r["service_tier"]), "context_window": _null(r["context_window"])},
            "u": r["uncached_input"], "cw5": r["cache_write_5m"], "cw1": r["cache_write_1h"],
            "cw": _int(_sum([r["cache_write_5m"], r["cache_write_1h"]])), "cr": r["cache_read"],
            "out": r["output_tokens"], "web": r.get("web_search_requests"), "req": r.get("requests"),
        } for r in rows]
    lo, hi = _day_range(frm, to)
    cols = "host,bucket,session_id,agent_id,model,ambiente,origem,requests,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens"
    rows = _all_rows(db, "dev_telemetry_claude", cols, ("host", "bucket", "session_id", "agent_id", "model"),
                     lambda q: _eq_filters(q.gte("bucket", lo).lt("bucket", hi), flt, LEDGER_COLS))
    return [{
        "day": date.fromisoformat(str(r["bucket"])[:10]),
        "dims": {"model": _null(r["model"]), "agent": r["agent_id"] or "main", "ambiente": _null(r["ambiente"]),
                 "origem": _null(r["origem"])},
        "u": r["input_tokens"], "cw5": None, "cw1": None, "cw": r["cache_write_tokens"], "cr": r["cache_read_tokens"],
        "out": r["output_tokens"], "web": None, "req": r.get("requests"),
    } for r in rows]


def cost_facts(db: Any, source: str, frm: date, to: date, flt: dict[str, str]) -> list[dict]:
    if source == "anthropic":
        cols = "day,dims_key,model,workspace_id,api_key_id,cost_type,token_type,amount_cents,list_amount_cents"
        rows = _all_rows(db, "ai_anthropic_cost_daily", cols, ("day", "dims_key"),
                         lambda q: _eq_filters(q.gte("day", frm.isoformat()).lte("day", to.isoformat()), flt, COST_COLS))
        return [{
            "day": date.fromisoformat(str(r["day"])[:10]),
            "dims": {"model": _null(r["model"]), "workspace": _null(r["workspace_id"]), "api_key": _null(r["api_key_id"]),
                     "cost_type": _null(r["cost_type"]), "token_type": _null(r["token_type"])},
            "amount": Decimal(str(r["amount_cents"])) / 100,
            "list": None if r.get("list_amount_cents") is None else Decimal(str(r["list_amount_cents"])) / 100,
            "final": bool(r.get("is_final")),
        } for r in rows]
    lo, hi = _day_range(frm, to)
    cols = "host,bucket,session_id,agent_id,model,ambiente,origem,cost_usd"
    rows = _all_rows(db, "dev_telemetry_claude", cols, ("host", "bucket", "session_id", "agent_id", "model"),
                     lambda q: _eq_filters(q.gte("bucket", lo).lt("bucket", hi), flt, LEDGER_COLS))
    return [{
        "day": date.fromisoformat(str(r["bucket"])[:10]),
        "dims": {"model": _null(r["model"]), "agent": r["agent_id"] or "main", "ambiente": _null(r["ambiente"]),
                 "origem": _null(r["origem"])},
        "amount": None if r.get("cost_usd") is None else Decimal(str(r["cost_usd"])),
        "list": None, "final": False,
    } for r in rows]


# ── measures ─────────────────────────────────────────────────────────────────────────────────────────────
def usage_tok(rows: list[dict], source: str, only: Optional[str] = None) -> dict:
    """`Tok` for a set of fact rows. Tokens are always recorded (0 on an empty set); requests/web are not
    always (anthropic nullable; ledger never records web) and stay null when nothing was recorded."""
    zero = Decimal(0)
    u = _sum(r["u"] for r in rows) or zero
    cw = _sum(r["cw"] for r in rows) or zero
    cr = _sum(r["cr"] for r in rows) or zero
    out = _sum(r["out"] for r in rows) or zero
    req = _sum(r["req"] for r in rows)
    web = _sum(r["web"] for r in rows)
    if only is None:
        return {"input_tokens": _int(u + cw + cr), "uncached_input_tokens": _int(u), "cache_write_tokens": _int(cw),
                "cache_read_tokens": _int(cr), "output_tokens": _int(out), "requests": _int(req),
                "web_search_requests": _int(web)}
    # one token type: its column is set, the rest are null (a token type has no request count)
    t = {k: None for k in ("input_tokens", "uncached_input_tokens", "cache_write_tokens", "cache_read_tokens",
                           "output_tokens", "requests", "web_search_requests")}
    if only == "output":
        t["output_tokens"] = _int(out)
    elif only == "uncached_input":
        t["uncached_input_tokens"] = t["input_tokens"] = _int(u)
    elif only == "cache_read":
        t["cache_read_tokens"] = t["input_tokens"] = _int(cr)
    else:
        v = _int(_sum(r["cw5" if only == "cache_write_5m" else "cw1"] for r in rows) or zero)
        t["cache_write_tokens"] = t["input_tokens"] = v
    return t


def cost_amounts(rows: list[dict], source: str, only: Optional[str] = None) -> dict:
    amt = _sum(r["amount"] for r in rows)
    lst = _sum(r["list"] for r in rows)
    return {"amount_usd": float(amt or 0), "list_amount_usd": None if lst is None else float(lst)}


def _null_tok() -> dict:
    return {k: None for k in ("input_tokens", "uncached_input_tokens", "cache_write_tokens", "cache_read_tokens",
                              "output_tokens", "requests", "web_search_requests")}


def _assemble(*, status: dict, frm: date, to: date, bucket: str, group_by: Optional[str], dim: Optional[str],
              facts: list[dict], measure: Callable[[list[dict], Optional[str]], dict], null_measure: dict,
              token_split: bool = False) -> dict:
    head = {"source": status, "window": {"from": frm.isoformat(), "to": to.isoformat(), "days": (to - frm).days + 1},
            "bucket": bucket, "group_by": group_by}
    if status["status"] == "unavailable":
        return {**head, "totals": null_measure, "series": [], "groups": []}
    if token_split:
        by_b: dict[date, list[dict]] = {}
        for f in facts:
            by_b.setdefault(_bucket_start(f["day"], bucket), []).append(f)
        series = [{"bucket_start": b.isoformat(), "key": t, **measure(by_b[b], t)} for b in sorted(by_b) for t in TOKEN_TYPES]
        groups = [{"key": t, "label": t, **measure(facts, t)} for t in TOKEN_TYPES] if facts else []
        return {**head, "totals": measure(facts, None), "series": series, "groups": groups}
    cells: dict[tuple[date, Optional[str]], list[dict]] = {}
    keys: dict[Optional[str], list[dict]] = {}
    for f in facts:
        k = f["dims"].get(dim) if dim else None
        cells.setdefault((_bucket_start(f["day"], bucket), k), []).append(f)
        keys.setdefault(k, []).append(f)
    series = [{"bucket_start": b.isoformat(), "key": k, **measure(cells[(b, k)], None)}
              for (b, k) in sorted(cells, key=lambda c: (c[0], c[1] or ""))]
    groups = ([{"key": k, "label": k if k is not None else "(sem valor)", **measure(rs, None)}
               for k, rs in sorted(keys.items(), key=lambda kv: kv[0] or "")] if dim else [])
    return {**head, "totals": measure(facts, None), "series": series, "groups": groups}


def usage_report(db: Any, *, source: str, status: dict, frm: date, to: date, bucket: str, group_by: Optional[str],
                 filters: dict[str, Optional[str]]) -> dict:
    flt = check_filters(source, filters)
    dim = check_group_by(source, group_by, USAGE_GROUPS)
    facts = [] if status["status"] == "unavailable" else usage_facts(db, source, frm, to, flt)
    return _assemble(status=status, frm=frm, to=to, bucket=bucket, group_by=group_by, dim=dim, facts=facts,
                     measure=lambda rs, only: usage_tok(rs, source, only), null_measure=_null_tok(),
                     token_split=(dim == "token_type"))


def cost_report(db: Any, *, source: str, status: dict, frm: date, to: date, bucket: str, group_by: Optional[str],
                filters: dict[str, Optional[str]]) -> dict:
    flt = check_filters(source, filters)
    dim = check_group_by(source, group_by, COST_GROUPS)
    facts = [] if status["status"] == "unavailable" else cost_facts(db, source, frm, to, flt)
    return _assemble(status=status, frm=frm, to=to, bucket=bucket, group_by=group_by, dim=dim, facts=facts,
                     measure=lambda rs, only: cost_amounts(rs, source), null_measure={"amount_usd": None, "list_amount_usd": None})


def spend_report(db: Any, *, source: str, status: dict, month: Optional[str], today: date) -> dict:
    first, last = parse_month(month)
    head = {"source": status, "month": month, "spend_limit": None, "credit_balance": None,
            "unavailable_fields": list(UNAVAILABLE_FIELDS)}
    if status["status"] == "unavailable":
        return {**head, "derived_spend_usd": None, "is_final": False, "daily": []}
    facts = cost_facts(db, source, first, last, {})
    per_day: dict[date, Decimal] = {}
    for f in facts:
        if f["amount"] is not None:
            per_day[f["day"]] = per_day.get(f["day"], Decimal(0)) + f["amount"]
    total = sum(per_day.values(), Decimal(0)) if per_day else None
    final = bool(facts) and all(f["final"] for f in facts) if source == "anthropic" else last < today
    return {**head, "derived_spend_usd": None if total is None else float(total), "is_final": final,
            "daily": [{"day": d.isoformat(), "amount_usd": float(a)} for d, a in sorted(per_day.items())]}


def rate_limits_report(db: Any, *, status: dict) -> dict:
    head = {"source": status, "peak_pct": None}
    if status["status"] == "unavailable":
        return {**head, "limits": []}
    rows = _all_rows(db, "ai_anthropic_rate_limits", "scope,workspace_id_key,model_group,metric,limit_value",
                     ("scope", "workspace_id_key", "model_group", "metric"), lambda q: q)
    return {**head, "limits": [{"scope": r["scope"], "workspace_id": _null(r["workspace_id_key"]),
                                "model_group": r["model_group"], "metric": r["metric"], "limit": r["limit_value"]}
                               for r in rows]}


# ── /deliveries ──────────────────────────────────────────────────────────────────────────────────────────
def _median(values: list) -> Optional[float]:
    got = [float(v) for v in values if v is not None]
    return statistics.median(got) if got else None


def _mean(values: list) -> Optional[float]:
    got = [float(v) for v in values if v is not None]
    return statistics.fmean(got) if got else None


def _wall(r: dict) -> Optional[float]:
    v = r.get("wall_s_measured")
    return float(v) if v is not None else (None if r.get("wall_s_self_reported") is None else float(r["wall_s_self_reported"]))


def _delivery_metrics(rs: list[dict]) -> dict:
    fp = [None if r.get("first_pass") is None else (1.0 if r["first_pass"] else 0.0) for r in rs]
    return {"n": len(rs), "small_sample": len(rs) < 10, "q_weighted_mean": _mean([r.get("q_weighted") for r in rs]),
            "first_pass_rate": _mean(fp), "cost_usd_median": _median([r.get("cost_usd") for r in rs]),
            "cost_is_estimate": True, "wall_s_median": _median([_wall(r) for r in rs]),
            "duration_min_median": _median([r.get("duration_minutes") for r in rs])}


def deliveries_report(db: Any, *, status: dict, frm: date, to: date, model: Optional[str], agent: Optional[str],
                      ambiente: Optional[str]) -> dict:
    head = {"source": status, "window": {"from": frm.isoformat(), "to": to.isoformat(), "days": (to - frm).days + 1},
            "bucket": "week"}
    if status["status"] == "unavailable":
        return {**head, "compare": [], "trend": [], "rows": []}
    lo, hi = _day_range(frm, to)
    cols = ("line_hash,slug,agent,model,ts,q_weighted,first_pass,rework_commits,tokens,cost_usd,wall_s_measured,"
            "wall_s_self_reported,duration_minutes,outcome,ambiente")

    def apply(q):
        q = q.gte("ts", lo).lt("ts", hi)
        for col, val in (("model", model), ("agent", agent), ("ambiente", ambiente)):
            if val is not None:
                q = q.eq(col, val)
        return q

    rows = _all_rows(db, "dev_deliveries", cols, ("ts", "line_hash"), apply)
    by_model: dict[str, list[dict]] = {}
    by_week: dict[tuple[date, str], list[dict]] = {}
    for r in rows:
        m = r.get("model") or "(desconhecido)"
        by_model.setdefault(m, []).append(r)
        wk = _bucket_start(date.fromisoformat(str(r["ts"])[:10]), "week")
        by_week.setdefault((wk, m), []).append(r)
    return {
        **head,
        "compare": [{"model": m, **_delivery_metrics(rs)} for m, rs in sorted(by_model.items())],
        "trend": [{"week_start": wk.isoformat(), "model": m, **_delivery_metrics(rs)} for (wk, m), rs in sorted(by_week.items())],
        "rows": [{
            "slug": r["slug"], "agent": r["agent"], "model": r.get("model"), "ambiente": r.get("ambiente"), "ts": r["ts"],
            "q_weighted": None if r.get("q_weighted") is None else float(r["q_weighted"]), "first_pass": r.get("first_pass"),
            "rework_commits": r.get("rework_commits"), "tokens": r.get("tokens"),
            "cost_usd": None if r.get("cost_usd") is None else float(r["cost_usd"]), "wall_s": _wall(r),
            "duration_minutes": None if r.get("duration_minutes") is None else float(r["duration_minutes"]),
            "outcome": r.get("outcome"),
        } for r in sorted(rows, key=lambda r: str(r["ts"]), reverse=True)],
    }
