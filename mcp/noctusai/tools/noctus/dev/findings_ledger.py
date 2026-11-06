"""noctus.dev.findings_ledger -- ONE generic mechanism for LIVING findings ledgers.

A *ledger* is a typed instance of one mechanism: a machine-readable NDJSON file (one row per line, sorted by id, so
parallel branches merge line-wise) plus a rendered summary next to it, written ONLY by this tool -- never by hand.
Instances today: ``access-tier`` (security burn-down, ``access_tier_findings``); Julia's mistakes ledger registers the
same way. KB § PATTERNS/common/living-findings-ledgers.md.

SHARED CORE (every ledger): ``id`` (``<prefix>-`` + hash of key: stable, merge-safe) · ``key`` · ``section`` · ``scope``
(product slug / agent key: the unit an agent works in) · ``target`` · ``severity`` · ``status`` (open | in-progress
<branch> | fixed <sha> | accepted <rationale>) · ``status_detail`` · ``source`` (which scanner / eval produced it) ·
``found_by`` · ``found_at`` · ``closed_at`` · ``note``. TYPED EXTENSION: each ledger declares ``extra`` fields (security:
``tier``, ``class``; Julia: ``attribution`` MODEL|STRUCTURAL|CONTENT, ``regression_case_id``) with allowed values.

REGISTRATION API (a ledger plugs in, it does not fork)::

    from tools.noctus.dev.findings_ledger import LedgerType, register_ledger
    register_ledger(LedgerType(
        name="julia-mistakes", prefix="JM", path="project-history/julia/mistakes.ndjson",
        summary="project-history/julia/MISTAKES.md",
        extra={"attribution": ("MODEL", "STRUCTURAL", "CONTENT"), "regression_case_id": None},   # None = free text
        sections=("eval",),
        scanner=lambda root: {key: {"section": "eval", "scope": "julia", "target": ..., "severity": "high", "note": ...,
                                    "attribution": "CONTENT", "regression_case_id": "..."}},      # what is STILL real
    ))

``scanner(root) -> {key: row-fields}`` is the ONE hook that decides whether a row is still real: ``reconcile`` opens
rows it returns that have no live row, closes (``fixed <sha>``) live rows of its ``sections`` it no longer returns, and
reopens a ``fixed`` row that came back. ``check`` (the ONE drift keeper, over ALL ledgers) fails when a status disagrees
with the latest scan: a NEW finding without a row, a ``fixed`` row still seen, a live row no longer seen. A ledger with
``scanner=None`` is manual-only (append / update; no reality check). Visibility: ``open_for_scope`` feeds briefs, the
agent-context extract and the noc-graph node of the scope.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from settings import REPO_ROOT

STATUSES = ("open", "in-progress", "fixed", "accepted")
LIVE = ("open", "in-progress", "accepted")
SEVERITIES = ("critical", "high", "medium", "low")
CORE = ("id", "key", "section", "scope", "target", "severity", "status", "status_detail", "source", "found_by",
        "found_at", "closed_at", "note")


@dataclass
class LedgerType:
    name: str
    prefix: str
    path: str
    summary: str
    extra: dict[str, tuple[str, ...] | None] = field(default_factory=dict)
    sections: tuple[str, ...] = ()
    scanner: Callable[[Path], dict[str, dict]] | None = None
    target_label: str = "target"
    #: classes from HEURISTIC checks: recorded in the ledger (reconcile) but warn-only -- a NEW one never fails `check`
    #: until the heuristic has measured precise (Google SRE-book ch.12: block only what is near-zero false-positive).
    advisory: tuple[str, ...] = ()
    #: called with the repo root after every successful `reconcile` (e.g. append a metrics snapshot)
    on_reconcile: Callable[[Path], Any] | None = None


_REGISTRY: dict[str, LedgerType] = {}


def register_ledger(lt: LedgerType) -> LedgerType:
    _REGISTRY[lt.name] = lt
    return lt


def ledgers() -> dict[str, LedgerType]:
    _load_builtin()
    return _REGISTRY


def _load_builtin() -> None:
    if "access-tier" not in _REGISTRY:
        from tools.noctus.dev import access_tier_findings  # noqa: F401  (registers on import)
    if "gate-walls" not in _REGISTRY:
        from tools.noctus.dev import gate_wall_findings  # noqa: F401  (registers on import)


def get(name: str) -> LedgerType:
    _load_builtin()
    if name not in _REGISTRY:
        raise KeyError(f"unknown ledger {name!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def _id(lt: LedgerType, key: str) -> str:
    return f"{lt.prefix}-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]  # noqa: S324 -- identity, not security


def _today() -> str:
    return datetime.date.today().isoformat()


def _head(root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, timeout=15, check=False)
        return out.stdout.strip() or "worktree"
    except (OSError, subprocess.SubprocessError):
        return "worktree"


def load(lt: LedgerType, root: Path | None = None) -> dict[str, dict]:
    p = (root or REPO_ROOT) / lt.path
    rows: dict[str, dict] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["key"]] = r
    return rows


def save(lt: LedgerType, rows: dict[str, dict], root: Path | None = None) -> None:
    root = root or REPO_ROOT
    p = root / lt.path
    p.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: r["id"])
    p.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in ordered), encoding="utf-8")
    _write_roster(lt, root)
    (root / lt.summary).parent.mkdir(parents=True, exist_ok=True)
    (root / lt.summary).write_text(render_summary(lt, ordered), encoding="utf-8")


ROSTER_REL = Path("project-history/findings-ledgers.json")


def _write_roster(lt: LedgerType, root: Path) -> None:
    """The roster the SessionStart/SubagentStart injection hook reads (stdlib-only, no toolkit import)."""
    p = root / ROSTER_REL
    doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"ledgers": {}}
    doc.setdefault("ledgers", {})[lt.name] = {"path": lt.path, "summary": lt.summary, "extra": sorted(lt.extra)}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"_comment": "GENERATED by noctus.dev.findings_ledger on every save. Read by scripts/hooks/claude-inject-open-findings.py.",
                             "ledgers": dict(sorted(doc["ledgers"].items()))}, indent=1) + "\n", encoding="utf-8")


def _validate_extra(lt: LedgerType, fields: dict[str, Any]) -> str | None:
    for name, allowed in lt.extra.items():
        v = fields.get(name)
        if allowed is not None and v not in allowed:
            return f"{lt.name}: `{name}` must be one of {allowed} (got {v!r})"
    return None


def _row(lt: LedgerType, key: str, f: dict[str, Any], source: str, found_by: str, status: str = "open", detail: str = "") -> dict:
    r = {"id": _id(lt, key), "key": key, "section": f.get("section", "manual"), "scope": f.get("scope", ""),
         "target": f.get("target", ""), "severity": f.get("severity", "high"), "status": status, "status_detail": detail,
         "source": source, "found_by": found_by, "found_at": _today(), "closed_at": "", "note": f.get("note", "")}
    for name in lt.extra:
        r[name] = f.get(name) if f.get(name) is not None else "none"
    return r


def _cur(lt: LedgerType, root: Path, sections: tuple[str, ...] | None = None) -> dict[str, dict]:
    if lt.scanner is None:
        return {}
    cur = lt.scanner(root)
    return {k: v for k, v in cur.items() if sections is None or v.get("section") in sections}


def reconcile(name: str, root: Path | None = None, found_by: str = "scanner", add: bool = True, close: bool = True) -> dict[str, Any]:
    lt = get(name)
    root = root or REPO_ROOT
    if lt.scanner is None:
        return {"ok": False, "error": f"ledger {name} is manual-only (no scanner registered)"}
    rows = load(lt, root)
    cur = _cur(lt, root)
    added = closed = reopened = 0
    sha = _head(root)
    for k, c in cur.items():
        r = rows.get(k)
        if r is None:
            if add:
                rows[k] = _row(lt, k, c, c.get("section", "scan"), found_by)
                added += 1
        elif r["status"] == "fixed":
            r.update(status="open", status_detail="", closed_at="", note=("regressed; " + c.get("note", ""))[:600])
            reopened += 1
    if close:
        scanned = set(lt.sections) if lt.sections else {v.get("section") for v in cur.values()}
        for k, r in rows.items():
            if r["section"] in scanned and r["status"] in ("open", "in-progress") and k not in cur:
                r.update(status="fixed", status_detail=sha, closed_at=_today())
                closed += 1
    save(lt, rows, root)
    if lt.on_reconcile is not None:
        lt.on_reconcile(root)
    return {"ok": True, "ledger": name, "added": added, "closed": closed, "reopened": reopened, "total": len(rows),
            "open": sum(1 for r in rows.values() if r["status"] in ("open", "in-progress"))}


def check(name: str, root: Path | None = None) -> list[dict]:
    """Status vs reality for one ledger (manual-only ledgers have no reality to disagree with)."""
    lt = get(name)
    root = root or REPO_ROOT
    if lt.scanner is None:
        return []
    rows = load(lt, root)
    cur = _cur(lt, root)
    out: list[dict] = []

    def _i(msg: str) -> None:
        out.append({"file": lt.path, "line": 0, "severity": "high",
                    "issue": f"[{lt.name}] {msg} Run `noctus.dev.findings_ledger action=reconcile ledger={lt.name}` "
                             "(CLI: `cli.py --findings-ledger-reconcile " + lt.name + "`); never edit the ledger by hand."})

    scanned = set(lt.sections) if lt.sections else {v.get("section") for v in cur.values()} | {r["section"] for r in rows.values() if r["section"] != "manual"}
    for k, c in sorted(cur.items()):
        r = rows.get(k)
        if r is None and c.get("class") in lt.advisory:
            continue
        if r is None:
            _i(f"NEW finding without a row: {c.get('scope')} {c.get('target')} -- {str(c.get('note', ''))[:140]}")
        elif r["status"] == "fixed":
            _i(f"{r['id']} ({r['scope']} {r['target']}) is marked FIXED ({r['status_detail']}) but the scanner still sees it.")
    for k, r in sorted(rows.items()):
        if r["section"] in scanned and r["section"] not in ("manual", "effective") and k not in cur and r["status"] in LIVE:
            _i(f"{r['id']} ({r['scope']} {r['target']}) is {r['status']} but the scanner no longer sees it: close it.")
    return out


def check_all(root: Path | None = None) -> list[dict]:
    out: list[dict] = []
    for n in sorted(ledgers()):
        out += check(n, root)
    return out


def known_live_keys(name: str, root: Path | None = None) -> set[str]:
    lt = get(name)
    return {k for k, r in load(lt, root).items() if r["status"] in LIVE}


def append(name: str, root: Path | None = None, *, scope: str, target: str, found_by: str, severity: str = "high",
           note: str = "", status: str = "open", detail: str = "", key: str | None = None, source: str = "manual",
           section: str = "manual", **extra: Any) -> dict:
    lt = get(name)
    root = root or REPO_ROOT
    if status not in STATUSES:
        return {"ok": False, "error": f"status must be one of {STATUSES}"}
    if severity not in SEVERITIES:
        return {"ok": False, "error": f"severity must be one of {SEVERITIES}"}
    if status != "open" and not detail.strip():
        return {"ok": False, "error": f"status {status} needs status_detail (branch | sha | rationale)"}
    bad = _validate_extra(lt, {**{n: None for n in lt.extra}, **extra}) if any(a is not None for a in lt.extra.values()) else None
    if bad:
        return {"ok": False, "error": bad}
    rows = load(lt, root)
    k = key or f"manual:{scope}:{target}"
    if k in rows and rows[k]["status"] != "fixed":
        return {"ok": False, "error": f"{rows[k]['id']} already exists ({rows[k]['status']}); use action=update"}
    f = {"section": section, "scope": scope, "target": target, "severity": severity, "note": note, **extra}
    rows[k] = _row(lt, k, f, source, found_by, status, detail)
    if status == "fixed":
        rows[k]["closed_at"] = _today()
    save(lt, rows, root)
    return {"ok": True, "id": rows[k]["id"]}


def update(name: str, root: Path | None = None, *, id: str, status: str, detail: str = "", note: str | None = None) -> dict:
    lt = get(name)
    root = root or REPO_ROOT
    if status not in STATUSES:
        return {"ok": False, "error": f"status must be one of {STATUSES}"}
    if status != "open" and not detail.strip():
        return {"ok": False, "error": f"status {status} needs detail (branch | sha | rationale)"}
    rows = load(lt, root)
    hit = next((r for r in rows.values() if r["id"] == id), None)
    if hit is None:
        return {"ok": False, "error": f"no finding {id} in ledger {name}"}
    hit.update(status=status, status_detail=detail, closed_at=_today() if status == "fixed" else "")
    if note is not None:
        hit["note"] = note
    save(lt, rows, root)
    return {"ok": True, "id": id, "status": status}


def query(name: str, root: Path | None = None, scope: str | None = None, status: str | None = None,
          section: str | None = None, limit: int = 60) -> dict:
    lt = get(name)
    rows = [r for r in load(lt, root).values()
            if (not scope or r["scope"] == scope) and (not status or r["status"] == status) and (not section or r["section"] == section)]
    rows.sort(key=lambda r: (SEVERITIES.index(r["severity"]) if r["severity"] in SEVERITIES else 9, r["scope"], r["id"]))
    keep = ("id", "scope", "target", "severity", "status", "status_detail", "source", "found_by", "found_at", *lt.extra)
    return {"ledger": name, "count": len(rows), "findings": [{k: r.get(k) for k in keep} for r in rows[:limit]]}


def status_of(name: str, root: Path | None = None) -> dict:
    lt = get(name)
    rows = list(load(lt, root).values())
    by: dict[str, dict[str, int]] = {}
    for r in rows:
        by.setdefault(r["scope"], {}).setdefault(r["status"], 0)
        by[r["scope"]][r["status"]] += 1
    return {"ledger": name, "total": len(rows), "open": sum(1 for r in rows if r["status"] in ("open", "in-progress")),
            "by_scope": by, "drift": len(check(name, root))}


def open_for_scope(scope: str, root: Path | None = None, limit: int = 6) -> list[str]:
    """Compact lines, across EVERY ledger, for a product / agent an engineer is about to touch (open rows first)."""
    out: list[str] = []
    for n, lt in sorted(ledgers().items()):
        live = [r for r in load(lt, root).values() if r["scope"] == scope and r["status"] in ("open", "in-progress")]
        if not live:
            continue
        by: dict[str, int] = {}
        for r in live:
            c = r.get("class") or r.get("attribution") or r["section"]
            by[c] = by.get(c, 0) + 1
        out.append(f"[{n}] {scope}: {len(live)} open ({', '.join(f'{c} {k}' for c, k in sorted(by.items()))}) -- see {lt.summary}")
        worst = sorted((r for r in live if r.get("class") != "browser-grant"),
                       key=lambda r: SEVERITIES.index(r["severity"]) if r["severity"] in SEVERITIES else 9)
        out += [f"  {r['id']} [{r['severity']}] {r['target']}" for r in worst[:limit]]
    return out


def render_summary(lt: LedgerType, rows: list[dict]) -> str:
    live = [r for r in rows if r["status"] in ("open", "in-progress")]
    L = [f"# {lt.name} -- living findings ledger", "",
         f"> GENERATED next to `{Path(lt.path).name}` by `noctus.dev.findings_ledger` (`cli.py --findings-ledger-reconcile {lt.name}`). "
         "Never edit by hand. Read your scope's open rows before you touch it. KB § PATTERNS/common/living-findings-ledgers.md.", "",
         f"**{len(live)} open / in-progress**, {sum(1 for r in rows if r['status'] == 'fixed')} fixed, "
         f"{sum(1 for r in rows if r['status'] == 'accepted')} accepted ({len(rows)} total).", "",
         "| scope | open | critical | high | medium | in-progress | fixed |", "|---|---:|---:|---:|---:|---:|---:|"]
    for p in sorted({r["scope"] for r in rows}):
        pr = [r for r in rows if r["scope"] == p]
        o = [r for r in pr if r["status"] in ("open", "in-progress")]
        L.append(f"| {p} | {len(o)} | {sum(r['severity'] == 'critical' for r in o)} | {sum(r['severity'] == 'high' for r in o)} | "
                 f"{sum(r['severity'] == 'medium' for r in o)} | {sum(r['status'] == 'in-progress' for r in pr)} | "
                 f"{sum(r['status'] == 'fixed' for r in pr)} |")
    extras = list(lt.extra)
    L += ["", "## Open / in-progress (bulk rows are summarised below; every row is in the NDJSON)", "",
          "| id | scope | target | " + " | ".join(extras) + (" | " if extras else "") + "sev | status | found |",
          "|---|---|---|" + "---|" * len(extras) + "---|---|---|"]
    bulk: dict[str, int] = {}
    for r in sorted(live, key=lambda r: (SEVERITIES.index(r["severity"]) if r["severity"] in SEVERITIES else 9, r["scope"], r["target"])):
        if r.get("class") == "browser-grant":
            bulk[r["scope"]] = bulk.get(r["scope"], 0) + 1
            continue
        st = r["status"] + (f" {r['status_detail']}" if r["status_detail"] else "")
        L.append(f"| {r['id']} | {r['scope']} | `{r['target']}` | " + " | ".join(str(r.get(e, "")) for e in extras)
                 + (" | " if extras else "") + f"{r['severity']} | {st} | {r['found_by']} {r['found_at']} |")
    if bulk:
        L += ["", "## Bulk (defence in depth: browser grants on tables without `tier:org|public`)", ""]
        L += [f"- {p}: {n}" for p, n in sorted(bulk.items(), key=lambda kv: -kv[1])]
    acc = [r for r in rows if r["status"] == "accepted"]
    if acc:
        L += ["", "## Accepted (rationale on record)", ""] + [f"- {r['id']} {r['scope']} `{r['target']}` -- {r['status_detail']}" for r in acc]
    return "\n".join(L) + "\n"


_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}


def export_sarif(name: str, root: Path | None = None) -> dict:
    """The ledger as SARIF 2.1.0 (OASIS) so GitHub code scanning can show it (``codeql-action/upload-sarif``).
    Mapping: ruleId = class (else section) · level = severity (critical/high -> error, medium -> warning, low -> note) ·
    location = target (a repo path -> physicalLocation, anything else -> logicalLocation) · baselineState = reconcile
    (open/in-progress/accepted -> unchanged, fixed -> absent) · suppressions[] = accept-with-rationale (accepted ->
    state `accepted` + justification; in-progress -> `underReview` + the branch) · properties = id/scope/status/found_by."""
    lt = get(name)
    rows = sorted(load(lt, root).values(), key=lambda r: r["id"])
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for r in rows:
        rid = str(r.get("class") or r["section"])
        rules.setdefault(rid, {"id": rid, "name": rid, "shortDescription": {"text": f"{lt.name}: {rid}"}})
        tgt = r["target"]
        loc = ({"physicalLocation": {"artifactLocation": {"uri": tgt}}} if "/" in tgt and " " not in tgt and "." in tgt.rsplit("/", 1)[-1]
               else {"logicalLocations": [{"name": tgt, "kind": "member"}]})
        res: dict[str, Any] = {
            "ruleId": rid, "level": _SARIF_LEVEL.get(r["severity"], "warning"), "message": {"text": (r["note"] or rid)[:900]},
            "locations": [loc], "baselineState": "absent" if r["status"] == "fixed" else "unchanged",
            "partialFingerprints": {"findingId/v1": r["id"]},
            "properties": {k: r.get(k) for k in ("id", "scope", "status", "status_detail", "found_by", "found_at", "severity", *lt.extra)},
        }
        if r["status"] == "accepted":
            res["suppressions"] = [{"kind": "external", "state": "accepted", "justification": r["status_detail"]}]
        elif r["status"] == "in-progress":
            res["suppressions"] = [{"kind": "external", "state": "underReview", "justification": r["status_detail"]}]
        results.append(res)
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": f"noctus-{lt.name}", "informationUri": "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/living-findings-ledgers.md",
                            "rules": sorted(rules.values(), key=lambda x: x["id"])}},
        "results": results}]}


def scaffold(name: str, prefix: str, extra: dict[str, list[str] | None] | None = None, sections: tuple[str, ...] = ("scan",)) -> dict:
    """Return the registration module for a NEW ledger (scaffolders return code; the caller pastes it under
    mcp/noctusai/tools/noctus/dev/<name>_findings.py and adds `from . import <name>_findings` to the dev package)."""
    mod = name.replace("-", "_")
    ex = {k: (tuple(v) if v else None) for k, v in (extra or {}).items()}
    code = f'''"""The `{name}` instance of the generic findings ledger (mechanism: findings_ledger; KB § PATTERNS/common/living-findings-ledgers.md)."""
from __future__ import annotations

from pathlib import Path

from tools.noctus.dev import findings_ledger as gl


def current_rows(root: Path) -> dict[str, dict]:
    """key -> {{section, scope, target, severity, note, <extra fields>}} for everything STILL real (the scan / eval decides)."""
    raise NotImplementedError("TODO: run the scanner / eval that decides whether a finding is still real")


LEDGER = gl.register_ledger(gl.LedgerType(
    name={name!r}, prefix={prefix!r}, path="project-history/{name}/findings.ndjson", summary="project-history/{name}/FINDINGS.md",
    extra={ex!r}, sections={tuple(sections)!r}, scanner=current_rows,
))
'''
    return {"ok": True, "module": f"mcp/noctusai/tools/noctus/dev/{mod}_findings.py", "code": code,
            "also": [f"add `from . import {mod}_findings` next to `findings_ledger` in tools/noctus/dev/__init__.py (and to findings_ledger._load_builtin)",
                     "a keeper test: register, reconcile a fixture scan, assert check() == [] then a fixed-but-seen row fails"]}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.findings_ledger",
        description=(
            "ONE tool for every LIVING findings ledger (access-tier security burn-down, Julia's mistakes, any future one); "
            "the only writer -- never edit a ledger by hand. action=ledgers (registered ledgers + schemas) | export_sarif (SARIF 2.1.0 for GitHub code scanning) | scaffold (target=<name>, scope=<PREFIX>, extra={field: 'A|B'}: returns the registration module for a NEW ledger) | status | query "
            "(scope/status/section filters, worst first) | open_for_scope (compact lines across ALL ledgers for a product/agent "
            "you are about to touch) | append (scope,target,found_by,severity,note + the ledger's extra fields) | update "
            "(id,new_status: open | in-progress <branch> | fixed <sha> | accepted <rationale>, detail) | reconcile (the ledger's "
            "registered scanner adds new rows, closes fixed ones, reopens regressions) | check (status-vs-reality drift)."
        ),
    )
    def _ledger(action: str = "ledgers", ledger: str = "access-tier", scope: str | None = None, status: str | None = None,
                section: str | None = None, id: str | None = None, target: str | None = None, severity: str = "high",
                found_by: str = "agent", note: str = "", detail: str = "", new_status: str | None = None,
                extra: dict[str, str] | None = None, worktree_path: str | None = None) -> dict:
        root = Path(worktree_path) if worktree_path else REPO_ROOT
        try:
            if action == "export_sarif":
                return export_sarif(ledger, root)
            if action == "scaffold":
                if not (target and scope):
                    return {"ok": False, "error": "scaffold needs target=<ledger name> and scope=<2-letter prefix>"}
                return scaffold(target, scope.upper(), extra={k: ([x for x in v.split("|")] if v else None) for k, v in (extra or {}).items()})
            if action == "ledgers":
                return {n: {"path": lt.path, "extra": {k: v for k, v in lt.extra.items()}, "scanner": lt.scanner is not None}
                        for n, lt in sorted(ledgers().items())}
            if action == "open_for_scope":
                return {"lines": open_for_scope(scope or "", root)}
            if action == "status":
                return status_of(ledger, root)
            if action == "query":
                return query(ledger, root, scope, status, section)
            if action == "check":
                return {"issues": check(ledger, root)}
            if action == "reconcile":
                return reconcile(ledger, root, found_by=found_by)
            if action == "append":
                if not (scope and target):
                    return {"ok": False, "error": "append needs scope and target"}
                return append(ledger, root, scope=scope, target=target, found_by=found_by, severity=severity, note=note,
                              status=new_status or "open", detail=detail, **(extra or {}))
            if action == "update":
                if not (id and new_status):
                    return {"ok": False, "error": "update needs id and new_status"}
                return update(ledger, root, id=id, status=new_status, detail=detail, note=note or None)
        except KeyError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "action must be ledgers | scaffold | status | query | open_for_scope | append | update | reconcile | check"}


__all__ = ["LedgerType", "append", "check", "check_all", "get", "known_live_keys", "ledgers", "load", "open_for_scope",
           "query", "reconcile", "register", "register_ledger", "status_of", "update"]
