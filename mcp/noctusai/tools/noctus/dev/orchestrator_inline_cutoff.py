"""Orchestrator inline cutoff - the build triad for "the maestro dispatches, it does not play every instrument".

WHY (owner, 2026-11-07): the tech-lead built 2 of 4 accountant slices inline and
did the tax research inline instead of dispatching the `accountant` advisor.
The rule existed as discipline only (KB § PATTERNS/architect/parallelization-first-orchestration.md
§ Inline-deving; first recurrence 2026-06-03) and recurred. Discipline that
recurs gets the triad (KB § PATTERNS/common/gate-methodology-sync.md):

* CONSTRUCTION - `release_steward action=request` measures the delivery against
  its fork base; over the cutoff it wants `inline_reason` (closed set) + a note,
  recorded on the branch-tree pointer. Shadow period: a missing reason is a
  WARNING naming the specialists to dispatch, never a refusal.
* BACKSTOP - keeper `check_orchestrator_inline_over_cutoff` (compliance.py).
* TELEMETRY - an auto-improvement drift row `orchestrator_inline_over_cutoff:<branch>`
  per unexplained over-cutoff inline delivery (self-closing on the recorded reason).

Pure functions with injection seams (runner / size_fn / record / log); nothing
here patches a guard. A pointer whose role is `engineer` is a dispatched worker,
not orchestrator inlining, and is excluded; so are merge trains and tool-written
migration records (orchestrator machinery, authored elsewhere).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

PATTERN_DOC = "KB § CONTEXT/PATTERNS/architect/parallelization-first-orchestration.md (Enforcement)"

CUTOFF_LOC = 100
CUTOFF_FILES = 3
SHADOW_SINCE = "2026-11-07"
MIN_NOTE_CHARS = 10

# Pointer agents meaning "the orchestrator did the work itself". compliance.py imports
# this as _SLICE_INLINE_AGENTS so the slice-scored keeper and this one never drift.
INLINE_AGENTS = frozenset({"self-branch", "tech-lead", "tech-lead-inline", "orchestrator", "orchestrator-operator"})
LANDED_OR_DELIVERED = frozenset({"integrated-worktree-live", "shipped"})

REASONS = {
    "orchestrator_owned": "git, merge, deploy, live DB/DNS mutation, cross-engineer conflict resolution",
    "single_coherent_voice": "methodology/doc work that needs one voice",
    "shared_state": "the work cannot be split without sharing mutable state",
    "owner_directed": "the owner explicitly asked for the orchestrator to do it inline",
}

# Orchestrator machinery whose diff is other people's work or tool output: merge trains
# (task_branch action=train) and record_applied_migrations rows.
_MACHINERY_BRANCH = re.compile(r"^(feat/)?(train-|applied-record)")

# Derived / generated paths never count toward size.
_DERIVED = re.compile(
    r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|uv\.lock)$"
    r"|^project-history/|^templates/product-seed/|\.snap$|(^|/)dist/"
    r"|migrations-applied\.json$|products/[^/]+/docker-compose\.yml$|products/[^/]+/backend/Dockerfile$"
    r"|^deploy/fleet/[^/]*\.txt$|_version_static\.py$|^\.claude/worktrees/|baseline[^/]*\.json$"
)

# path pattern -> specialists from .claude/agents/ who should have been dispatched
_SPECIALISTS: tuple[tuple[str, str], ...] = (
    (r"^(mcp/|scripts/|\.claude/(skills|agents|commands)/)", "tooling-engineer"),
    (r"^(products/[^/]+/frontend/|seed/lib/frontend/|seed/framework/frontend/)", "frontend-engineer"),
    (r"^(products/[^/]+/backend/|seed/lib/backend/|seed/framework/backend/)", "backend-engineer"),
    (r"^(deploy/|\.github/)|Dockerfile|docker-compose", "devops-engineer"),
    (r"/(finance|tax)/|br-tax", "accountant (read-only advisor)"),
    (r"^KNOWLEDGE-BASE/", "architect (read-only advisor)"),
    (r"(^|/)tests?/|\.test\.|(^|/)test_", "test-engineer"),
)

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def measure(numstat_text: str) -> dict[str, Any]:
    """``{loc, files, paths}`` over the authored (non-derived) paths of a ``git diff --numstat``."""
    loc, paths = 0, []
    for ln in numstat_text.splitlines():
        parts = ln.split("\t", 2)
        if len(parts) != 3 or _DERIVED.search(parts[2]):
            continue
        a, d, f = parts
        loc += (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)
        paths.append(f)
    return {"loc": loc, "files": len(paths), "paths": paths}


def is_over(loc: int, files: int) -> bool:
    """The inline cutoff is ``<100 LoC and <3 files``; at or past either bound is over."""
    return loc >= CUTOFF_LOC or files >= CUTOFF_FILES


def specialists_for(paths: list[str]) -> list[str]:
    seen: list[str] = []
    for pat, who in _SPECIALISTS:
        if any(re.search(pat, p) for p in paths) and who not in seen:
            seen.append(who)
    return seen or ["the matching specialist in .claude/agents/ (noctus.dev.brief_route_to_agent picks one)"]


def validate_reason(reason: str | None, note: str | None) -> str | None:
    """Error text, or None when ``reason``/``note`` satisfy the closed set."""
    if reason not in REASONS:
        return f"inline_reason must be one of {sorted(REASONS)}; got {reason!r}"
    if len((note or "").strip()) < MIN_NOTE_CHARS:
        return f"inline_note must say why in >= {MIN_NOTE_CHARS} chars"
    return None


def is_inline_pointer(row: dict) -> bool:
    return ((row.get("agent") or "") in INLINE_AGENTS and (row.get("role") or "") != "engineer"
            and not _MACHINERY_BRANCH.match(str(row.get("branch") or "")))


def warning_text(branch: str, loc: int, files: int, paths: list[str]) -> str:
    return (
        f"inline over the cutoff: '{branch}' changes {loc} LoC across {files} files (cutoff: "
        f"<{CUTOFF_LOC} LoC and <{CUTOFF_FILES} files) with no inline_reason. The orchestrator conducts - "
        f"dispatch {', '.join(specialists_for(paths))}; advisor work (research, legal/tax, design, security) "
        f"goes to read-only Agent calls, no worktree. If inline was right, state inline_reason="
        f"{'|'.join(sorted(REASONS))} plus inline_note (>= {MIN_NOTE_CHARS} chars). Shadow period: warning only. "
        f"{PATTERN_DOC}."
    )


def _git(root: Path, args: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)


def base_sha(row: dict) -> str | None:
    m = re.search(r"@([0-9a-f]{7,40})", str(row.get("base") or ""))
    return m.group(1) if m else None


def evaluate_pointer(row: dict, *, root: Path, runner: Runner | None = None) -> dict[str, Any] | None:
    """Measure a pointer's delivery against its fork base; None when unmeasurable (never a verdict)."""
    base, head = base_sha(row), row.get("commit")
    if not base or not head:
        return None
    p = (runner or (lambda a: _git(root, a)))(["diff", "--numstat", base, str(head)])
    return measure(p.stdout) if p.returncode == 0 else None


def scan(rows: list[dict], *, root: Path, since: str = SHADOW_SINCE, runner: Runner | None = None,
         size_fn: Callable[[dict], dict[str, Any] | None] | None = None) -> list[dict]:
    """Latest-per-branch inline pointers delivered on/after ``since``, over the cutoff,
    with no valid recorded ``inline_reason``."""
    from tools.noctus.dev import branch_pointer as bp

    size = size_fn or (lambda r: evaluate_pointer(r, root=root, runner=runner))
    out: list[dict] = []
    for branch, row in sorted(bp._latest_per_branch(rows).items()):
        if row.get("status") not in LANDED_OR_DELIVERED or not is_inline_pointer(row):
            continue
        if str(row.get("ts", ""))[:10] < since:
            continue
        if row.get("inline_reason") and validate_reason(row.get("inline_reason"), row.get("inline_note")) is None:
            continue
        m = size(row)
        if m is None or not is_over(m["loc"], m["files"]):
            continue
        out.append({"branch": branch, "agent": row.get("agent"), "loc": m["loc"], "files": m["files"],
                    "paths": m["paths"], "session": row.get("session")})
    return out


def issue_for(f: dict) -> dict:
    return {"product": "<platform>", "file": "project-history/branch-tree.ndjson",
            "issue": warning_text(f["branch"], f["loc"], f["files"], f["paths"]), "severity": "warning"}


def log_telemetry(findings: list[dict]) -> dict[str, Any]:
    """One open auto-improvement drift row per unexplained over-cutoff branch (deduped)."""
    from tools.noctus.dev import auto_improvement as ai

    logged: list[str] = []
    errors: list[str] = []
    for f in findings:
        target = f"orchestrator_inline_over_cutoff:{f['branch']}"
        if any(e.get("target") == target for e in ai.query(target=target, kind="drift", open_only=True,
                                                           skip_reconcile=True)):
            continue
        out = ai.log_entry(
            scope="scoped", kind="drift", target=target, agent="tech-lead",
            description=(f"{f['branch']} landed inline: {f['loc']} LoC / {f['files']} files, no inline_reason. "
                         f"Dispatch next time: {', '.join(specialists_for(f['paths']))}. {PATTERN_DOC}"),
            resolve_when=f"inline_reason_recorded:{f['branch']}", source_ref="orchestrator_inline_cutoff",
        )
        (logged if out.get("ok") else errors).append(f["branch"] if out.get("ok") else f"{f['branch']}: {out.get('error')}")
    return {"logged": logged, "errors": errors}


def gate_delivery(branch: str, *, pointer: dict | None, inline_reason: str | None, inline_note: str | None,
                  root: Path, runner: Runner | None = None, record: Callable[..., dict] | None = None,
                  log: Callable[[list[dict]], dict] | None = None) -> dict[str, Any]:
    """The construction leg, called by release_steward ``request``. Never raises, never refuses
    (shadow): returns ``{applicable, over, loc, files, warnings, recorded, telemetry}``."""
    if pointer is None or not is_inline_pointer(pointer):
        return {"applicable": False}
    try:
        m = evaluate_pointer(pointer, root=root, runner=runner)
    except Exception as exc:  # noqa: BLE001 - loud, never a refusal
        return {"applicable": True, "over": None, "warnings": [f"inline cutoff unmeasured: {exc}"]}
    if m is None:
        return {"applicable": True, "over": None,
                "warnings": ["inline cutoff unmeasured: the pointer's base/commit do not resolve in this tree"]}
    over = is_over(m["loc"], m["files"])
    out: dict[str, Any] = {"applicable": True, "over": over, "loc": m["loc"], "files": m["files"]}
    if not over:
        return out
    if not (inline_reason or inline_note):
        out["warnings"] = [warning_text(branch, m["loc"], m["files"], m["paths"])]
        out["telemetry"] = (log or log_telemetry)([{"branch": branch, **m}])
        return out
    err = validate_reason(inline_reason, inline_note)
    if err is None:
        out["recorded"] = (record or _record_on_pointer)(branch, inline_reason, inline_note)
    else:
        out["warnings"] = [f"{err}. {warning_text(branch, m['loc'], m['files'], m['paths'])}"]
    return out


def _record_on_pointer(branch: str, reason: str | None, note: str | None) -> dict[str, Any]:
    from tools.noctus.dev import branch_pointer as bp

    r = bp.update(branch=branch, inline_reason=reason, inline_note=note)
    return {"ok": bool(r.get("ok")), "error": r.get("error")}


__all__ = ["REASONS", "INLINE_AGENTS", "CUTOFF_LOC", "CUTOFF_FILES", "SHADOW_SINCE", "measure", "is_over",
           "validate_reason", "scan", "gate_delivery", "log_telemetry", "issue_for", "specialists_for",
           "warning_text", "evaluate_pointer", "is_inline_pointer"]
