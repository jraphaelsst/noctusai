"""`noctus.dev.perf_probe` — SCOPED browser-side performance analysis (the client view).

Server half = `latency_report` (req_timing logs vs budgets). This is the CLIENT half: what a
browser actually experienced — page data-ready time, request waterfalls, duplicate calls, edge vs
app time. SCOPE is the unit everywhere: a product slug (ours) or an external host (third-party).

Capture is a browser snippet (`snippet`) that records ONLY paths + query KEYS + timings into
localStorage['__noc_perf'] (capture contract v1, `perf_assets/capture-append.js`). `ingest` TEMPLATES
every id out of every path and stores only the templated summary — the raw capture is never kept.

Actions: snippet | ingest | report | compare | list.   Verdicts: ok | over_budget | inconclusive.
KB § PATTERNS/common/performance-analysis.md · skill noc-perf-probe
"""
from __future__ import annotations

import fnmatch
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .latency_report import BUDGETS_PATH, REPO_ROOT, classify, load_budgets, percentile

ASSETS = Path(__file__).resolve().parent / "perf_assets"
DEFAULT_STORE = REPO_ROOT / ".noc-perf"
SUMMARY_VERSION = 1

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_NUM = re.compile(r"^\d+$")
_HEX = re.compile(r"^[0-9a-fA-F]{8,}$")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Same-host paths answered by the CDN edge itself (never reach the origin): not app endpoints, so
# never budgeted -- reported as `edge_floor`, the browser<->edge round trip every API call pays too.
EDGE_PATHS = ("/cdn-cgi/*",)


class PerfProbeError(Exception):
    """Named, loud refusal (no silent fallback)."""


# --------------------------------------------------------------------------- templating
def _is_id(seg: str) -> bool:
    if not seg:
        return False
    if _UUID.match(seg) or _NUM.match(seg) or _HEX.match(seg):
        return True
    if len(seg) >= 12 and "." not in seg:
        has_d = any(c.isdigit() for c in seg)
        if has_d and any(c.isalpha() for c in seg):
            return True  # opaque token (slug-with-digits, base64-ish, ULID, nanoid)
    if len(seg) >= 20 and seg.upper() != seg.lower() and seg != seg.lower() and seg != seg.upper() and "-" not in seg:
        return True  # long mixed-case opaque string
    return False


def template_path(path: str) -> str:
    """Template a path (no query): id-looking segments become `{id}`."""
    return "/".join("{id}" if _is_id(s) else s for s in path.split("/"))


def template_where(where: str) -> str:
    """`where` = `/path?k1&k2` (same host) or `host/path?k1` (third party). Keys kept, ids templated."""
    base, sep, query = where.partition("?")
    if base.startswith("/"):
        host, path = "", base
    else:
        host, slash, rest = base.partition("/")
        path = slash + rest
    return host + template_path(path) + (sep + query if sep else "")


def _route_of(endpoint: str) -> str:
    """Path part only, for budget classification (same-host endpoints)."""
    return endpoint.partition("?")[0]


# --------------------------------------------------------------------------- stats
def _p(values: list[float], pct: float) -> float | None:
    return round(percentile(values, pct), 1) if values else None


def chain_depth(calls: list[tuple[float, float]]) -> int:
    """Longest chain of calls where each starts at/after the previous one ENDED (waterfall depth)."""
    ordered = sorted(calls)
    depth = [1] * len(ordered)
    for j, (sj, _) in enumerate(ordered):
        for i in range(j):
            if ordered[i][0] + ordered[i][1] <= sj + 1e-9:
                depth[j] = max(depth[j], depth[i] + 1)
    return max(depth, default=0)


def _page_summary(page: dict[str, Any]) -> dict[str, Any]:
    api = page.get("api") or []
    tpl = [(template_where(a[0]), float(a[1]), float(a[2])) for a in api]
    counts: dict[str, int] = {}
    for t, _, _ in tpl:
        counts[t] = counts.get(t, 0) + 1
    nav = page.get("nav")
    return {
        "path": template_path(page.get("path", "")),
        "at": page.get("at"),
        "api_calls": len(api),
        "distinct_endpoints": len(counts),
        "duplicates": {t: n for t, n in sorted(counts.items()) if n > 1},
        "data_ready_ms": round(max((s + d for _, s, d in tpl), default=0.0), 1),
        "chain_depth": chain_depth([(s, d) for _, s, d in tpl]),
        "nav": {k: nav.get(k) for k in ("ttfb", "dcl", "load", "bytes")} if nav else None,
        "assets": page.get("assets") or {},
    }


# Optional server concurrency metrics carried as an 8th api-tuple element (capture v1 stays valid
# without it). inflight/inflight_peak are counts; blk/blkq/lag are milliseconds.
CONC_METRICS = ("inflight", "inflight_peak", "blk", "blkq", "lag")
CONC_COMPARE = ("app_p50_ms", "inflight_peak_p50", "blk_p50", "blkq_p50", "lag_p50")


def _endpoint_stats(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    acc: dict[str, dict[str, list]] = {}
    for pg in pages:
        ptpl = template_path(pg.get("path", ""))
        for a in pg.get("api") or []:
            e = acc.setdefault(template_where(a[0]), {"dur": [], "ttfb": [], "app": [], "net": [],
                                                      "bytes": [], "bad": [], "pages": set(),
                                                      "conc": {}})
            dur, ttfb, app, size, status = float(a[2]), a[3], a[4], a[5], a[6]
            e["dur"].append(dur)
            if ttfb is not None:
                e["ttfb"].append(float(ttfb))
            if app is not None:
                e["app"].append(float(app))
                e["net"].append(max(0.0, dur - float(app)))
            x = a[7] if len(a) > 7 and isinstance(a[7], dict) else None
            for m in CONC_METRICS:
                if x and x.get(m) is not None:
                    e["conc"].setdefault(m, []).append(float(x[m]))
            e["bytes"].append(float(size or 0))
            e["bad"].append(0 if (status == 0 or 200 <= int(status) < 300) else 1)
            e["pages"].add(ptpl)
    out = {}
    for ep, e in sorted(acc.items()):
        out[ep] = {"count": len(e["dur"]), "p50_ms": _p(e["dur"], 50), "p95_ms": _p(e["dur"], 95),
                   "ttfb_p50_ms": _p(e["ttfb"], 50), "app_p50_ms": _p(e["app"], 50),
                   "app_p95_ms": _p(e["app"], 95), "network_p50_ms": _p(e["net"], 50),
                   "bytes_p50": _p(e["bytes"], 50), "non_2xx": sum(e["bad"]),
                   "pages": sorted(e["pages"])}
        for m, vals in e["conc"].items():  # present only when the server emitted them -- never 0
            out[ep][f"{m}_p50"], out[ep][f"{m}_p95"] = _p(vals, 50), _p(vals, 95)
    return out


# --------------------------------------------------------------------------- catalog / store
def live_slugs() -> set[str]:
    slugs: set[str] = set()
    for name in ("active-scope.txt", "build-scope.txt"):
        f = REPO_ROOT / "deploy" / "fleet" / name
        if f.exists():
            slugs |= {ln.strip() for ln in f.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    return slugs


def _safe(name: str, what: str) -> str:
    if not name or not _SAFE.match(name) or ".." in name:
        raise PerfProbeError(f"{what} {name!r} invalid: use letters/digits/._- only (no path separators)")
    return name


def _store(store: str | None) -> Path:
    return Path(store).expanduser() if store else DEFAULT_STORE


def _path(scope: str, label: str, store: str | None) -> Path:
    return _store(store) / _safe(scope, "scope") / f"{_safe(label, 'label')}.json"


def _load(scope: str, label: str, store: str | None) -> dict[str, Any]:
    p = _path(scope, label, store)
    if not p.exists():
        raise PerfProbeError(f"no stored summary for scope={scope} label={label} at {p}")
    return json.loads(p.read_text())


# --------------------------------------------------------------------------- actions
def snippet(kind: str = "append", offset: int = 0, size: int = 1000) -> dict[str, Any]:
    files = {"append": "capture-append.js", "read": "read.js", "clear": "clear.js"}
    if kind not in files:
        raise PerfProbeError(f"snippet kind must be one of {sorted(files)}, got {kind!r}")
    js = (ASSETS / files[kind]).read_text()
    if kind == "read":
        if offset < 0 or size <= 0:
            raise PerfProbeError("read needs offset>=0 and size>0")
        js = js.replace("__OFFSET__", str(int(offset))).replace("__SIZE__", str(int(size)))
    return {"ok": True, "status": "ok", "kind": kind, "js": js}


def ingest(scope: str, label: str, capture: str, store: str | None = None,
           overwrite: bool = False) -> dict[str, Any]:
    _safe(scope, "scope"); _safe(label, "label")
    try:
        cap = json.loads(Path(capture).expanduser().read_text())
    except (OSError, ValueError) as exc:
        raise PerfProbeError(f"capture unreadable: {exc}") from exc
    if not isinstance(cap, dict) or cap.get("v") != 1:
        raise PerfProbeError(f"unsupported capture version v={cap.get('v') if isinstance(cap, dict) else None!r} (need 1)")
    if not cap.get("pages"):
        raise PerfProbeError("capture has no pages")
    host = str(cap.get("host", ""))
    if scope in live_slugs():
        kind = "product"
    elif "." in scope:
        kind = "external"
        if host != scope:
            raise PerfProbeError(f"capture host {host!r} disagrees with external scope {scope!r}")
    else:
        raise PerfProbeError(f"scope {scope!r} is neither a live-catalog product slug nor an external host")
    dest = _path(scope, label, store)
    if dest.exists() and not overwrite:
        raise PerfProbeError(f"{dest} exists; pass overwrite=true to replace")
    summary = {"v": SUMMARY_VERSION, "scope": scope, "kind": kind, "label": label, "host": host,
               "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "pages": [_page_summary(p) for p in cap["pages"]],
               "endpoints": _endpoint_stats(cap["pages"])}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(summary, indent=1))
    return {"ok": True, "status": "ok", "path": str(dest), "kind": kind, "pages": len(summary["pages"]),
            "endpoints": len(summary["endpoints"]), "api_calls": sum(p["api_calls"] for p in summary["pages"])}


def _glob(items: list[str], pats: list[str] | None) -> list[str]:
    return items if not pats else [i for i in items if any(fnmatch.fnmatchcase(i, p) for p in pats)]


def _page_groups(s: dict[str, Any], pages: list[str] | None) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list[dict[str, Any]]] = {}
    for p in s["pages"]:
        if _glob([p["path"]], pages):
            g.setdefault(p["path"], []).append(p)
    return g


def _page_rows(s: dict[str, Any], pages: list[str] | None) -> dict[str, dict[str, Any]]:
    rows = {}
    for path, ps in _page_groups(s, pages).items():
        dr = [p["data_ready_ms"] for p in ps]
        rows[path] = {"loads": len(ps), "data_ready_p50_ms": _p(dr, 50), "data_ready_max_ms": max(dr),
                      "api_calls_p50": _p([p["api_calls"] for p in ps], 50),
                      "chain_depth_max": max(p["chain_depth"] for p in ps),
                      "ttfb_p50_ms": _p([p["nav"]["ttfb"] for p in ps if p["nav"]], 50)}
    return rows


def _endpoint_rows(s: dict[str, Any], pages: list[str] | None, endpoints: list[str] | None) -> dict[str, dict[str, Any]]:
    out = {}
    for ep, st in s["endpoints"].items():
        if endpoints and not _glob([ep], endpoints):
            continue
        if pages and not _glob(st["pages"], pages):
            continue
        out[ep] = st
    return out


def _is_edge(endpoint: str) -> bool:
    return any(fnmatch.fnmatchcase(_route_of(endpoint), g) for g in EDGE_PATHS)


def report(scope: str, label: str, store: str | None = None, pages: list[str] | None = None,
           endpoints: list[str] | None = None, top: int = 10, big_bytes: int = 100_000,
           budgets_path: str | None = None) -> dict[str, Any]:
    s = _load(scope, label, store)
    eps = _endpoint_rows(s, pages, endpoints)
    prow = _page_rows(s, pages)
    samples = sum(e["count"] for e in eps.values())
    findings: dict[str, Any] = {
        "slowest_pages": sorted(({"page": k, **v} for k, v in prow.items()),
                                key=lambda r: -r["data_ready_p50_ms"])[:top],
        "slowest_endpoints": sorted(({"endpoint": k, "count": v["count"], "p95_ms": v["p95_ms"], "p50_ms": v["p50_ms"]}
                                     for k, v in eps.items()), key=lambda r: -r["p95_ms"])[:top],
        "duplicate_calls": [], "deep_serial_chains": [], "edge_bound": [], "app_bound": [], "oversized": [],
        "non_2xx": [{"endpoint": k, "non_2xx": v["non_2xx"], "of": v["count"]} for k, v in eps.items() if v["non_2xx"]],
        "edge_floor": [{"endpoint": k, "count": v["count"], "p50_ms": v["p50_ms"], "p95_ms": v["p95_ms"]}
                       for k, v in eps.items() if _is_edge(k)],
    }
    for p in s["pages"]:
        if not _glob([p["path"]], pages):
            continue
        for t, n in p["duplicates"].items():
            if not endpoints or _glob([t], endpoints):
                findings["duplicate_calls"].append({"page": p["path"], "endpoint": t, "times": n})
        if p["chain_depth"] >= 3:
            findings["deep_serial_chains"].append({"page": p["path"], "depth": p["chain_depth"],
                                                   "data_ready_ms": p["data_ready_ms"]})
    findings["duplicate_calls"].sort(key=lambda r: -r["times"])
    findings["deep_serial_chains"].sort(key=lambda r: -r["depth"])
    for k, v in eps.items():
        if v["app_p50_ms"] is not None and v["p50_ms"] is not None:
            net = v["network_p50_ms"] or 0
            row = {"endpoint": k, "p50_ms": v["p50_ms"], "app_p50_ms": v["app_p50_ms"], "network_p50_ms": net}
            if net >= 100 and net >= 2 * v["app_p50_ms"]:
                findings["edge_bound"].append(row)
            elif v["app_p50_ms"] >= 0.5 * v["p50_ms"] and v["p50_ms"] >= 100:
                findings["app_bound"].append(row)
        if (v["bytes_p50"] or 0) >= big_bytes:
            findings["oversized"].append({"endpoint": k, "bytes_p50": v["bytes_p50"]})
    findings["concurrency"] = sorted(
        ({"endpoint": k, "count": v["count"], "app_p50_ms": v["app_p50_ms"],
          **{f: v[f] for m in CONC_METRICS for f in (f"{m}_p50", f"{m}_p95") if f in v}}
         for k, v in eps.items() if any(f"{m}_p50" in v for m in CONC_METRICS)),
        key=lambda r: -(r["app_p50_ms"] or 0))
    findings["edge_bound"].sort(key=lambda r: -r["network_p50_ms"])
    findings["app_bound"].sort(key=lambda r: -r["app_p50_ms"])

    result: dict[str, Any] = {"ok": True, "scope": scope, "label": label, "kind": s["kind"], "samples": samples,
                              "findings": findings}
    min_n = 5
    over: list[dict[str, Any]] = []
    if s["kind"] == "product":
        try:
            budgets = load_budgets(Path(budgets_path) if budgets_path else BUDGETS_PATH)
        except (OSError, ValueError) as exc:
            raise PerfProbeError(f"budgets unreadable: {exc}") from exc
        min_n = int(budgets.get("min_samples", 5))
        ignore = budgets.get("ignore_routes", [])
        measured = 0
        rows = []
        for k, v in eps.items():
            route = _route_of(k)
            if not route.startswith("/") or _is_edge(k) or any(fnmatch.fnmatchcase(route, g) for g in ignore):
                continue
            # method is not captured; the client view assumes GET (read/shell budgets).
            cls, budget, _ = classify("GET", route, budgets)
            row = {"endpoint": k, "class": cls, "budget_p95_ms": budget, "client_p95_ms": v["p95_ms"],
                   "app_p95_ms": v["app_p95_ms"], "count": v["count"]}
            if v["count"] < min_n:
                row["thin"] = True
            else:
                measured += 1
                if v["p95_ms"] > budget:
                    row["over_budget"] = True
                    row["basis"] = ("network" if v["app_p95_ms"] is not None and v["app_p95_ms"] <= budget
                                    else "app")
                    over.append(row)
            rows.append(row)
        result["budget"] = {"min_samples": min_n, "routes": rows, "over_budget": over, "measured": measured}
        status = "over_budget" if over else ("ok" if measured else "inconclusive")
    else:
        status = "ok" if samples >= min_n else "inconclusive"
    result["status"] = status
    result["exit_code"] = 0 if status == "ok" else 1
    if status == "inconclusive":
        result["hint"] = ("too few samples per endpoint (need >= min_samples repeated loads): capture more "
                          "page loads (or widen the scope filters) and re-ingest. Never read as ok.")
    return result


def _delta(b: float | None, a: float | None, min_pct: float, min_ms: float) -> tuple[str, float | None, float | None]:
    if b is None or a is None:
        return "unchanged", None, None
    d = round(a - b, 1)
    pct = round(d / b * 100, 1) if b else (None if d == 0 else 100.0)
    if abs(d) > min_ms and pct is not None and abs(pct) > min_pct:
        return ("regressed" if d > 0 else "improved"), d, pct
    return "unchanged", d, pct


def compare(scope: str, before: str, after: str, store: str | None = None, pages: list[str] | None = None,
            endpoints: list[str] | None = None, min_pct: float = 15.0, min_ms: float = 30.0) -> dict[str, Any]:
    sb, sa = _load(scope, before, store), _load(scope, after, store)

    def side(key: str, b: dict[str, Any], a: dict[str, Any], metric: str, extra: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for k in sorted(set(b) | set(a)):
            if k not in a:
                rows.append({key: k, "verdict": "gone", "before": b[k].get(metric)}); continue
            if k not in b:
                rows.append({key: k, "verdict": "new", "after": a[k].get(metric)}); continue
            v, d, pct = _delta(b[k].get(metric), a[k].get(metric), min_pct, min_ms)
            row = {key: k, "verdict": v, "before": b[k].get(metric), "after": a[k].get(metric),
                   "delta_ms": d, "delta_pct": pct}
            for x in extra:
                pair = [b[k].get(x), a[k].get(x)]
                if pair != [None, None] or x in ("p95_ms", "count"):
                    row[x] = pair
            rows.append(row)
        return rows

    erows = side("endpoint", _endpoint_rows(sb, pages, endpoints), _endpoint_rows(sa, pages, endpoints),
                 "p50_ms", ("p95_ms", "count") + CONC_COMPARE)
    prows = side("page", _page_rows(sb, pages), _page_rows(sa, pages), "data_ready_p50_ms",
                 ("api_calls_p50", "chain_depth_max"))
    allv = [r["verdict"] for r in erows + prows]
    if not (erows or prows):
        overall = "inconclusive"
    elif "regressed" in allv:
        overall = "regressed"
    elif "improved" in allv:
        overall = "improved"
    else:
        overall = "unchanged"
    return {"ok": True, "scope": scope, "before": before, "after": after, "status": overall,
            "exit_code": 1 if overall in ("regressed", "inconclusive") else 0,
            "noise_floor": {"min_pct": min_pct, "min_ms": min_ms},
            "pages": prows, "endpoints": erows}


def list_labels(scope: str | None = None, store: str | None = None) -> dict[str, Any]:
    root = _store(store)
    out: dict[str, list[str]] = {}
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            if scope and d.name != scope:
                continue
            out[d.name] = sorted(f.stem for f in d.glob("*.json"))
    return {"ok": True, "status": "ok", "store": str(root), "scopes": out}


def perf_probe(action: str, scope: str | None = None, label: str | None = None, capture: str | None = None,
               before: str | None = None, after: str | None = None, store: str | None = None,
               overwrite: bool = False, pages: list[str] | None = None, endpoints: list[str] | None = None,
               kind: str = "append", offset: int = 0, size: int = 1000, **opts: Any) -> dict[str, Any]:
    """Dispatcher. Every refusal is a named `error` (never a silent fallback)."""
    try:
        if action == "snippet":
            return snippet(kind, offset, size)
        if action == "list":
            return list_labels(scope, store)
        if not scope:
            raise PerfProbeError(f"{action} requires scope")
        if action == "ingest":
            if not (label and capture):
                raise PerfProbeError("ingest requires label and capture")
            return ingest(scope, label, capture, store, overwrite)
        if action == "report":
            if not label:
                raise PerfProbeError("report requires label")
            return report(scope, label, store, pages, endpoints, **opts)
        if action == "compare":
            if not (before and after):
                raise PerfProbeError("compare requires before and after")
            return compare(scope, before, after, store, pages, endpoints, **opts)
        raise PerfProbeError(f"unknown action {action!r} (snippet|ingest|report|compare|list)")
    except PerfProbeError as exc:
        return {"ok": False, "status": "error", "exit_code": 1, "error": str(exc)}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.perf_probe",
        description=(
            "Scoped BROWSER-side performance analysis (client view; server half = latency_report). SCOPE = a "
            "live product slug or an external host. action=snippet kind=append|read|clear returns the JS to run "
            "in the page (paths + query keys + timings only); ingest scope label capture=<raw json> TEMPLATES ids "
            "and stores only the summary under .noc-perf/<scope>/<label>.json (gitignored; store= overrides); "
            "report scope label -> slowest pages/endpoints, duplicate calls, serial chains, edge-vs-app, oversized, "
            "and for products over-budget vs deploy/fleet/latency-budgets.json (ok|over_budget|inconclusive); "
            "compare scope before after -> per-endpoint/page deltas with a 15%+30ms noise floor "
            "(improved|regressed|unchanged|new|gone) = evaluate an improvement; list. Filters: pages/endpoints globs. "
            "KB § PATTERNS/common/performance-analysis.md."
        ),
    )
    def _perf_probe(action: str, scope: str | None = None, label: str | None = None, capture: str | None = None,
                    before: str | None = None, after: str | None = None, store: str | None = None,
                    overwrite: bool = False, pages: list[str] | None = None, endpoints: list[str] | None = None,
                    kind: str = "append", offset: int = 0, size: int = 1000) -> dict:
        return perf_probe(action, scope, label, capture, before, after, store, overwrite, pages, endpoints,
                          kind, offset, size)


__all__ = ["perf_probe", "ingest", "report", "compare", "snippet", "list_labels", "template_path",
           "template_where", "chain_depth", "register"]
