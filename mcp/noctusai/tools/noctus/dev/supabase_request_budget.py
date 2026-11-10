"""`noctus.dev.supabase_request_budget` — measure our Supabase request volume from the project's
OWN edge logs and say ok | warn | critical | unknown.

WHY (2026-11-10). The Free-plan project was Fair-Use restricted (HTTP 402 on every call) after
~620k REST calls/day from our own pollers. Nothing measured request volume, so the first signal was
the 402 (`KB § PATTERNS/backend/polling-request-budget.md`). This is the telemetry leg of that rule
and the sensor of the off-host breaker (`prod_watchdog` runs it every 10 min).

SOURCE. Supabase Management API `GET /v1/projects/{ref}/analytics/endpoints/logs` (ClickHouse SQL over
the unified `logs` table; `iso_timestamp_start/end`, max 24 h; `logs.all` answers 410 Gone) and, for the
usage block, `GET .../analytics/endpoints/usage.api-counts` (hourly request counts per API). The v1 API
exposes NO org egress / quota figure, so the budget is judged on request VOLUME (the thing we control);
`usage.available` says so explicitly.

LGPD. The logs carry user ids, emails and phone numbers inside paths and filters. Every endpoint is
reduced to a SHAPE (`GET /rest/v1/jobs ?id=eq.?&type=eq.?`): filter values, ids and storage object
names become `?`; user agents become a family. No raw value ever reaches the report.

SHAPE. Protocol + Fake + Real + factory (the house seed IO shape) in one stdlib-only module: the
watchdog runs under a bare python with no pip install, so nothing here imports outside the stdlib.
The token comes from env (`SUPABASE_ACCESS_TOKEN`) and is never logged, echoed or put in a repr.

Verdict (thresholds are per-day projections, env-overridable):
  critical  projected total > 250k · a single shape > 50k · ANY 402 in the window
  warn      projected total > 100k · a single shape > 15k
  unknown   the logs could not be read (never green, never red)
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Protocol

DEFAULT_PROJECT_REF = "nyplttplcoyiiqjrvtiw"
MGMT_BASE = "https://api.supabase.com"
TOKEN_ENV = "SUPABASE_ACCESS_TOKEN"
PROJECT_REF_ENV = "SUPABASE_PROJECT_REF"
MAX_WINDOW_HOURS = 24.0
_UA = "noctusai-request-budget/1.0"

DEFAULTS: dict[str, float] = {
    "SUPABASE_BUDGET_WARN_TOTAL_PER_DAY": 100_000,
    "SUPABASE_BUDGET_CRIT_TOTAL_PER_DAY": 250_000,
    "SUPABASE_BUDGET_WARN_SHAPE_PER_DAY": 15_000,
    "SUPABASE_BUDGET_CRIT_SHAPE_PER_DAY": 50_000,
}

SQL_SHAPES = (
    "select log_attributes['request.method'] m, log_attributes['request.path'] p, "
    "log_attributes['request.search'] s, count() calls from logs where source='edge_logs' "
    "group by m, p, s order by calls desc limit 3000"
)
SQL_STATUS_UA = (
    "select log_attributes['request.headers.user_agent'] ua, "
    "log_attributes['response.status_code'] status, count() calls from logs "
    "where source='edge_logs' group by ua, status order by calls desc limit 1000"
)
USAGE_NOTE_NO_EGRESS = (
    "the Supabase Management API v1 exposes request counts only - no org egress or quota figure; "
    "the budget is judged on request volume"
)


class LogsError(Exception):
    """The logs could not be read. `transient` = worth retrying next run."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


class LogsSource(Protocol):
    def query_logs(self, sql: str, start: str, end: str) -> list[dict]: ...

    def usage_counts(self, interval: str = "1day") -> list[dict]: ...


# ── normalisation (LGPD: no raw value survives) ──────────────────────────────
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_EMAIL = re.compile(r"[^\s/,()&=?]+@[^\s/,()&=?]+")
_LONG_DIGITS = re.compile(r"\d{6,}")
_OPS = ("eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is", "in", "cs", "cd", "ov",
        "sl", "sr", "nxl", "nxr", "adj", "fts", "plfts", "phfts", "wfts", "match", "imatch", "isdistinct")
_OP_ALT = "|".join(_OPS)
_FILTER_VALUE = re.compile(rf"^(?P<neg>not\.)?(?P<op>{_OP_ALT})\.(?P<rest>.*)$", re.S)
_INLINE_FILTER = re.compile(rf"\.(?P<op>{_OP_ALT})\.(?:\([^)]*\)|[^,)]*)")
_KEEP_VERBATIM = frozenset({"select", "order", "columns", "on_conflict", "returning", "count"})
_STORAGE_MODES = frozenset({"sign", "public", "authenticated", "upload", "info"})


def _scrub(text: str) -> str:
    """Belt and braces: whatever survived the structural rules, no uuid/email/long number remains."""
    text = _UUID.sub("?", text)
    text = _EMAIL.sub("?", text)
    return _LONG_DIGITS.sub("?", text)


def _norm_filter_value(value: str) -> str:
    m = _FILTER_VALUE.match(value)
    if not m:
        return "?"
    neg = m.group("neg") or ""
    op = m.group("op")
    return f"{neg}{op}." + ("(?)" if op == "in" else "?")


def _norm_inline(value: str) -> str:
    return _INLINE_FILTER.sub(lambda m: f".{m.group('op')}." + ("(?)" if m.group("op") == "in" else "?"), value)


def normalize_search(search: Optional[str]) -> str:
    """PostgREST query string -> shape: keys kept (sorted), every filter value -> `?`."""
    if not search:
        return ""
    raw = urllib.parse.unquote(search.lstrip("?"))
    parts: list[str] = []
    for chunk in raw.split("&"):
        if not chunk:
            continue
        key, sep, val = chunk.partition("=")
        if not sep:
            parts.append(_scrub(key))
            continue
        if key in _KEEP_VERBATIM:
            out = _scrub(val)
        elif key == "limit":
            out = val if val.isdigit() else "?"
        elif key == "offset":
            out = "?"
        elif key in ("or", "and", "not.or", "not.and"):
            out = _norm_inline(val)
        else:
            out = _norm_filter_value(val)
        parts.append(f"{_scrub(key)}={_scrub(out)}")
    return "&".join(sorted(parts))


def _norm_segment(seg: str) -> str:
    if _UUID.fullmatch(seg) or "@" in seg or seg.isdigit() or re.fullmatch(r"[0-9a-fA-F]{16,}", seg):
        return "?"
    return _scrub(seg)


def normalize_path(path: Optional[str]) -> str:
    """Request path -> shape: ids, emails and storage object names -> `?`."""
    segs = (urllib.parse.unquote(path or "").split("?", 1)[0]).split("/")
    if len(segs) > 5 and segs[1:4] == ["storage", "v1", "object"]:
        keep = 6 if segs[4] in _STORAGE_MODES else 5  # '' storage v1 object [mode] bucket
        head = [_norm_segment(s) for s in segs[:keep]]
        return "/".join(head + (["?"] if len(segs) > keep else []))
    return "/".join(_norm_segment(s) for s in segs) or "/"


def ua_family(ua: Optional[str]) -> str:
    """User agent -> family (no version, no free text)."""
    text = (ua or "").strip().lower()
    if not text:
        return "unknown"
    if text.startswith("mozilla") or "applewebkit" in text:
        return "browser"
    token = re.split(r"[/\s;(]", text, maxsplit=1)[0]
    return token if re.fullmatch(r"[a-z0-9._-]{1,32}", token) else "other"


def shape_key(method: Any, path: Any, search: Any) -> str:
    s = normalize_search(search if isinstance(search, str) else None)
    base = f"{str(method or '?').upper()[:8]} {normalize_path(path if isinstance(path, str) else None)}"
    return f"{base} ?{s}" if s else base


# ── sources: Fake + Real + factory ───────────────────────────────────────────
class FakeLogsSource:
    """Deterministic source for tests: rows keyed by which query is asked."""

    def __init__(self, *, shape_rows=None, status_rows=None, usage_rows=None,
                 error: Optional[LogsError] = None) -> None:
        self.shape_rows = list(shape_rows or [])
        self.status_rows = list(status_rows or [])
        self.usage_rows = list(usage_rows or [])
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def query_logs(self, sql: str, start: str, end: str) -> list[dict]:
        self.calls.append((sql, start, end))
        if self.error:
            raise self.error
        return list(self.shape_rows if "request.search" in sql else self.status_rows)

    def usage_counts(self, interval: str = "1day") -> list[dict]:
        if self.error:
            raise self.error
        return list(self.usage_rows)


class RealLogsSource:
    """Management API client (stdlib urllib, read-only GETs). The token is never repr'd or raised."""

    def __init__(self, *, token: str, project_ref: str = DEFAULT_PROJECT_REF,
                 opener: Callable[..., Any] = urllib.request.urlopen, timeout: float = 60.0) -> None:
        self._token = token
        self._ref = project_ref
        self._opener = opener
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"RealLogsSource(project_ref={self._ref!r}, token=<redacted>)"

    def _get(self, endpoint: str, params: Mapping[str, str]) -> list[dict]:
        url = f"{MGMT_BASE}/v1/projects/{self._ref}/analytics/endpoints/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._token}", "User-Agent": _UA})
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise LogsError(f"HTTP {exc.code} {exc.reason}", transient=exc.code in (429, 502, 503, 504)) from None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise LogsError(f"network error: {type(exc).__name__}", transient=True) from None
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            raise LogsError("unparseable response from the logs endpoint") from None
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            raise LogsError(f"logs endpoint error: {(err if isinstance(err, str) else json.dumps(err))[:160]}")
        result = body.get("result") if isinstance(body, dict) else None
        return [r for r in (result or []) if isinstance(r, dict)]

    def query_logs(self, sql: str, start: str, end: str) -> list[dict]:
        return self._get("logs", {"sql": sql, "iso_timestamp_start": start, "iso_timestamp_end": end})

    def usage_counts(self, interval: str = "1day") -> list[dict]:
        return self._get("usage.api-counts", {"interval": interval})


def make_source(env: Optional[Mapping[str, str]] = None) -> Optional[RealLogsSource]:
    """Real source from env, or None when no token is configured."""
    env = os.environ if env is None else env
    token = (env.get(TOKEN_ENV) or "").strip()
    if not token:
        return None
    return RealLogsSource(token=token, project_ref=(env.get(PROJECT_REF_ENV) or "").strip() or DEFAULT_PROJECT_REF)


# ── evaluation ───────────────────────────────────────────────────────────────
def thresholds(env: Mapping[str, str]) -> dict[str, float]:
    out = dict(DEFAULTS)
    for name in DEFAULTS:
        raw = (env.get(name) or "").strip()
        if raw:
            try:
                out[name] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{name}={raw!r} is not a number") from exc
    return out


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _window(window_hours: float, now: Optional[str], start: Optional[str], end: Optional[str]):
    if start or end:
        if not (start and end):
            raise ValueError("start and end must be given together")
        s, e = _parse_ts(start), _parse_ts(end)
        hours = (e - s).total_seconds() / 3600
        if hours <= 0:
            raise ValueError("end must be after start")
        if hours > MAX_WINDOW_HOURS:
            raise ValueError(f"window is {hours:.1f} h; the logs endpoint allows at most {MAX_WINDOW_HOURS:g} h")
        return s, e, hours
    if window_hours <= 0:
        raise ValueError("window_hours must be > 0")
    hours = min(float(window_hours), MAX_WINDOW_HOURS)
    e = _parse_ts(now) if now else datetime.now(timezone.utc)
    return e - timedelta(hours=hours), e, hours


def _usage_block(source: LogsSource) -> dict:
    try:
        rows = source.usage_counts("1day")
    except LogsError as exc:
        return {"available": False, "note": f"usage read failed ({exc}); {USAGE_NOTE_NO_EGRESS}"}
    if not rows:
        return {"available": False, "note": USAGE_NOTE_NO_EGRESS}
    tot = {k: sum(_int(r.get(k)) for r in rows) for k in
           ("total_rest_requests", "total_auth_requests", "total_storage_requests", "total_realtime_requests")}
    return {"available": True, "rest_requests_24h": tot["total_rest_requests"],
            "auth_requests_24h": tot["total_auth_requests"], "storage_requests_24h": tot["total_storage_requests"],
            "realtime_requests_24h": tot["total_realtime_requests"], "note": USAGE_NOTE_NO_EGRESS}


def evaluate(source: LogsSource, *, window_hours: float = 1.0, now: Optional[str] = None,
             start: Optional[str] = None, end: Optional[str] = None,
             th: Optional[Mapping[str, float]] = None, top_n: int = 10) -> dict:
    """Read the window, reduce to shapes, judge against the thresholds. Never raises on a read failure."""
    th = dict(th) if th is not None else dict(DEFAULTS)
    s_dt, e_dt, hours = _window(window_hours, now, start, end)
    s_iso, e_iso = _iso(s_dt), _iso(e_dt)
    per_day = 24.0 / hours
    base = {"window_hours": round(hours, 3), "start": s_iso, "end": e_iso, "thresholds": th}
    try:
        status_rows = source.query_logs(SQL_STATUS_UA, s_iso, e_iso)
        shape_rows = source.query_logs(SQL_SHAPES, s_iso, e_iso)
    except LogsError as exc:
        return {**base, "ok": False, "verdict": "unknown", "error": str(exc), "transient": exc.transient,
                "reasons": [f"could not read the Supabase logs: {exc}"]}

    ua_totals: Counter = Counter()
    total = n402 = n4xx = 0
    for r in status_rows:
        c, st = _int(r.get("calls")), _int(r.get("status"))
        total += c
        ua_totals[ua_family(r.get("ua"))] += c
        if st == 402:
            n402 += c
        if 400 <= st < 500:
            n4xx += c
    shapes: Counter = Counter()
    for r in shape_rows:
        shapes[shape_key(r.get("m"), r.get("p"), r.get("s"))] += _int(r.get("calls"))
    if not status_rows:
        total = sum(shapes.values())

    projected = int(round(total * per_day))
    shape_sum = sum(shapes.values())
    top = [{"shape": k, "calls": c, "projected_per_day": int(round(c * per_day)),
            "pct": round(100.0 * c / total, 1) if total else 0.0}
           for k, c in shapes.most_common(max(1, int(top_n)))]

    offenders: list[dict] = []
    level = "ok"
    if n402:
        level = "critical"
        offenders.append({"reason": "http_402", "level": "critical", "calls": n402,
                          "detail": "Supabase answers 402 (Fair Use restriction): every call is being refused"})
    if projected > th["SUPABASE_BUDGET_CRIT_TOTAL_PER_DAY"]:
        level = "critical"
        offenders.append({"reason": "total_projected", "level": "critical", "projected_per_day": projected})
    elif projected > th["SUPABASE_BUDGET_WARN_TOTAL_PER_DAY"]:
        level = level if level == "critical" else "warn"
        offenders.append({"reason": "total_projected", "level": "warn", "projected_per_day": projected})
    for k, c in shapes.most_common():
        p = c * per_day
        if p > th["SUPABASE_BUDGET_CRIT_SHAPE_PER_DAY"]:
            level = "critical"
            offenders.append({"reason": "shape_projected", "level": "critical", "shape": k, "calls": c,
                              "projected_per_day": int(round(p))})
        elif p > th["SUPABASE_BUDGET_WARN_SHAPE_PER_DAY"]:
            level = level if level == "critical" else "warn"
            offenders.append({"reason": "shape_projected", "level": "warn", "shape": k, "calls": c,
                              "projected_per_day": int(round(p))})
        else:
            break  # most_common is sorted: nothing below can exceed
    offenders.sort(key=lambda o: 0 if o["level"] == "critical" else 1)

    reasons = []
    for o in offenders:
        if o["reason"] == "http_402":
            reasons.append(f"{o['calls']} calls answered 402 in the window (project restricted)")
        elif o["reason"] == "total_projected":
            reasons.append(f"projected {o['projected_per_day']:,} calls/day ({o['level']})")
        else:
            reasons.append(f"{o['shape']}: {o['projected_per_day']:,}/day ({o['level']})")
    return {
        **base, "ok": True, "verdict": level, "reasons": reasons,
        "total_calls": total, "projected_per_day": projected,
        "status_402": n402, "status_4xx": n4xx, "restricted": n402 > 0,
        "top_shapes": top, "offenders": offenders,
        "by_user_agent": [{"family": f, "calls": c} for f, c in ua_totals.most_common(10)],
        "coverage_pct": round(100.0 * shape_sum / total, 1) if total else 100.0,
        "usage": _usage_block(source),
    }


def supabase_request_budget(
    *, window_hours: float = 1.0, start: Optional[str] = None, end: Optional[str] = None,
    top_n: int = 10, source: Optional[LogsSource] = None, env: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Tool core: build the real source from env (or take an injected one) and evaluate."""
    env = os.environ if env is None else env
    src = source if source is not None else make_source(env)
    if src is None:
        return {"ok": False, "status": "not_configured", "verdict": "unknown",
                "error": f"{TOKEN_ENV} is not set (a Supabase personal access token, read-only use)"}
    try:
        rep = evaluate(src, window_hours=window_hours, start=start, end=end, th=thresholds(env), top_n=top_n)
    except ValueError as exc:
        return {"ok": False, "status": "error", "verdict": "unknown", "error": str(exc)}
    return {"status": rep["verdict"], **rep}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.supabase_request_budget",
        description=(
            "Measure Supabase request volume from the project's own edge logs (Management API "
            "analytics logs endpoint) and return ok|warn|critical|unknown: total + projected calls/day, top "
            "endpoint SHAPES (method + path + query shape; ids/emails/filter values replaced by ?), user-agent "
            "families, 4xx/402 counts, usage block. critical = projected >250k/day, a shape >50k/day or any "
            "402; warn = >100k/day or a shape >15k/day (env-overridable). window_hours default 1, max 24; or "
            "start+end ISO. Needs SUPABASE_ACCESS_TOKEN in env. READ-ONLY. prod_watchdog runs it every 10 "
            "min and trips the fleet breaker on critical. KB § PATTERNS/backend/polling-request-budget.md"
        ),
    )
    def _supabase_request_budget(window_hours: float = 1.0, start: Optional[str] = None,
                                 end: Optional[str] = None, top_n: int = 10) -> dict:
        return supabase_request_budget(window_hours=window_hours, start=start, end=end, top_n=top_n)


__all__ = ["DEFAULT_PROJECT_REF", "FakeLogsSource", "LogsError", "LogsSource", "RealLogsSource", "evaluate",
           "make_source", "normalize_path", "normalize_search", "register", "shape_key",
           "supabase_request_budget", "thresholds", "ua_family"]
