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

from tools.noctus.dev._primary_ledger_guard import ensure_not_shared_primary

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
                 reason: str = "", source: str = "", log_path: Path | None = None,
                 class_key: str = "") -> None:
    """Append one gate event. `outcome` is 'deny' (refusal), 'warn' (advisory, not a refusal) or 'pass'. Never raises.

    `class_key` (a `refusal_class(...)` key) is stored as `class` so recurrence counting
    is exact; absent, a deny's class is derived at read time (`event_class`)."""
    extra = {"kind": kind, "source": source}
    if class_key:
        extra["class"] = class_key
    try:
        _guard_module().log_event(
            gate, outcome, reason,
            {"tool_name": kind, "tool_input": {"command": target},
             "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID") or None},
            log_path=log_path or Path(os.environ["NOCTUS_GUARD_EVENT_LOG"])
            if os.environ.get("NOCTUS_GUARD_EVENT_LOG") else log_path,
            extra=extra,
        )
    except Exception as exc:  # telemetry must never change a verdict
        import sys
        print(f"gate_alignment: event write failed ({exc}); verdict unchanged", file=sys.stderr)


_FINDING_RE = re.compile(r"\[(?:critical|high|medium|warning|error)\]\s*(.+)")
_first_finding: list[str] = []


def first_finding_code(text: str) -> str:
    """Stable slug of the first `[severity] <file> - <issue>` line in a keeper's output ('' if none)."""
    for line in text.splitlines():
        m = _FINDING_RE.search(re.sub(r"\x1b\[[0-9;]*m", "", line))
        if m:
            body = m.group(1).split(" \u2014 ", 1)[-1]
            return _slug(body, words=5)
    return ""


class _Tee:
    """stdout wrapper that remembers the first finding line (cli.main installs it; verdict-neutral)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def write(self, data: str) -> int:
        if not _first_finding:
            code = first_finding_code(data)
            if code:
                _first_finding.append(code)
        return self._inner.write(data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def capture_first_finding() -> None:
    """Install the tee so `record_cli_exit` can name the first finding code. Idempotent; never raises."""
    import sys
    try:
        if not any(re.match(r"^--(check|verify)-", a) for a in sys.argv[1:]):
            return
        if not isinstance(sys.stdout, _Tee):
            sys.stdout = _Tee(sys.stdout)
    except Exception:  # pragma: no cover - telemetry only
        pass


def record_cli_exit(argv: list[str], code: Any, *, finding: str = "") -> None:
    """Called by cli.py on exit: log a `--check-*` / `--verify-*` gate run.

    A deny carries WHERE it fired (`NOC_HOOK_STAGE`: pre-commit|pre-push|ci|...) and WHAT it
    found (the first finding code) as `reason`/`target`, so refusals can be counted by class."""
    flags = [a for a in argv if re.match(r"^--(check|verify)-[a-z0-9-]+$", a)]
    if not flags:
        return
    ok = code in (None, 0)
    target = ""
    for i, a in enumerate(argv):
        if a == "--paths" and i + 1 < len(argv):
            target = argv[i + 1][:200]
    stage = os.environ.get("NOC_HOOK_STAGE", "").strip() or "manual"
    # An ADVISORY invocation (the pre-commit heads-up whose blocking twin runs in commit-msg) is a `warn`, never a
    # `deny`: logging it as a refusal double-counted every doc-staleness block (476 denies, 2026-11-14).
    outcome = "pass" if ok else ("warn" if os.environ.get("NOC_GATE_ADVISORY") else "deny")
    if not ok:
        finding = finding or (_first_finding[0] if _first_finding else "")
        target = target or f"stage:{stage}"
    for f in flags:
        gate = f"keeper:{f[2:]}"
        record_event(gate, outcome, kind="keeper", target=target,
                     reason="" if ok else f"stage={stage} code={finding or 'unknown'}", source="cli",
                     class_key="" if ok else refusal_class(gate, stage, finding or "unknown"))


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


# --------------------------------------------------------- refusal classes
_CLASS_MAX = 60


def _slug(text: str, *, words: int | None = None) -> str:
    """Stable, volatile-free slug: lowercase, hex shas / numbers / paths' numeric tails dropped."""
    t = re.sub(r"\b[0-9a-f]{7,40}\b", " ", str(text).lower())
    t = re.sub(r"\d+", " ", t)
    toks = [w for w in re.split(r"[^a-z0-9_*./:-]+", t) if w.strip("-:./")]
    if words:
        toks = toks[:words]
    return "-".join(toks).strip("-")[:_CLASS_MAX]


def refusal_class(gate: str, item: str, detail: str) -> str:
    """A stable key for a KIND of refusal, so the same wall is counted as one thing across sessions:
    `deliverable:head_pushed_clean:stale-request-head`, `mq:eject:conflict:<path-glob>`,
    `ci-parity:timeout:suite:product:social-wiring`, `guard:<name>:<first finding code>`.
    Empty parts are dropped; volatile tokens (shas, counts) never enter the key."""
    parts = [p for p in (str(gate).strip(), str(item).strip(), _slug(detail)) if p]
    return ":".join(parts)


def event_class(row: dict) -> str:
    """The class of a deny event: the stored `class`, else derived from gate + reason."""
    if row.get("class"):
        return str(row["class"])
    reason = str(row.get("reason") or "")
    m = re.search(r"stage=(\S+) code=(\S+)", reason)
    if m:
        return refusal_class(row.get("gate", ""), m.group(1), m.group(2))
    return refusal_class(row.get("gate", ""), "", re.sub(r"^\[noc-guard:[^\]]*\]\s*", "", reason))


def _parse_ts(ts: Any) -> _dt.datetime | None:
    try:
        d = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)


def class_events(key: str, *, window_days: float, events: list[dict] | None = None,
                 now: _dt.datetime | None = None) -> list[dict]:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=window_days)
    out = []
    for e in events if events is not None else read_events():
        if e.get("outcome") != "deny":
            continue
        t = _parse_ts(e.get("ts"))
        if t is not None and t >= cutoff and event_class(e) == key:
            out.append(e)
    return out


def gate_quiet(key: str, days: float = 7, *, events: list[dict] | None = None,
               now: _dt.datetime | None = None) -> bool:
    """True when the class has had no refusal for `days` (the `gate_quiet:<class>:7d` predicate)."""
    return not class_events(key, window_days=days, events=events, now=now)


def _open_fix(key: str, root: Path) -> str | None:
    """A live fix owner for the class: branch-tree pointer naming it, an in-progress gate-walls
    row, or a NOC-REMEDIATE[<key>] marker. None = nobody owns it."""
    import subprocess
    try:
        from tools.noctus.dev import branch_pointer as bp
        for branch, row in bp._latest_per_branch(bp._read_local_ledger()).items():
            if row.get("status") in bp.TERMINAL_STATUSES:
                continue
            if key in f"{row.get('brief', '')} {row.get('notes', '')}":
                return f"pointer:{branch}"
    except Exception:  # noqa: BLE001 - ownership lookup must not break the count
        pass
    gate = key.split(":", 1)[0]
    try:
        from tools.noctus.dev import findings_ledger as gl
        from tools.noctus.dev import gate_wall_findings  # noqa: F401  (registers the ledger)
        for r in gl.load(gl.get("gate-walls"), root).values():
            if r.get("status") == "in-progress" and (key in json.dumps(r) or r.get("target") == gate):
                return f"findings:{r.get('id', 'gate-walls')}"
    except Exception:  # noqa: BLE001
        pass
    try:
        r = subprocess.run(["git", "grep", "-lF", f"NOC-REMEDIATE[{key}]"], cwd=root,
                           capture_output=True, text=True, timeout=30)
        hit = (r.stdout.split() or [""])[0]
        if hit:
            return f"marker:{hit}"
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def refusal_recurrence(keys: list[str], *, window_days: int = 14, root: Path | None = None,
                       events: list[dict] | None = None) -> list[dict]:
    """For each class key: how often it refused in the window, across how many sessions, and who (if
    anyone) owns the fix. `open_fix` is None when the class recurs with no live fix."""
    root = root or REPO_ROOT
    evs = events if events is not None else read_events()
    out = []
    for key in dict.fromkeys(keys):
        hits = class_events(key, window_days=window_days, events=evs)
        out.append({"class": key, "n_14d": len(hits),
                    "sessions": len({h.get("session") for h in hits if h.get("session")}),
                    "open_fix": _open_fix(key, root)})
    return out


def all_classes(*, window_days: int = 14, events: list[dict] | None = None) -> list[str]:
    evs = events if events is not None else read_events()
    seen: dict[str, None] = {}
    for e in class_events_all(evs, window_days):
        seen[event_class(e)] = None
    return list(seen)


def class_events_all(events: list[dict], window_days: float) -> list[dict]:
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=window_days)
    return [e for e in events if e.get("outcome") == "deny"
            and (t := _parse_ts(e.get("ts"))) is not None and t >= cutoff]


def unowned_classes(root: Path | None = None, *, min_n: int = 3, window_days: int = 14,
                    events: list[dict] | None = None) -> list[dict]:
    """Classes refused >= `min_n` times in the window with no open fix (keeper `check_refusal_classes_owned`)."""
    evs = events if events is not None else read_events()
    rows = refusal_recurrence(all_classes(window_days=window_days, events=evs), window_days=window_days,
                              root=root, events=evs)
    return [r for r in rows if r["n_14d"] >= min_n and not r["open_fix"]]


def trend(*, days: int = 7, events: list[dict] | None = None,
          now: _dt.datetime | None = None) -> dict:
    """Refusals this window vs the previous one, by class (worst delta first)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    evs = events if events is not None else read_events()
    this: dict[str, int] = {}
    last: dict[str, int] = {}
    for e in evs:
        if e.get("outcome") != "deny":
            continue
        t = _parse_ts(e.get("ts"))
        if t is None:
            continue
        age = (now - t).total_seconds() / 86400
        bucket = this if 0 <= age < days else last if days <= age < 2 * days else None
        if bucket is not None:
            c = event_class(e)
            bucket[c] = bucket.get(c, 0) + 1
    rows = [{"class": c, "this": this.get(c, 0), "last": last.get(c, 0), "delta": this.get(c, 0) - last.get(c, 0)}
            for c in set(this) | set(last)]
    rows.sort(key=lambda r: (-r["delta"], -r["this"], r["class"]))
    return {"window_days": days, "this_total": sum(this.values()), "last_total": sum(last.values()), "classes": rows[:30]}


def sync_refusal_rows(root: Path | None = None, *, min_n: int = 2, window_days: int = 14,
                      events: list[dict] | None = None) -> dict:
    """One auto-improvement row per recurring class (N>=min_n), count updated in place, self-closing on quiet."""
    from tools.noctus.dev import auto_improvement as ai
    evs = events if events is not None else read_events()
    synced = []
    for r in refusal_recurrence(all_classes(window_days=window_days, events=evs), window_days=window_days,
                                root=root, events=evs):
        if r["n_14d"] >= min_n:
            res = ai.upsert_class_row(key=r["class"], count=r["n_14d"], sessions=r["sessions"],
                                      target=r["class"].split(":", 1)[0] or "gate",
                                      description=f"Refusal class `{r['class']}` recurs: no fix owner yet." if not r["open_fix"]
                                      else f"Refusal class `{r['class']}` recurs; fix owner: {r['open_fix']}.",
                                      agent="gate_alignment")
            synced.append({"class": r["class"], "n": r["n_14d"], "action": res.get("action")})
    return {"synced": synced}


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
    ensure_not_shared_primary(root, 'gate_alignment.refresh_baseline')
    inv = load_inventory(root).get("gates", {})
    base = load_baseline(root).get("undeclared_mechanism", [])
    kept = [g for g in base if g in inv and not mechanism_ok(inv[g].get("mechanism"))]
    (root / BASELINE_REL).write_text(json.dumps({"undeclared_mechanism": sorted(kept)}, indent=1) + "\n")
    return {"before": len(base), "after": len(kept)}


def declare_gate(gate: str, mechanism: str, owner: str, *, standard: str = "",
                 placement: str = "warn", source: str = "", existing: bool = False,
                 root: Path | None = None) -> dict:
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
                "standard": standard or row.get("standard", ""), "new": False if existing else row.get("new", gate not in inv["gates"]),
                "declared": _dt.date.today().isoformat()})
    if source:
        row["source"] = source
    if placement == "blocking" and row["new"]:
        row.setdefault("shadow", None)
    inv["gates"][gate] = row
    _write_inventory(root, inv)
    return {"ok": True, "gate": gate, "row": row}


def _write_inventory(root: Path, inv: dict) -> None:
    ensure_not_shared_primary(root, 'gate_alignment.declare')
    inv["gates"] = dict(sorted(inv["gates"].items()))
    (root / INVENTORY_REL).write_text(json.dumps(inv, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------- decision coverage matrix
_LEGS = ("home", "construction", "gate", "telemetry", "branch")


# ── git merge driver logic (pure) ─────────────────────────────────────────
def _decision_num(d: dict) -> int:
    m = re.fullmatch(r"D(\d+)", str(d.get("id", "")))
    return int(m.group(1)) if m else 0


def _same_decision(a: dict, b: dict) -> bool:
    """Same decision added twice: identical content (ids aside) or same gate + decision text."""
    strip = lambda d: {k: v for k, v in d.items() if k != "id"}  # noqa: E731
    return strip(a) == strip(b) or (
        bool(a.get("gate")) and a.get("gate") == b.get("gate") and a.get("decision") == b.get("decision"))


def merge_inventory(base: str, ours: str, theirs: str) -> tuple[str, bool, list[str]]:
    """3-way merge of `gate-alignment-inventory.json`. Returns (text, conflicted, notes).

    * `gates`: union; a key changed differently on both sides is a conflict
      (ours kept in the output, `conflicted=True`). Output sorted.
    * `decisions`: ours + theirs' entries whose id is not in base. A theirs entry
      that duplicates one already present (identical content, or same gate +
      decision text) is dropped; one whose id collides with a different decision
      is renumbered past the current max. Base entries changed on one side only
      take that side (deleted on one side + unchanged on the other: deleted).
    * other top-level keys: ordinary 3-way (both sides differ => conflict, ours kept).
    * Output format = `_write_inventory` (indent=1, ensure_ascii=False, trailing newline).
    """
    def load(t: str) -> dict:
        return json.loads(t) if t.strip() else {}
    b, o, t = load(base), load(ours), load(theirs)
    conflicted, notes = False, []

    def three(bv: Any, ov: Any, tv: Any, what: str) -> Any:
        nonlocal conflicted
        if ov == tv or tv == bv:
            return ov
        if ov == bv:
            return tv
        conflicted = True
        notes.append(f"conflict: {what} changed differently on both sides")
        return ov

    out: dict[str, Any] = {}
    for k in [*o, *[k for k in t if k not in o]]:
        if k in ("gates", "decisions"):
            continue
        v = three(b.get(k), o.get(k), t.get(k), f"top-level key {k!r}")
        if v is not None:
            out[k] = v

    bg, og, tg = b.get("gates", {}), o.get("gates", {}), t.get("gates", {})
    gates: dict[str, Any] = {}
    for g in sorted({*bg, *og, *tg}):
        v = three(bg.get(g), og.get(g), tg.get(g), f"gate {g!r}")
        if v is not None:
            gates[g] = v
    out["gates"] = gates

    bd = {d.get("id"): d for d in b.get("decisions", [])}
    td = {d.get("id"): d for d in t.get("decisions", [])}
    decisions: list[dict] = []
    for d in o.get("decisions", []):
        i = d.get("id")
        if i in bd and i not in td:  # theirs deleted it
            if d == bd[i]:
                continue
        elif i in bd:
            d = three(bd[i], d, td[i], f"decision {i}")
        decisions.append(d)
    for d in t.get("decisions", []):
        if d.get("id") in bd:
            continue
        if any(_same_decision(d, x) for x in decisions):
            notes.append(f"dedup: {d.get('id')} already present on the other side")
            continue
        if any(x.get("id") == d.get("id") for x in decisions):
            new = f"D{max(_decision_num(x) for x in decisions) + 1}"
            notes.append(f"renumber: incoming {d.get('id')} -> {new}")
            d = {**d, "id": new}
        decisions.append(d)
    out["decisions"] = decisions
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n", conflicted, notes


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
            "markdown. action=refresh-baseline: shrink-only. action=trend: refusals this week vs last, by class. "
            "action=refusals: recurrence by class (n_14d, sessions, open_fix); file=true upserts ONE auto-improvement row per "
            "class at N>=2 (self-closing on gate_quiet). Read-only except file/declare/render/refresh-baseline."
        ),
    )
    def _gate_alignment(action: str = "walls", gate: str = "", mechanism: str = "", owner: str = "",
                        placement: str = "warn", file: bool = False, existing: bool = False,
                        worktree_path: str = "") -> dict:
        return run_action(action, gate=gate, mechanism=mechanism, owner=owner, placement=placement,
                          file=file, existing=existing, root=Path(worktree_path) if worktree_path else None)


def run_action(action: str, *, gate: str = "", mechanism: str = "", owner: str = "",
               placement: str = "warn", file: bool = False, existing: bool = False,
               root: Path | None = None) -> dict:
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
        return declare_gate(gate, mechanism, owner, placement=placement, existing=existing, root=root)
    if action == "sources":
        return sources_report(root)
    if action == "matrix":
        fails, findings = matrix_issues(root)
        return {"ok": not fails, "issues": fails, "pending_findings": findings, "table": render_matrix(root)}
    if action == "render":
        ensure_not_shared_primary(root, 'gate_alignment.render')
        (root / RENDERED_REL).write_text(render_markdown(root) + "\n## Decision coverage matrix\n\n" + render_matrix(root), encoding="utf-8")
        return {"ok": True, "path": str(RENDERED_REL)}
    if action == "refresh-baseline":
        return {"ok": True, **refresh_baseline(root)}
    if action == "trend":
        return {"ok": True, **trend()}
    if action == "refusals":
        recur = refusal_recurrence(all_classes(), root=root)
        out = {"ok": True, "classes": sorted(recur, key=lambda r: -r["n_14d"])[:30],
               "unowned": [r["class"] for r in recur if r["n_14d"] >= 3 and not r["open_fix"]]}
        if file:
            out["synced"] = sync_refusal_rows(root)["synced"]
        return out
    return {"ok": False, "error": f"unknown action {action!r}; one of walls|triad|matrix|sources|declare|render|refresh-baseline|trend|refusals"}


__all__ = ["record_event", "record_cli_exit", "read_events", "scan_gates", "triad_issues", "walls_report",
           "gate_stats", "refusal_class", "refusal_recurrence", "unowned_classes", "trend", "declare_gate", "burn_down", "run_action", "register"]
