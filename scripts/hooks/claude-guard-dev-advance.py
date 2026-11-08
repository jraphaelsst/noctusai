#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit + PostToolUse hook — tell a session when `origin/dev`
ADVANCED under it in a way that matters to it (receiver-side change propagation).

**Why (2026-11-07).** A peer's HEADS-UP is a voluntary message a busy/idle/refusing session
may never read; the first sign of a landed methodology change or of a change to a file in
one's own claimed paths was the merge queue ejecting the branch. A message points at state
(KB § PATTERNS/architect/orchestration-craft-canon.md §6.2) - this hook is the PULL leg that
reads the state. KB § PATTERNS/architect/orchestration-craft-canon.md §6.13.

**Mechanism.** Per session (state under `~/.noctus/dev-advance-seen.json`) remember the
`origin/dev` sha last seen. When the LOCAL ref moved, diff seen..current and inject
`additionalContext` ONLY if the advance touched (a) a methodology surface, or (b) a path
overlapping this session's `on_going` branch-pointer `paths` (latest row per branch on the
local `origin/ledgers` ref; own session or own worktree) or its worktree's diff vs dev.
Anything else only moves the baseline, silently.

**Refs are local - no network.** The hook never fetches. `origin/dev` is shared by every
worktree of the clone and is advanced by the SessionStart sweep, `task_branch`, the merge
queue and any peer's fetch; a landing nobody has fetched yet is invisible until one does
(documented limit).

ADVISORY: never blocks, always exits 0, fails OPEN, 1.5 s self-deadline, scans throttled.
Telemetry: one `guard-events.ndjson` row per injection (guard=dev-advance).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

GUARD = "dev-advance"
SCAN_EVERY_S = 30
MAX_FILES_SHOWN = 12
METHODOLOGY_PREFIXES = (
    "CLAUDE.md", "CLAUDE/", "KNOWLEDGE-BASE/CONTEXT/PATTERNS/", ".claude/agents/", ".claude/skills/",
    ".claude/commands/", "scripts/hooks/", ".claude/settings.json",
)
SOURCE = "KB § PATTERNS/architect/orchestration-craft-canon.md §6.13"


def _git(repo: str, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=1.0)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def is_methodology(path: str) -> bool:
    return path.startswith(METHODOLOGY_PREFIXES)


def paths_overlap(a: str, b: str) -> bool:
    a, b = a.strip("/"), b.strip("/")
    return bool(a and b) and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))


def own_pointer_paths(ledger_text: str, session_id: str, worktree_rel: str | None) -> list[str]:
    """`paths` of this session's live pointers: latest row per branch, status on_going."""
    latest: dict[str, dict] = {}
    for line in ledger_text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("branch"):
            latest[row["branch"]] = row
    out: list[str] = []
    for row in latest.values():
        if row.get("status") != "on_going":
            continue
        if row.get("session") == session_id or (worktree_rel and row.get("worktree") == worktree_rel):
            out.extend(p for p in (row.get("paths") or []) if isinstance(p, str))
    return out


def analyse(repo: str, seen: str, cur: str, ledger_text: str, session_id: str,
            worktree_rel: str | None, my_diff: list[str]) -> dict | None:
    """Pure-ish core: returns the report dict, or None when the advance is irrelevant."""
    files = (_git(repo, "diff", "--name-only", seen, cur) or "").splitlines()
    if not files:
        return None
    mine = own_pointer_paths(ledger_text, session_id, worktree_rel) + my_diff
    method = [f for f in files if is_methodology(f)]
    overlap = sorted({f for f in files if any(paths_overlap(f, m) for m in mine)})
    if not method and not overlap:
        return None
    commits = (_git(repo, "log", "--format=%h %s", f"{seen}..{cur}", "--", *(method + overlap)[:40]) or "").splitlines()
    return {"methodology": method, "overlap": overlap, "commits": commits[:8]}


def format_report(rep: dict, seen: str, cur: str) -> str:
    def lst(fs):
        shown = ", ".join(fs[:MAX_FILES_SHOWN])
        return shown + (f" (+{len(fs) - MAX_FILES_SHOWN} more)" if len(fs) > MAX_FILES_SHOWN else "")
    parts = [f"[noc-guard:{GUARD}] origin/dev advanced {seen[:9]}..{cur[:9]} under this session."]
    if rep["methodology"]:
        parts.append("METHODOLOGY changed - re-read before acting on a cached copy of it: " + lst(rep["methodology"]) + ".")
    if rep["overlap"]:
        parts.append("Landed changes to files in YOUR claimed paths / branch diff: " + lst(rep["overlap"])
                     + ". Rebase onto origin/dev and re-check before you enqueue.")
    if rep["commits"]:
        parts.append("Commits: " + "; ".join(rep["commits"]) + ".")
    parts.append("This is information, not a stop order: you know your own environment - adopt now, finish the current step first, "
                 "rebase, or ignore if unaffected; decide how to proceed, no need to wait for the owner. "
                 "If it conflicts with your work or breaks something (a collision with your paths, a broken assumption, "
                 "a failing test), reply to the sender/steward (SendMessage) and resolve it together - silence is not OK. " + SOURCE)
    return " ".join(parts)


def _state_path() -> Path:
    return Path(os.environ.get("NOCTUS_DEV_ADVANCE_STATE") or Path.home() / ".noctus" / "dev-advance-seen.json")


def run(payload: dict, repo: str, now: float | None = None) -> str | None:
    if payload.get("agent_id"):
        return None
    sid = payload.get("session_id")
    if not sid:
        return None
    now = time.time() if now is None else now
    cur = _git(repo, "rev-parse", "--verify", "-q", "refs/remotes/origin/dev")
    if not cur:
        return None
    sp = _state_path()
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    mine = state.get(sid) if isinstance(state.get(sid), dict) else {}
    seen = mine.get("sha")
    event = payload.get("hook_event_name")
    if seen and event != "SessionStart" and now - float(mine.get("last_scan", 0)) < SCAN_EVERY_S:
        return None
    text = None
    if seen and seen != cur and event != "SessionStart":
        if _git(repo, "rev-parse", "-q", "--verify", f"{seen}^{{commit}}"):
            cwd = payload.get("cwd") or repo
            top = _git(cwd, "rev-parse", "--show-toplevel") or repo
            wt_rel = os.path.relpath(top, repo) if top != repo else None
            my_diff = (_git(cwd, "diff", "--name-only", "origin/dev...HEAD") or "").splitlines()
            ledger = _git(repo, "show", "refs/remotes/origin/ledgers:branch-tree.ndjson") or ""
            rep = analyse(repo, seen, cur, ledger, sid, wt_rel, my_diff)
            if rep:
                text = format_report(rep, seen, cur)
                from _guard_failclosed import log_event
                log_event(GUARD, "warn", f"{seen[:9]}..{cur[:9]} methodology={len(rep['methodology'])} overlap={len(rep['overlap'])}",
                          payload, extra={"kind": "advisory", "owner": "tooling-engineer", "source": SOURCE,
                                          "methodology_files": len(rep["methodology"]), "overlap_files": len(rep["overlap"])})
    state[sid] = {"sha": cur, "last_scan": now}
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, sp)
    except OSError as exc:
        print(f"claude-guard-{GUARD}: state write failed ({exc})", file=sys.stderr)
    return text


def main() -> int:
    try:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
        signal.setitimer(signal.ITIMER_REAL, 1.5)
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            repo = str(Path(__file__).resolve().parents[2])
            text = run(payload, repo)
            if text:
                print(text, file=sys.stderr)
                json.dump({"hookSpecificOutput": {"hookEventName": payload.get("hook_event_name") or "UserPromptSubmit",
                                                  "additionalContext": text}}, sys.stdout)
    except BaseException as exc:  # noqa: BLE001 - fail OPEN
        print(f"claude-guard-{GUARD}: unavailable ({type(exc).__name__}) - not blocking", file=sys.stderr)
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
