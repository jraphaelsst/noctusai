"""noctus.dev.access_tier_findings -- the ``access-tier`` instance of the generic findings ledger.

The mechanism is ``findings_ledger`` (KB § PATTERNS/common/living-findings-ledgers.md); this module only supplies what is
specific to access tiers: the typed extension (``tier``, ``class``), the scanner (the route / table / grant / stream /
fingerprint keepers' current findings) and the effective-state (prod) writer. NEVER edit the ledger by hand.
Ratchet: a violation without a live row (open | in-progress | accepted) is NEW and fails the keeper.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from settings import REPO_ROOT
from tools.noctus.dev import findings_ledger as gl

NAME = "access-tier"
LEDGER_REL = Path("project-history/access-tiers/findings.ndjson")
SUMMARY_REL = Path("project-history/access-tiers/FINDINGS.md")
SCANNED = ("routes", "tables", "grants", "streams", "fingerprint", "schema")   # reconciled by the static keepers


# ---------------------------------------------------------------------------
# What the static scanners see right now
# ---------------------------------------------------------------------------
def current_rows(root: Path, sections: tuple[str, ...] = SCANNED) -> dict[str, dict]:
    """key -> normalized finding, from the live scanners (routes / tables / grants / streams / fingerprint)."""
    from tools.noctus.dev import access_tiers as at

    out: dict[str, dict] = {}
    if "routes" in sections:
        for r in at.classify_routes(root):
            if r.verdict != "ok":
                out[r.key] = {"section": "routes", "scope": r.product, "target": f"{r.method} {r.path}", "tier": r.tier,
                              "class": r.verdict, "severity": "high" if r.verdict == "too-open" else "medium", "note": r.note}
    if {"tables", "grants"} & set(sections):
        an = at.analyze_tables(root)
        if "tables" in sections:
            for f in an["findings"]:
                out[f["key"]] = {"section": "tables", "scope": f["product"], "target": f["table"],
                                 "tier": "platform" if f["kind"] in ("grant", "policy") else None, "class": f["kind"],
                                 "severity": f.get("severity", "high"), "note": f["issue"]}
        if "grants" in sections:
            for f in an["grant_findings"]:
                out[f["key"]] = {"section": "grants", "scope": f["product"], "target": f["table"], "tier": None,
                                 "class": "browser-grant", "severity": "medium", "note": f["issue"]}
    if "streams" in sections:
        for f in at.analyze_streams(root):
            out[f["key"]] = {"section": "streams", "scope": "agents" if "/agents/" in f["file"] else "seed",
                             "target": f["file"], "tier": None, "class": "stream-leak-filter", "severity": "high", "note": f["issue"]}
    if "schema" in sections:
        for f in at.analyze_schema_exposure(root):
            out[f["key"]] = {"section": "schema", "scope": f["product"], "target": f"{f['file']} ({f['n']} routes)", "tier": "platform",
                             "class": "platform-in-public-schema", "severity": "medium", "note": f["issue"]}
    if "fingerprint" in sections:
        for f in at.analyze_fingerprint(root):
            out[f["key"]] = {"section": "fingerprint", "scope": "agents", "target": f["key"].split(":", 1)[1], "tier": None,
                             "class": "leak-fingerprint", "severity": "high", "note": f["issue"]}
    return out



LEDGER = gl.register_ledger(gl.LedgerType(
    name=NAME, prefix="AT", path=str(LEDGER_REL), summary=str(SUMMARY_REL),
    extra={"tier": None, "class": None}, sections=SCANNED, scanner=lambda root: current_rows(root),
    advisory=("policy-pii", "browser-grant"), on_reconcile=lambda root: snapshot_metrics(root),   # heuristic classes: warn-only until measured precise
))


METRICS_REL = Path("project-history/access-tiers/metrics.ndjson")


def snapshot_metrics(root: Path | None = None) -> dict[str, Any]:
    """CISA Secure-by-Design: measure how common the class stays. One line per (date, sha) appended on reconcile."""
    import json

    root = root or REPO_ROOT
    rows = list(gl.load(LEDGER, root).values())
    live = [r for r in rows if r["status"] in ("open", "in-progress")]
    m = {
        "date": gl._today(), "sha": gl._head(root), "open_total": len(live),
        "routes_unclassified": sum(r["section"] == "routes" and r["class"] == "unclear" for r in live),
        "routes_too_open": sum(r["class"] == "too-open" for r in live),
        "public_undeclared_routes": sum(r["section"] == "routes" and r["class"] == "unclear" and "allowlist" in r["note"] for r in live),
        "platform_ip_tables_exposed": sum(r["class"] in ("grant", "policy") for r in live),
        "anon_readable_secret_or_pii_tables": sum(r["class"] in ("policy-secret", "policy-pii", "policy-open") for r in live),
        "tables_with_browser_grant": sum(r["class"] == "browser-grant" for r in live),
        "fixed_total": sum(r["status"] == "fixed" for r in rows),
    }
    p = root / METRICS_REL
    last = json.loads(p.read_text(encoding="utf-8").splitlines()[-1]) if p.exists() and p.read_text(encoding="utf-8").strip() else {}
    if (last.get("date"), last.get("sha")) != (m["date"], m["sha"]):
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(m, sort_keys=True) + "\n")
    return m


def reconcile(root: Path | None = None, found_by: str = "keeper", **_: Any) -> dict[str, Any]:
    return gl.reconcile(NAME, root, found_by=found_by)


def check(root: Path | None = None) -> list[dict]:
    return gl.check(NAME, root)


def known_live_keys(root: Path) -> set[str]:
    return gl.known_live_keys(NAME, root)


_EFFECTIVE_KINDS = frozenset({"grant", "policy", "policy-secret", "policy-open", "inactive-schema-served"})


def reconcile_effective(effective_result: dict, root: Path | None = None, found_by: str = "exposure-tool") -> dict[str, Any]:
    """Feed a `diff_exposure` result into the ledger: new `eff:` findings are opened; a previously-open `eff:` row that a
    FULLY MEASURED run no longer reports is closed. An unmeasured run only adds, never closes."""
    root = root or REPO_ROOT
    rows = gl.load(LEDGER, root)
    seen: set[str] = set()
    added = closed = 0
    for f in effective_result.get("findings", []):
        k = f"eff:{f['kind']}:{f['table']}"
        seen.add(k)
        if k not in rows or rows[k]["status"] == "fixed":
            rows[k] = gl._row(LEDGER, k, {"section": "effective", "scope": f["table"].split(".")[0], "target": f["table"],
                                          "severity": f.get("severity", "high"), "note": f["issue"],
                                          "tier": "platform" if f["kind"] in ("grant", "policy") else None, "class": f["kind"]},
                              "exposure-tool", found_by)
            added += 1
    if not effective_result.get("unmeasured"):
        sha = gl._head(root)
        for k, r in rows.items():
            if (r["section"] == "effective" and k not in seen and r["status"] in ("open", "in-progress")
                    and k.split(":")[1] in _EFFECTIVE_KINDS):  # only classes this tool MEASURES; seeded context rows stay
                r.update(status="fixed", status_detail=sha, closed_at=gl._today())
                closed += 1
    gl.save(LEDGER, rows, root)
    return {"ok": True, "added": added, "closed": closed}


__all__ = ["LEDGER", "check", "current_rows", "known_live_keys", "reconcile", "reconcile_effective"]
