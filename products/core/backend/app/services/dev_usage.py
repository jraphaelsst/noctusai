"""Reads + maths for the "Uso & Custos" dev-side endpoints (``public.dev_telemetry_*``, core 097).

Our own development work: Claude Code API-list-price equivalents (NOT an invoice, never product
credits), OS samples from the hardware-admission sampler, heavy-job admissions and phase marks.
Written by ``noctus.dev.usage_eval``; read here ONCE per table per request (paged -- PostgREST caps
a response at 1 000 rows) and aggregated in Python; no N+1.

The job/phase maths mirror ``mcp/noctusai/tools/noctus/dev/usage_eval.py`` (``window_report`` /
``_COMPARE_KEYS``): mean = sum/n rounded to 2, failed = ``exit_code not in (None, 0)``, ``ran`` /
``not_admitted`` split by ``event``. Unmeasured is ``None``, never 0. Counts only, no text.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from fastapi import HTTPException

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.paging import PagerOverflowError
from noctusai_lib.primitives.parsing import parse_iso_or_400 as _parse_iso

DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 400
MAX_SERIES_POINTS = 720
MAX_JOBS = 500
BASELINE_PHASE = "build"
_MAX_PAGES = 200

_CLAUDE_COLS = (
    "host,bucket,session_id,agent_id,project,model,requests,input_tokens,output_tokens,thinking_tokens,"
    "cache_read_tokens,cache_write_tokens,cost_usd,prompt_chars,output_chars,tool_result_chars,tool_calls"
)
_OS_COLS = "host,ts,phase,overloaded,busy_slots,cpu_idle_pct,reclaimable_mb,swapout_per_s,load_1m,claude_sessions"
_JOB_COLS = (
    "host,ts,job,kind,target,event,phase,admitted,waited_s,duration_s,children_peak_rss_mb,exit_code,metrics"
)
_MARK_COLS = "host,ts,kind,label,payload"

_COUNTERS = (
    "requests", "input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens",
    "cache_write_tokens", "prompt_chars", "output_chars", "tool_result_chars", "tool_calls",
)


class DevWindow:
    def __init__(self, start: datetime, end: datetime) -> None:
        self.start, self.end = start, end
        self.hours = max((end - start).total_seconds() / 3600.0, 1e-9)

    def as_dict(self) -> dict[str, Any]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat(), "hours": round(self.hours, 3)}


def resolve_window(from_: Optional[str], to: Optional[str]) -> DevWindow:
    now = datetime.now(tz=timezone.utc)
    start = _parse_iso(from_) or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = _parse_iso(to) or now
    if end < start:
        raise HTTPException(status_code=400, detail="'to' precede 'from'")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise HTTPException(status_code=400, detail=f"Janela maior que {MAX_WINDOW_DAYS} dias")
    return DevWindow(start, end)


def _read(db: Any, table: str, cols: str, pk: tuple[str, ...], win: DevWindow) -> list[dict]:
    """Every row of ``table`` in the window (``pk[0]`` is its time column) -- paged, bounded.

    These tables have composite primary keys and no ``id``: ordering by the whole key keeps offset
    paging stable, and a joined ``_pk`` feeds the pager's progress guard. Overflow -> 400, never a
    silent cap."""
    ts_col = pk[0]

    def page(lo: int, hi: int) -> Any:
        q = (
            db.table(table).select(cols)
            .gte(ts_col, win.start.isoformat()).lte(ts_col, win.end.isoformat())
        )
        for c in pk:
            q = q.order(c)
        rows = q.range(lo, hi).execute().data or []
        return [{**r, "_pk": "|".join(str(r.get(c)) for c in pk)} for r in rows]

    try:
        return list(
            iter_paged_rows(page, max_pages=_MAX_PAGES, id_key="_pk", label=table, overflow_error=PagerOverflowError)
        )
    except PagerOverflowError:
        raise HTTPException(status_code=400, detail="Janela grande demais; reduza o período")


def freshness(db: Any, table: str, col: str = "synced_at") -> Optional[str]:
    rows = db.table(table).select(col).order(col, desc=True).limit(1).execute().data or []
    return str(rows[0][col]) if rows and rows[0].get(col) is not None else None


def _f(v: Any) -> Optional[float]:
    return None if v is None else float(v)


def _avg(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 2) if xs else None


def _nums(rows: Iterable[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) is not None]


def _distinct(rows: Iterable[dict], key: str) -> list[str]:
    return sorted({r[key] for r in rows if r.get(key)})


# ── dev (Claude Code) ────────────────────────────────────────────────────────

def _totals(rows: list[dict], hours: float) -> dict[str, Any]:
    """Counters summed; every value ``None`` when there are no rows (unmeasured, not 0)."""
    if not rows:
        return {**dict.fromkeys(_COUNTERS), "cost_usd": None, "cost_usd_per_hour": None}
    out: dict[str, Any] = {k: sum(int(r.get(k) or 0) for r in rows) for k in _COUNTERS}
    cost = sum(float(r.get("cost_usd") or 0) for r in rows)
    out["cost_usd"] = round(cost, 6)
    out["cost_usd_per_hour"] = round(cost / hours, 4)
    return out


def _by(rows: list[dict], keyf: Callable[[dict], Any]) -> dict[Any, list[dict]]:
    groups: dict[Any, list[dict]] = defaultdict(list)
    for r in rows:
        groups[keyf(r)].append(r)
    return groups


def _cost_desc(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: i["cost_usd"] or 0, reverse=True)


def dev_report(db: Any, win: DevWindow, *, host: Optional[str], project: Optional[str],
               session_id: Optional[str], agent_id: Optional[str], model: Optional[str]) -> dict[str, Any]:
    all_rows = _read(db, "dev_telemetry_claude", _CLAUDE_COLS, ("bucket", "host", "session_id", "agent_id", "model"), win)
    rows = [
        r for r in all_rows
        if (not host or r["host"] == host)
        and (not project or r["project"] == project)
        and (not session_id or r["session_id"] == session_id)
        and (not model or r["model"] == model)
        and (not agent_id or (r.get("agent_id") or "") == ("" if agent_id == "main" else agent_id))
    ]
    h = win.hours
    per_session = []
    for sid, grp in _by(rows, lambda r: r["session_id"]).items():
        buckets = sorted(str(r["bucket"]) for r in grp)
        per_session.append({
            "session_id": sid,
            "project": grp[0]["project"],
            "host": grp[0]["host"],
            "subagents": len({r["agent_id"] for r in grp if r.get("agent_id")}),
            "first": buckets[0], "last": buckets[-1],
            **_totals(grp, h),
        })
    per_agent = [
        {"session_id": sid, "agent_id": aid, **_totals(grp, h)}
        for (sid, aid), grp in _by(rows, lambda r: (r["session_id"], r.get("agent_id") or "")).items()
    ]
    per_model = [{"model": m, **_totals(grp, h)} for m, grp in _by(rows, lambda r: r["model"]).items()]
    series = []
    for hour, grp in sorted(_by(rows, lambda r: _hour(r["bucket"])).items()):
        series.append({
            "hour": hour,
            "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in grp), 6),
            "input_tokens": sum(int(r.get("input_tokens") or 0) for r in grp),
            "output_tokens": sum(int(r.get("output_tokens") or 0) for r in grp),
            "requests": sum(int(r.get("requests") or 0) for r in grp),
        })
    return {
        "window": win.as_dict(),
        "freshness": {"dev_telemetry_claude": freshness(db, "dev_telemetry_claude")},
        "filters": {"host": host, "project": project, "session_id": session_id, "agent_id": agent_id, "model": model},
        "totals": _totals(rows, h),
        "per_session": _cost_desc(per_session),
        "per_agent": _cost_desc(per_agent),
        "per_model": _cost_desc(per_model),
        "series": series,
        "filters_available": {
            "hosts": _distinct(all_rows, "host"),
            "projects": _distinct(all_rows, "project"),
            "models": _distinct(all_rows, "model"),
        },
    }


def _dt(v: Any) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _hour(v: Any) -> str:
    return _dt(v).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()


# ── machine (OS samples + marks) ─────────────────────────────────────────────

_OS_AVG = ("cpu_idle_pct", "reclaimable_mb", "swapout_per_s", "load_1m", "claude_sessions", "busy_slots")


def machine_report(db: Any, win: DevWindow, *, host: Optional[str], phase: Optional[str]) -> dict[str, Any]:
    all_os = _read(db, "dev_telemetry_os", _OS_COLS, ("ts", "host"), win)
    all_marks = _read(db, "dev_telemetry_marks", _MARK_COLS + ",id", ("ts", "id"), win)
    rows = [r for r in all_os if (not host or r["host"] == host) and (not phase or r.get("phase") == phase)]
    step = max(math.ceil((win.end - win.start).total_seconds() / MAX_SERIES_POINTS), 1)
    origin = win.start.timestamp()

    def slot(r: dict) -> int:
        return int((_dt(r["ts"]).timestamp() - origin) // step)

    series = []
    for idx, grp in sorted(_by(rows, slot).items()):
        point: dict[str, Any] = {"ts": datetime.fromtimestamp(origin + idx * step, tz=timezone.utc).isoformat()}
        phases = [r["phase"] for r in grp if r.get("phase")]
        point["phase"] = phases[-1] if phases else None
        for k in _OS_AVG:
            point[k] = _avg(_nums(grp, k))
        flags = [bool(r["overloaded"]) for r in grp if r.get("overloaded") is not None]
        point["overloaded"] = any(flags) if flags else None
        series.append(point)
    marks = [
        {"ts": str(m["ts"]), "kind": m["kind"], "label": m["label"], "payload": m.get("payload") or {}}
        for m in all_marks if not host or m["host"] == host
    ]
    return {
        "window": win.as_dict(),
        "freshness": {"dev_telemetry_os": freshness(db, "dev_telemetry_os"),
                      "dev_telemetry_marks": freshness(db, "dev_telemetry_marks", "ts")},
        "filters": {"host": host, "phase": phase},
        "series": series,
        "marks": marks,
        "filters_available": {"hosts": _distinct(all_os, "host"), "phases": _distinct(all_os, "phase")},
    }


# ── heavy jobs ───────────────────────────────────────────────────────────────

def _metric(job: dict, key: str) -> Optional[int]:
    v = (job.get("metrics") or {}).get(key)
    return None if v is None else int(v)


def _failed(j: dict) -> bool:
    return j.get("exit_code") not in (None, 0)


def jobs_report(db: Any, win: DevWindow, *, host: Optional[str], phase: Optional[str], kind: Optional[str],
                target: Optional[str], event: Optional[str]) -> dict[str, Any]:
    all_jobs = _read(db, "dev_telemetry_jobs", _JOB_COLS, ("ts", "host", "job", "event"), win)
    os_rows = _read(db, "dev_telemetry_os", "host,ts,phase", ("ts", "host"), win)
    jobs = [
        j for j in all_jobs
        if (not host or j["host"] == host) and (not phase or j.get("phase") == phase)
        and (not kind or j["kind"] == kind) and (not target or j["target"] == target)
        and (not event or j["event"] == event)
    ]
    recent = sorted(jobs, key=lambda j: str(j["ts"]), reverse=True)[:MAX_JOBS]
    spans: dict[Any, list[float]] = defaultdict(list)
    for r in os_rows:
        if (not host or r["host"] == host) and r.get("phase"):
            spans[r["phase"]].append(_dt(r["ts"]).timestamp())
    for j in jobs:
        if j.get("phase"):
            spans[j["phase"]].append(_dt(j["ts"]).timestamp())

    per_phase = []
    for ph, grp in _by(jobs, lambda j: j.get("phase")).items():
        ran = [j for j in grp if j["event"] == "ran"]
        reds = [_metric(j, "false_red_count") for j in grp]
        reds = [x for x in reds if x is not None]
        ts = spans.get(ph) or []
        span_h = (max(ts) - min(ts)) / 3600.0 if len(ts) > 1 else 0.0
        per_phase.append({
            "phase": ph,
            "runs": len(ran),
            "not_admitted": sum(1 for j in grp if j["event"] == "not_admitted"),
            "mean_duration_s": _avg(_nums(ran, "duration_s")),
            "mean_waited_s": _avg(_nums(ran, "waited_s")),
            "max_peak_rss_mb": max(_nums(ran, "children_peak_rss_mb"), default=None),
            "fail_rate": round(sum(1 for j in ran if _failed(j)) / len(ran), 4) if ran else None,
            "false_red_total": sum(reds) if reds else None,
            "jobs_per_hour": round(len(ran) / span_h, 2) if span_h > 0 else None,
        })
    per_phase.sort(key=lambda p: (p["phase"] is None, str(p["phase"])))

    means: dict[tuple, Optional[float]] = {}
    for (kt, ph), grp in _by(
        [j for j in jobs if j["event"] == "ran"], lambda j: (f"{j['kind']}:{j['target']}", j.get("phase"))
    ).items():
        means[(kt, ph)] = _avg(_nums(grp, "duration_s"))
    slowdown = []
    for (kt, ph), mean in sorted(means.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        if ph == BASELINE_PHASE:
            continue
        base = means.get((kt, BASELINE_PHASE))
        slowdown.append({
            "kind_target": kt, "phase": ph, "mean_duration_s": mean,
            "baseline_phase": BASELINE_PHASE, "baseline_mean_s": base,
            "factor": round(mean / base, 2) if mean is not None and base else None,
        })

    return {
        "window": win.as_dict(),
        "freshness": {"dev_telemetry_jobs": freshness(db, "dev_telemetry_jobs")},
        "filters": {"host": host, "phase": phase, "kind": kind, "target": target, "event": event},
        "jobs": [
            {
                "ts": str(j["ts"]), "job": j["job"], "kind": j["kind"], "target": j["target"], "event": j["event"],
                "phase": j.get("phase"), "admitted": j.get("admitted"),
                "waited_s": _f(j.get("waited_s")), "duration_s": _f(j.get("duration_s")),
                "peak_rss_mb": _f(j.get("children_peak_rss_mb")), "exit_code": j.get("exit_code"),
                "false_red_count": _metric(j, "false_red_count"), "real_red_count": _metric(j, "real_red_count"),
            }
            for j in recent
        ],
        "per_phase": per_phase,
        "slowdown": slowdown,
        "filters_available": {
            "hosts": _distinct(all_jobs, "host"), "phases": _distinct(all_jobs, "phase"),
            "kinds": _distinct(all_jobs, "kind"),
        },
    }


# ── fx ───────────────────────────────────────────────────────────────────────

def latest_fx(db: Any) -> dict[str, Any]:
    rows = (
        db.table("fx_rates").select("rate,quote_date,created_at").eq("pair", "USD/BRL")
        .order("quote_date", desc=True).limit(1).execute().data or []
    )
    if not rows:
        return {"usd_brl": None, "date": None, "created_at": None}
    return {"usd_brl": float(rows[0]["rate"]), "date": str(rows[0]["quote_date"]), "created_at": rows[0].get("created_at")}
