"""`noctus.dev.latency_report` — are a product's server-side responses inside budget?

Fast responses are mandatory (owner, 2026-10-22). The seed `RequestTimingMiddleware`
logs one `req_timing method= route= status= dur_ms=` line per request for EVERY
product; this tool reads a product's recent container logs over the existing VPS
log plumbing and reports p50/p95/count per ROUTE TEMPLATE against the budgets in
`deploy/fleet/latency-budgets.json` (the single place budgets live).

Verdict: `ok | over_budget | inconclusive`. No parsable samples (old image without
the middleware, quiet product, log window too short) is `inconclusive` — NEVER ok.
Routes under `min_samples` are listed as `thin` and cannot make a verdict ok on
their own: if EVERY route is thin the verdict is `inconclusive`.

KB § PATTERNS/backend/request-path-latency.md · skill noc-fast-responses
"""
from __future__ import annotations

import fnmatch
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

from . import vps as _vps

REPO_ROOT = Path(__file__).resolve().parents[5]
BUDGETS_PATH = REPO_ROOT / "deploy" / "fleet" / "latency-budgets.json"

_LINE = re.compile(
    r"req_timing method=(?P<method>[A-Z]+) route=(?P<route>\S+) "
    r"status=(?P<status>\d+) dur_ms=(?P<dur>\d+(?:\.\d+)?)"
)


# Optional concurrency fields appended AFTER dur_ms by the seed middleware (2026-10-23). Old lines
# lack them; absent => omitted from the report, never 0.
CONC_FIELDS = ("inflight", "inflight_peak", "blk_n", "blk_ms", "blkq_ms", "parq_ms", "lag_ms", "tp_busy", "tp_wait")
_EXTRA = re.compile(r"\b(" + "|".join(CONC_FIELDS) + r")=(\d+(?:\.\d+)?)")


def load_budgets(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or BUDGETS_PATH).read_text())


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    out = []
    for ln in lines:
        m = _LINE.search(ln)
        if m:
            row = {"method": m["method"], "route": m["route"],
                   "status": int(m["status"]), "dur_ms": float(m["dur"])}
            for k, v in _EXTRA.findall(ln[m.end():]):
                row[k] = float(v)
            out.append(row)
    return out


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (deterministic, no interpolation)."""
    s = sorted(values)
    return s[max(0, math.ceil(pct / 100.0 * len(s)) - 1)]


def _matches(route: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(route, p) for p in patterns)


def classify(method: str, route: str, budgets: dict[str, Any]) -> tuple[str, int, str | None]:
    """(class, p95 budget ms, override reason). Overrides win; then shell; then method."""
    for ov in budgets.get("overrides", []):
        if ov["route"] == route and ov.get("method", method) == method:
            return "override", int(ov["p95_ms"]), ov["reason"]
    cls = "shell" if _matches(route, budgets.get("shell_routes", [])) else (
        "read" if method in ("GET", "HEAD") else "write")
    return cls, int(budgets["budgets_p95_ms"][cls]), None


def evaluate(samples: list[dict[str, Any]], budgets: dict[str, Any]) -> dict[str, Any]:
    """Pure: samples + budgets -> verdict payload."""
    min_n = int(budgets.get("min_samples", 5))
    ignore = budgets.get("ignore_routes", [])
    groups: dict[tuple[str, str], list[float]] = {}
    conc: dict[tuple[str, str], dict[str, list[float]]] = {}
    for s in samples:
        if _matches(s["route"], ignore):
            continue
        key = (s["method"], s["route"])
        groups.setdefault(key, []).append(s["dur_ms"])
        for f in CONC_FIELDS:
            if f in s:
                conc.setdefault(key, {}).setdefault(f, []).append(s[f])
    routes, over, thin = [], [], []
    for (method, route), durs in sorted(groups.items()):
        cls, budget, reason = classify(method, route, budgets)
        row = {"method": method, "route": route, "class": cls, "count": len(durs),
               "p50_ms": round(percentile(durs, 50), 1), "p95_ms": round(percentile(durs, 95), 1),
               "budget_p95_ms": budget}
        if reason:
            row["override_reason"] = reason
        if (method, route) in conc:
            row["concurrency"] = {f: {"p50": round(percentile(v, 50), 1), "p95": round(percentile(v, 95), 1),
                                      "n": len(v)} for f, v in conc[(method, route)].items()}
        if len(durs) < min_n:
            row["thin"] = True
            thin.append(row)
        elif row["p95_ms"] > budget:
            row["over_budget"] = True
            over.append(row)
        routes.append(row)
    measured = len(routes) - len(thin)
    if over:
        status = "over_budget"
    elif measured == 0:
        status = "inconclusive"
    else:
        status = "ok"
    return {"status": status, "samples": sum(len(v) for v in groups.values()),
            "routes": routes, "over_budget": over, "thin": [(r["method"], r["route"]) for r in thin]}


def latency_report(product: str, lines: int = 5000, ssh_host: str = _vps.DEFAULT_HOST,
                   budgets_path: str | None = None,
                   run_remote: Callable | None = None) -> dict[str, Any]:
    if not product:
        return {"ok": False, "status": "error", "exit_code": 1, "error": "product required"}
    try:
        budgets = load_budgets(Path(budgets_path) if budgets_path else None)
    except (OSError, ValueError, KeyError) as exc:
        return {"ok": False, "status": "error", "exit_code": 1, "error": f"budgets unreadable: {exc}"}
    container = f"{_vps.CONTAINER_PREFIX}{product}"
    got = _vps.logs(container, lines=lines, ssh_host=ssh_host, grep="req_timing", run_remote=run_remote)
    if not got.get("ok"):
        return {"ok": False, "status": "inconclusive", "exit_code": 1, "product": product,
                "error": got.get("error", "log fetch failed")}
    samples = parse_lines(got["lines"])
    rep = evaluate(samples, budgets)
    rep.update({"ok": rep["status"] == "ok", "exit_code": 0 if rep["status"] == "ok" else 1,
                "product": product, "container": container, "log_lines_scanned": len(got["lines"])})
    if rep["status"] == "inconclusive":
        rep["hint"] = ("no measurable routes: image may predate RequestTimingMiddleware, the product is "
                       "quiet, or lines= is too small. Browse the product, then re-run — never read as ok.")
    return rep


def register(server) -> None:
    @server.tool(
        name="noctus.dev.latency_report",
        description=(
            "Fast-responses gate. Reads a product's recent container logs (req_timing lines emitted by the "
            "seed RequestTimingMiddleware) over the VPS log plumbing and reports p50/p95/count per route "
            "template vs the budgets in deploy/fleet/latency-budgets.json (shell/me 150, reads 300, writes "
            "500 ms p95; per-route overrides carry a reason). Verdict ok | over_budget | inconclusive "
            "(no data is inconclusive, never ok). Run after every deploy_image. Read-only. "
            "KB § PATTERNS/backend/request-path-latency.md."
        ),
    )
    def _latency_report(product: str, lines: int = 5000, ssh_host: str = _vps.DEFAULT_HOST) -> dict:
        return latency_report(product, lines=lines, ssh_host=ssh_host)


__all__ = ["latency_report", "evaluate", "parse_lines", "classify", "percentile", "load_budgets", "register"]
