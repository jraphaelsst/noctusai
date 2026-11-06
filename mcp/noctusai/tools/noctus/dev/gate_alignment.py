"""noctus.dev.gate_alignment — keep every gate aligned with the default-correct build.

The measurement + meta-gate half of the BUILD TRIAD
(`KB § PATTERNS/common/gate-methodology-sync.md`): every enforceable artifact
ships (a) a CONSTRUCTION leg that makes the correct thing the default, (b) a
BACKSTOP gate that catches only real drift, (c) ALIGNMENT TELEMETRY proving (a)
works. This module owns (c) and the check that (a)+(c) were declared:

* `record_event`   - one structured line per gate refusal / pass (gate, actor,
                     target, outcome), through the ONE writer the PreToolUse
                     guards already use (`scripts/hooks/_guard_failclosed.log_event`).
* `walls_report`   - ranks gates that fire in normal flow (live events) and the
                     transcript-measured history; measures each gate's
                     EFFECTIVE false-positive rate (a refusal not followed by a
                     pass of the same gate = no positive action taken).
* `triad_issues`   - the meta-gate (keeper `check_gate_triad`): every blocking
                     gate is declared in the inventory with a mechanism, an
                     owner, a placement and (when new) a shadow record. Legacy
                     gates with no mechanism yet sit in a SHRINK-ONLY baseline.
* `file_wall_findings` - reconciles the `gate-walls` living findings ledger (`gate_wall_findings.py`).

Stdlib-only at import (the cli wrapper imports it on every `--check-*` exit).
KB § PATTERNS/common/gate-methodology-sync.md (Build triad · Sources).
"""
from __future__ import annotations

import ast
import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
_PATTERN_DIR = Path("KNOWLEDGE-BASE/CONTEXT/PATTERNS/common")
INVENTORY_REL = _PATTERN_DIR / "gate-alignment-inventory.json"
BASELINE_REL = _PATTERN_DIR / "gate-triad-baseline.json"
RENDERED_REL = _PATTERN_DIR / "gate-alignment-inventory.md"

# Tunables (Tricorder, Sadowski et al.: keep effective false positives <= ~10%).
WALL_MIN_FIRINGS = 10          # a gate refusing this often in normal flow is a wall
WALL_MIN_SESSIONS = 4          # ... across this many distinct sessions
MAX_EFFECTIVE_FP = 0.10        # unfixed-refusal share above which a gate is demoted
MIN_SHADOW_DAYS = 7            # a NEW blocking gate runs warn-only this long first

CI_GATE_WORKFLOWS = ("test", "merge-queue", "embedding-cache-gate", "seed-typecheck", "agents-secc-ci")
MECHANISM_PREFIXES = ("KB §", "tool:", "scaffold:", "template:", "write-path:",
                      "injection:", "api:", "mcp/", "scripts/", "products/", "seed/", ".claude/")
_NONE_RE = re.compile(r"^none \(.{12,}\)$", re.S)


# ------------------------------------------------------------------ events
def _guard_module():
    import importlib.util
    path = REPO_ROOT / "scripts" / "hooks" / "_guard_failclosed.py"
    spec = importlib.util.spec_from_file_location("noc__guard_failclosed", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    import sys as _sys
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def events_path() -> Path:
    return Path(os.environ.get("NOCTUS_GUARD_EVENT_LOG") or _guard_module().EVENT_LOG)


def record_event(gate: str, outcome: str, *, kind: str, target: str = "",
                 reason: str = "", source: str = "", log_path: Path | None = None) -> None:
    """Append one gate event. `outcome` is 'deny' (refusal) or 'pass'. Never raises."""
    try:
        _guard_module().log_event(
            gate, outcome, reason,
            {"tool_name": kind, "tool_input": {"command": target},
             "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID") or None},
            log_path=log_path or Path(os.environ["NOCTUS_GUARD_EVENT_LOG"])
            if os.environ.get("NOCTUS_GUARD_EVENT_LOG") else log_path,
            extra={"kind": kind, "source": source},
        )
    except Exception as exc:  # telemetry must never change a verdict
        import sys
        print(f"gate_alignment: event write failed ({exc}); verdict unchanged", file=sys.stderr)


def record_cli_exit(argv: list[str], code: Any) -> None:
    """Called by cli.py on exit: log a `--check-*` / `--verify-*` gate run."""
    flags = [a for a in argv if re.match(r"^--(check|verify)-[a-z0-9-]+$", a)]
    if not flags:
        return
    ok = code in (None, 0)
    target = ""
    for i, a in enumerate(argv):
        if a == "--paths" and i + 1 < len(argv):
            target = argv[i + 1][:200]
    for f in flags:
        record_event(f"keeper:{f[2:]}", "pass" if ok else "deny", kind="keeper",
                     target=target, source="cli")


def read_events(path: Path | None = None) -> list[dict]:
    p = path or events_path()
    rows: list[dict] = []
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("guard"):
            row.setdefault("kind", "guard")
            gate = str(row["guard"])
            row["gate"] = gate if ":" in gate else f"guard:{gate}"
            rows.append(row)
    return rows


# --------------------------------------------------------------- inventory
def _cli_help(root: Path) -> dict[str, str]:
    """flag -> help text, parsed from cli.py's add_argument calls (AST, no regex)."""
    out: dict[str, str] = {}
    try:
        tree = ast.parse((root / "mcp/noctusai/cli.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument" and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            helps = [k.value for k in node.keywords if k.arg == "help"]
            if helps:
                try:
                    out[node.args[0].value.lstrip("-")] = str(ast.literal_eval(helps[0]))
                except ValueError:
                    pass
    return out


def _compliance_keepers(root: Path) -> dict[str, str]:
    """name -> 'high'|'critical' for every `check_*` in compliance.py whose body emits that severity (AST)."""
    p = root / "mcp/noctusai/tools/noctus/dev/compliance.py"
    out: dict[str, str] = {}
    try:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("check_"):
            seg = ast.get_source_segment(src, node) or ""
            sev = "critical" if re.search(r"""['"]severity['"]\s*:\s*['"]critical""", seg) else (
                "high" if re.search(r"""['"]severity['"]\s*:\s*['"]high""", seg) else "")
            if sev:
                out[node.name] = sev
    return out


def scan_gates(root: Path | None = None) -> dict[str, dict]:
    """Every gate the repo wires today: id -> {kind, wired_in, standard}."""
    root = root or REPO_ROOT
    helps = _cli_help(root)
    gates: dict[str, dict] = {}
    for hook in ("pre-commit", "pre-push"):
        p = root / "scripts" / "hooks" / hook
        if not p.exists():
            continue
        for flag in sorted(set(re.findall(r"--((?:check|verify)-[a-z0-9-]+)", p.read_text(encoding="utf-8")))):
            g = gates.setdefault(f"keeper:{flag}", {"kind": "keeper", "wired_in": [],
                                                    "standard": helps.get(flag, "")})
            g["wired_in"].append(hook)
    try:
        settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    for event, entries in (settings.get("hooks") or {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                m = re.search(r"claude-(guard|session-start)-([a-z0-9-]+)\.py", h.get("command", ""))
                if m and m.group(1) == "guard":
                    gates[f"guard:{m.group(2)}"] = {"kind": "guard", "wired_in": [event], "standard": ""}
    # High/critical keepers that run through the validate/CI sweep rather than a hook flag.
    for fn_name, sev in _compliance_keepers(root).items():
        gid = "keeper:" + fn_name.replace("_", "-")
        if gid not in gates:
            gates[gid] = {"kind": "keeper-batch", "wired_in": ["compliance.py sweep"], "standard": "", "severity": sev}
    wf = root / ".github" / "workflows"
    if wf.is_dir():
        for p in sorted(wf.glob("*.yml")):
            if p.stem not in CI_GATE_WORKFLOWS:  # build/deploy/cleanup workflows are not gates
                continue
            gates[f"ci:{p.stem}"] = {"kind": "ci", "wired_in": ["github-actions"], "standard": ""}
    return gates


def load_inventory(root: Path | None = None) -> dict:
    p = (root or REPO_ROOT) / INVENTORY_REL
    if not p.exists():
        return {"gates": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def load_baseline(root: Path | None = None) -> dict:
    p = (root or REPO_ROOT) / BASELINE_REL
    if not p.exists():
        return {"undeclared_mechanism": []}
    return json.loads(p.read_text(encoding="utf-8"))


def mechanism_ok(value: str | None) -> bool:
    v = (value or "").strip()
    return bool(v) and (v.startswith(MECHANISM_PREFIXES) or bool(_NONE_RE.match(v)))


def triad_issues(root: Path | None = None) -> list[dict]:
    """The meta-gate. Returns keeper-shaped issues; [] when the triad is honoured."""
    root = root or REPO_ROOT
    inv = load_inventory(root).get("gates", {})
    base = set(load_baseline(root).get("undeclared_mechanism", []))
    issues: list[dict] = []
    inv_file = str(INVENTORY_REL)

    def add(msg: str, sev: str = "high") -> None:
        issues.append({"file": inv_file, "issue": msg, "severity": sev})

    for gid, meta in sorted(scan_gates(root).items()):
        if gid not in inv:
            add(f"{gid} is wired ({', '.join(meta['wired_in'])}) but not declared in the gate inventory. "
                "Declare it with its construction leg: `python mcp/noctusai/cli.py --gate-alignment declare "
                f"--gate {gid} --mechanism '<scaffold/template/write-path/injection pointer | none (reason)>' "
                "--owner <agent>`. A gate ships its mechanism (KB § PATTERNS/common/gate-methodology-sync.md).")
    for gid, entry in sorted(inv.items()):
        mech = entry.get("mechanism", "")
        if not entry.get("owner"):
            add(f"{gid}: no owner. A wall must route somewhere - name the agent/file that owns this gate.")
        if mechanism_ok(mech):
            if gid in base:
                add(f"{gid}: now declares a mechanism but is still in {BASELINE_REL} - shrink the baseline "
                    "(`--gate-alignment refresh-baseline`).", "medium")
        elif gid not in base:
            add(f"{gid}: mechanism {mech!r} is not a construction pointer or 'none (reason)'. A NEW gate must ship "
                "the scaffold/template/write-path/injection that makes compliance the default, or justify none.")
        dem = entry.get("demoted")
        if dem is not None:  # demotion is containment, never the end state (research-and-fix owed)
            missing = [k for k in ("since", "expiry", "destination") if not (dem or {}).get(k)]
            if missing:
                add(f"{gid}: demoted-noisy without {missing}. A demoted gate carries an open ledger row: "
                    "`destination` = the researched fix (sources read, cited), `expiry` = date it must be re-promoted.")
            elif str(dem["expiry"]) < _dt.date.today().isoformat():
                add(f"{gid}: demoted-noisy past its expiry {dem['expiry']} - research how specialists detect this "
                    "property (primary sources), fix the detector, add FP+TP regression tests, re-measure, re-promote.")
        if entry.get("new") and not entry.get("source"):
            add(f"{gid}: a new gate cites no `source` (the standard/rule it enforces, read before codifying).")
        if entry.get("placement") == "blocking" and entry.get("new") and not entry.get("shadow"):
            add(f"{gid}: new blocking gate without a shadow-precision record. Run it warn-only for "
                f">={MIN_SHADOW_DAYS} days and record {{'since','fires','fix_rate'}} before promoting.")
    for gid in sorted(base - set(inv)):
        add(f"{BASELINE_REL}: {gid} no longer exists - drop it from the baseline.", "medium")
    issues.extend(matrix_issues(root)[0])
    return issues


def burn_down(root: Path | None = None) -> dict:
    inv = load_inventory(root).get("gates", {})
    base = load_baseline(root).get("undeclared_mechanism", [])
    declared = [g for g, e in inv.items() if mechanism_ok(e.get("mechanism"))]
    none_just = [g for g in declared if inv[g]["mechanism"].startswith("none")]
    return {"gates": len(inv), "declared": len(declared), "declared_none_justified": len(none_just),
            "undeclared_baseline": len(base)}


def refresh_baseline(root: Path | None = None) -> dict:
    """Shrink-only: drops baseline rows that now declare a mechanism or vanished. Never adds."""
    root = root or REPO_ROOT
    inv = load_inventory(root).get("gates", {})
    base = load_baseline(root).get("undeclared_mechanism", [])
    kept = [g for g in base if g in inv and not mechanism_ok(inv[g].get("mechanism"))]
    (root / BASELINE_REL).write_text(json.dumps({"undeclared_mechanism": sorted(kept)}, indent=1) + "\n")
    return {"before": len(base), "after": len(kept)}


def declare_gate(gate: str, mechanism: str, owner: str, *, standard: str = "",
                 placement: str = "warn", source: str = "", root: Path | None = None) -> dict:
    """Write/replace one inventory row. Refuses an invalid mechanism (no silent-null)."""
    root = root or REPO_ROOT
    if not mechanism_ok(mechanism):
        return {"ok": False, "error": "mechanism must point at the construction leg (KB §/tool:/scaffold:/template:/"
                "write-path:/injection:/api: or a path) or be 'none (<reason, >=12 chars>)'"}
    if not owner.strip():
        return {"ok": False, "error": "owner is required (the agent or file that owns this gate)"}
    if placement not in ("blocking", "warn", "report", "demoted"):
        return {"ok": False, "error": "placement must be blocking|warn|report"}
    inv = load_inventory(root)
    row = inv["gates"].get(gate, {})
    row.update({"mechanism": mechanism, "owner": owner, "placement": placement,
                "standard": standard or row.get("standard", ""), "new": row.get("new", gate not in inv["gates"]),
                "declared": _dt.date.today().isoformat()})
    if source:
        row["source"] = source
    if placement == "blocking" and row["new"]:
        row.setdefault("shadow", None)
    inv["gates"][gate] = row
    _write_inventory(root, inv)
    return {"ok": True, "gate": gate, "row": row}


def _write_inventory(root: Path, inv: dict) -> None:
    inv["gates"] = dict(sorted(inv["gates"].items()))
    (root / INVENTORY_REL).write_text(json.dumps(inv, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------- decision coverage matrix
_LEGS = ("home", "construction", "gate", "telemetry", "branch")


def matrix_issues(root: Path | None = None) -> tuple[list[dict], list[dict]]:
    """(failures, findings) for the decision coverage matrix (inventory `decisions`).

    FAIL: a row missing a leg, a row whose `gate` names no inventory gate and is not
    `pending:<branch>`, or a NEW gate (inventory `new: true`) no row references.
    FINDING (ledger, not a failure): a leg or gate marked `pending:<branch>` - the
    owning branch has not landed it yet; surfaced so it cannot be forgotten.
    """
    root = root or REPO_ROOT
    inv = load_inventory(root)
    gates = inv.get("gates", {})
    fails: list[dict] = []
    findings: list[dict] = []
    referenced: set[str] = set()
    for row in inv.get("decisions", []):
        did = row.get("id", "?")
        for leg in _LEGS:
            val = row.get(leg)
            if not val:
                fails.append({"file": str(INVENTORY_REL), "severity": "high",
                              "issue": f"decision {did}: missing leg `{leg}`. Every decision needs a methodology home, "
                                       "construction leg, backstop gate, telemetry and an owning branch."})
            elif isinstance(val, str) and val.startswith("pending:"):
                findings.append({"decision": did, "leg": leg, "pending": val})
        gate_ids = row.get("gates") or []
        for g in gate_ids:
            referenced.add(g)
            if g not in gates and not g.startswith("pending:"):
                fails.append({"file": str(INVENTORY_REL), "severity": "high",
                              "issue": f"decision {did}: gate {g} is not in the inventory (declare it, or use pending:<branch>)."})
            elif g.startswith("pending:"):
                findings.append({"decision": did, "leg": "gate", "pending": g})
        if not gate_ids and not str(row.get("gate", "")).startswith("pending:"):
            fails.append({"file": str(INVENTORY_REL), "severity": "high",
                          "issue": f"decision {did}: no backstop gate id listed in `gates`."})
    for gid, e in gates.items():
        if e.get("new") and gid not in referenced:
            fails.append({"file": str(INVENTORY_REL), "severity": "high",
                          "issue": f"{gid}: a new gate with no decision-matrix row. Add the row (or extend the decision it serves)."})
    return fails, findings


def sources_report(root: Path | None = None, base: str = "origin/dev") -> dict:
    """REPORT-ONLY (never blocks): KB docs changed on this branch that carry no sources section.

    Research-first is the default for every request; a methodology/KB deliverable cites what it read.
    """
    import subprocess
    root = root or REPO_ROOT
    r = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD", "--", "KNOWLEDGE-BASE/CONTEXT/PATTERNS"],
                       cwd=root, capture_output=True, text=True, timeout=60)
    missing = []
    for rel in r.stdout.split():
        p = root / rel
        if rel.endswith(".md") and p.exists() and not re.search(r"(?im)^#{1,4}\s.*(sources|references)|\*\*sources?\b|^composes[- ]with",
                                                              p.read_text(encoding="utf-8", errors="replace")):
            missing.append(rel)
    return {"ok": True, "report_only": True, "changed_kb_docs_without_sources": missing}


def render_matrix(root: Path | None = None) -> str:
    inv = load_inventory(root)
    out = ["| # | Decision | Home | Construction | Backstop gate | Telemetry | Branch |", "|---|---|---|---|---|---|---|"]
    for r in inv.get("decisions", []):
        out.append("| {id} | {decision} | {home} | {construction} | {gate} | {telemetry} | {branch} |".format(
            **{k: str(r.get(k, "")).replace("|", "/") for k in ("id", "decision", "home", "construction", "gate", "telemetry", "branch")}))
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- walls
def gate_stats(events: list[dict]) -> dict[str, dict]:
    """Per gate: denies, passes, sessions, fixed denies and the effective-FP rate.

    A deny is `fixed` when a later 'pass' of the SAME gate exists (same session,
    or same target) - i.e. the actor took a positive action. Denies without one
    are the effective false positives (Tricorder's definition).
    """
    by_gate: dict[str, list[dict]] = {}
    for e in events:
        by_gate.setdefault(e["gate"], []).append(e)
    stats: dict[str, dict] = {}
    for gate, rows in by_gate.items():
        rows.sort(key=lambda r: r.get("ts", ""))
        denies = [(i, r) for i, r in enumerate(rows) if r.get("outcome") == "deny"]
        fixed = 0
        for i, d in denies:
            later_pass = [r for r in rows[i + 1:] if r.get("outcome") == "pass"
                          and (r.get("session") == d.get("session") or r.get("target") == d.get("target"))]
            if later_pass or any(r.get("outcome") == "allow" for r in rows[i + 1:]
                                 if r.get("session") == d.get("session")):
                fixed += 1
        n = len(denies)
        stats[gate] = {"denies": n, "passes": sum(r.get("outcome") == "pass" for r in rows),
                       "sessions": len({r.get("session") for _, r in denies if r.get("session")}),
                       "fixed": fixed, "effective_fp": round((n - fixed) / n, 3) if n else 0.0}
    return stats


def walls_report(root: Path | None = None, events: list[dict] | None = None,
                 min_firings: int = WALL_MIN_FIRINGS, min_sessions: int = WALL_MIN_SESSIONS) -> dict:
    """Rank walls: gates firing in normal flow above threshold (live events + inventory history)."""
    root = root or REPO_ROOT
    inv = load_inventory(root).get("gates", {})
    live = gate_stats(events if events is not None else read_events())
    rows = []
    for gid in sorted(set(inv) | set(live)):
        hist = (inv.get(gid) or {}).get("firings", {}) or {}
        l = live.get(gid, {"denies": 0, "sessions": 0, "effective_fp": 0.0})
        firings = max(int(hist.get("count", 0)), l["denies"])
        sessions = max(int(hist.get("sessions", 0)), l["sessions"])
        wall = firings >= min_firings and sessions >= min_sessions
        noisy = l["denies"] >= 5 and l["effective_fp"] > MAX_EFFECTIVE_FP
        rows.append({"gate": gid, "firings": firings, "sessions": sessions, "live_denies": l["denies"],
                     "effective_fp": l["effective_fp"], "wall": wall, "demote": noisy,
                     "mechanism": (inv.get(gid) or {}).get("mechanism", ""),
                     "owner": (inv.get(gid) or {}).get("owner", "")})
    rows.sort(key=lambda r: (-r["firings"], r["gate"]))
    pending = matrix_issues(root)[1]
    walls = [r for r in rows if r["wall"] or r["demote"]]
    return {"threshold": {"firings": min_firings, "sessions": min_sessions, "max_effective_fp": MAX_EFFECTIVE_FP},
            "walls": walls, "pending_matrix": pending, "ranked": rows[:25], "burn_down": burn_down(root)}


def file_wall_findings(root: Path | None = None) -> dict:
    """Hand walls to the shared living findings ledger (`gate-walls`, `gate_wall_findings.py`): the ledger's own
    scanner decides what is still real, so this is a reconcile, never a hand-written row."""
    from tools.noctus.dev import findings_ledger as gl
    from tools.noctus.dev import gate_wall_findings  # noqa: F401  (registers the ledger)
    return gl.reconcile("gate-walls", root or REPO_ROOT, found_by="gate_alignment")


def render_markdown(root: Path | None = None) -> str:
    root = root or REPO_ROOT
    inv = load_inventory(root)
    gates = inv.get("gates", {})
    classes: dict[str, int] = {}
    for e in gates.values():
        classes[e.get("class", "?")] = classes.get(e.get("class", "?"), 0) + 1
    lines = [
        "# Gate alignment inventory",
        "",
        "> Generated from `gate-alignment-inventory.json` by `python mcp/noctusai/cli.py --gate-alignment render`."
        " Method and rules: `KB § PATTERNS/common/gate-methodology-sync.md`. Firing counts are measured from "
        f"{inv.get('measured_over', 'session transcripts')} (upper-bound-free: tool results only, one count per tool call).",
        "",
        "Totals by class: " + ", ".join(f"**{k}** {v}" for k, v in sorted(classes.items())) + f" (of {len(gates)} gates). "
        f"Mechanism burn-down: {burn_down(root)}.",
        "",
        "| Gate | Standard | Construction mechanism | Owner | Firings (sessions) | Class |",
        "|---|---|---|---|---:|---|",
    ]
    order = sorted(gates.items(), key=lambda kv: (-int((kv[1].get("firings") or {}).get("count", 0)), kv[0]))
    for gid, e in order:
        f = e.get("firings") or {}
        std = (e.get("standard") or "").replace("|", "/").replace("\n", " ")[:110]
        mech = (e.get("mechanism") or "**NONE**").replace("|", "/")[:90]
        lines.append(f"| `{gid}` | {std} | {mech} | {e.get('owner', '')} | {f.get('count', 0)} ({f.get('sessions', 0)}) | {e.get('class', '?')} |")
    lines += ["", "## Route auth / exposure gates re-judged for a publicly documented API", "",
              "| Gate | Verdict | Gap / overlap / decision |", "|---|---|---|"]
    for gid, e in sorted(gates.items()):
        r = e.get("api_review")
        if r:
            lines.append(f"| `{gid}` | {r['verdict']} | {r['note'].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------- MCP tool
def register(server) -> None:
    @server.tool(
        name="noctus.dev.gate_alignment",
        description=(
            "Gate alignment (build-triad telemetry + meta-gate). action=walls (default): rank gates that fire in "
            "normal flow and their effective false-positive rate; file=true appends wall findings to the ledger "
            "feed. action=sources: report-only KB docs changed without a sources section. action=triad: run the meta-gate (every gate declared with mechanism+owner). action=declare: "
            "write one inventory row (gate, mechanism, owner, placement). action=render: regenerate the inventory "
            "markdown. action=refresh-baseline: shrink-only. Read-only except file/declare/render/refresh-baseline."
        ),
    )
    def _gate_alignment(action: str = "walls", gate: str = "", mechanism: str = "", owner: str = "",
                        placement: str = "warn", file: bool = False, worktree_path: str = "") -> dict:
        return run_action(action, gate=gate, mechanism=mechanism, owner=owner, placement=placement,
                          file=file, root=Path(worktree_path) if worktree_path else None)


def run_action(action: str, *, gate: str = "", mechanism: str = "", owner: str = "",
               placement: str = "warn", file: bool = False, root: Path | None = None) -> dict:
    root = root or REPO_ROOT
    if action == "walls":
        rep = walls_report(root)
        if file:
            rep["filed"] = file_wall_findings(root)
        return {"ok": True, **rep}
    if action == "triad":
        issues = triad_issues(root)
        return {"ok": not issues, "issues": issues, "burn_down": burn_down(root)}
    if action == "declare":
        return declare_gate(gate, mechanism, owner, placement=placement, root=root)
    if action == "sources":
        return sources_report(root)
    if action == "matrix":
        fails, findings = matrix_issues(root)
        return {"ok": not fails, "issues": fails, "pending_findings": findings, "table": render_matrix(root)}
    if action == "render":
        (root / RENDERED_REL).write_text(render_markdown(root) + "\n## Decision coverage matrix\n\n" + render_matrix(root), encoding="utf-8")
        return {"ok": True, "path": str(RENDERED_REL)}
    if action == "refresh-baseline":
        return {"ok": True, **refresh_baseline(root)}
    return {"ok": False, "error": f"unknown action {action!r}; one of walls|triad|matrix|sources|declare|render|refresh-baseline"}


__all__ = ["record_event", "record_cli_exit", "read_events", "scan_gates", "triad_issues", "walls_report",
           "gate_stats", "declare_gate", "burn_down", "run_action", "register"]
