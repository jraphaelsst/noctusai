#!/usr/bin/env python3
"""PostToolUse + UserPromptSubmit hook — surface background agents of THIS session
that handed back but are still held by the harness (the idle-agent footer).

**Why (2026-11-07).** The leader's footer showed 4 subagents + 23 shells "running"
~1h20m after each agent had handed back: the harness keeps a finished background
agent (and its shell tasks) until the leader calls `TaskStop`. Rule + salvage legs:
KB § PATTERNS/common/background-agent-lifecycle.md.

**Detection (verified on real transcripts 2026-11-07).** The session tasks dir
`/private/tmp/claude-<uid>/<project>/<session-id>/tasks/<agentId>.output` is a symlink to
`~/.claude/projects/<project>/<session-id>/subagents/agent-<agentId>.jsonl`; beside it
sits `agent-<agentId>.meta.json` whose `finished: true` is written when the agent's run
ended (a running agent has no such key). An agent is REPORTED when finished, quiet for
>= GRACE_S, and the leader transcript holds no `TaskStop` and no `[Subagent hand-back]` (from=<id>) for its id
(a delivered hand-back = released by the harness). Scope is the
payload's own `session_id`, so a peer session's agents are never seen (owner rule: never
stop another session). Hooks that fire INSIDE a subagent (payload has `agent_id`) skip.

ADVISORY BY CONSTRUCTION: never stops anything (the leader acts), always exits 0, fails
OPEN on any error, self-limits to DEADLINE_S, throttles scans per session.
Telemetry: one `guard-events.ndjson` row per reported agent (guard=background-agent-idle).
"""
from __future__ import annotations

import glob
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

GUARD = "background-agent-idle"
GRACE_S = 180          # a just-finished agent still gets its hand-back read + salvaged
MAX_AGE_S = 24 * 3600  # older leftovers belong to a previous session's cleanup
SCAN_EVERY_S = 45      # throttle: the hook runs after every tool call
REMIND_S = 20 * 60     # re-report a still-unstopped agent
DEADLINE_S = 1.5


def _state_path() -> Path:
    from _guard_failclosed import _primary_root
    return Path(os.environ.get("NOCTUS_BG_AGENT_STATE")
                or _primary_root() / ".claude" / "cache" / "background-agent-idle-state.json")


def tasks_dirs(session_id: str) -> list[Path]:
    override = os.environ.get("NOCTUS_AGENT_TASKS_DIR")
    if override:
        return [Path(override)]
    uid = os.getuid()
    pats = [f"/private/tmp/claude-{uid}/*/{session_id}/tasks", f"/tmp/claude-{uid}/*/{session_id}/tasks"]
    seen: set[str] = set()
    out: list[Path] = []
    for pat in pats:  # /tmp and /private/tmp are one directory (macOS symlink): dedupe by realpath
        for p in sorted(glob.glob(pat)):
            rp = os.path.realpath(p)
            if rp not in seen:
                seen.add(rp)
                out.append(Path(p))
    return out


def stopped_ids(transcript_path: str | None, ids: list[str]) -> set[str]:
    """Ids the leader already `TaskStop`ped (a line holding both the tool name and the id), or whose
    `TaskStop` came back `No task found with ID: <id>` (the harness already released that agent:
    nothing left to stop, so it must not be re-reported)."""
    if not transcript_path or not ids:
        return set()
    found: set[str] = set()
    try:
        with open(transcript_path, "rb") as fh:
            for line in fh:
                if b"TaskStop" not in line and b"No task found with ID" not in line:
                    continue
                for i in ids:
                    if i.encode() in line:
                        found.add(i)
    except OSError:
        return set()
    return found


HANDBACK_MARK = b"[Subagent hand-back]"


def handed_back_ids(transcript_path: str | None, ids: list[str]) -> set[str]:
    """Ids whose `[Subagent hand-back]` the leader already received (`from=\\"<id>\\"` /
    `"from":"<id>"` on a marked line): the harness released those agents - not held, not idle."""
    if not transcript_path or not ids:
        return set()
    found: set[str] = set()
    try:
        with open(transcript_path, "rb") as fh:
            for line in fh:
                if HANDBACK_MARK not in line:
                    continue
                for i in ids:
                    b = i.encode()
                    if b'from=\\"' + b + b'\\"' in line or b'"from":"' + b + b'"' in line:
                        found.add(i)
    except OSError:
        return set()
    return found


def find_idle(session_id: str, transcript_path: str | None, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    cands: list[dict] = []
    for d in tasks_dirs(session_id):
        for out in sorted(d.glob("*.output")):
            try:
                jsonl = Path(os.path.realpath(out))
                meta = jsonl.with_name(jsonl.name[:-len(".jsonl")] + ".meta.json")
                if jsonl.suffix != ".jsonl" or not meta.is_file():
                    continue
                md = json.loads(meta.read_text(encoding="utf-8"))
                if md.get("finished") is not True:
                    continue
                idle_s = now - jsonl.stat().st_mtime
                if not GRACE_S <= idle_s <= MAX_AGE_S:
                    continue
                cands.append({"agent_id": out.stem, "agent_type": md.get("agentType"),
                              "description": md.get("description"), "idle_s": int(idle_s)})
            except (OSError, ValueError):
                continue
    ids = [c["agent_id"] for c in cands]
    done = stopped_ids(transcript_path, ids) | handed_back_ids(transcript_path, ids)
    return [c for c in cands if c["agent_id"] not in done]


def format_report(idle: list[dict]) -> str:
    def fmt(c):
        return f"{c['agent_id']} ({c.get('agent_type') or '?'}, idle {c['idle_s'] // 60}m: {(c.get('description') or '')[:50]})"
    return (
        f"[noc-guard:{GUARD}] {len(idle)} background agent(s) of THIS session handed back but are still held "
        "(footer shows them as running): " + "; ".join(fmt(c) for c in idle[:8]) + ". "
        "Leader: salvage each (work + learnings), take over any leftover (verdict/push/queued run), then "
        "`TaskStop` it now. Own dispatched agents ONLY - never a peer session. Already stopped? ignore. "
        "KB § PATTERNS/common/background-agent-lifecycle.md"
    )


def run(payload: dict, now: float | None = None) -> str | None:
    """Return the report text (or None). Updates throttle/remind state and appends telemetry."""
    if payload.get("agent_id"):  # fired inside a subagent
        return None
    sid = payload.get("session_id")
    if not sid:
        return None
    now = time.time() if now is None else now
    sp = _state_path()
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    mine = state.get(sid) if isinstance(state.get(sid), dict) else {}
    if now - float(mine.get("last_scan", 0)) < SCAN_EVERY_S:
        return None
    mine["last_scan"] = now
    reported = mine.setdefault("reported", {})
    idle = [c for c in find_idle(sid, payload.get("transcript_path"), now)
            if now - float(reported.get(c["agent_id"], 0)) >= REMIND_S]
    for c in idle:
        reported[c["agent_id"]] = now
    state[sid] = mine
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, sp)
    except OSError as exc:
        print(f"claude-guard-{GUARD}: state write failed ({exc})", file=sys.stderr)
    if not idle:
        return None
    from _guard_failclosed import log_event
    for c in idle:
        log_event(GUARD, "warn", f"{c['agent_id']} idle {c['idle_s']}s after hand-back", payload,
                  extra={"kind": "advisory", "owner": "tooling-engineer",
                         "source": "KB § PATTERNS/common/background-agent-lifecycle.md",
                         "agent_id": c["agent_id"], "agent_type": c.get("agent_type"), "idle_s": c["idle_s"]})
    return format_report(idle)


def main() -> int:
    try:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
        signal.setitimer(signal.ITIMER_REAL, DEADLINE_S)
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        text = run(payload)
        if text:
            print(text, file=sys.stderr)
            json.dump({"hookSpecificOutput": {"hookEventName": payload.get("hook_event_name") or "PostToolUse",
                                              "additionalContext": text}}, sys.stdout)
    except BaseException as exc:  # noqa: BLE001 - fail OPEN: an advisory must never wedge the leader
        print(f"claude-guard-{GUARD}: unavailable ({type(exc).__name__}) - not blocking", file=sys.stderr)
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
