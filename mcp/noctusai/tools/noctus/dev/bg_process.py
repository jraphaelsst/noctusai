"""noctus.dev.bg_process - lifecycle of THIS session's own background processes.

Design (owner, 2026-11-14): background processes end themselves (launch wrapper `scripts/bg_run.py`,
refusal at launch by `claude-guard-background-launch.py`). This tool is the safety net: what is still
running at session end is salvaged and stopped here, or kept because it is declared long-lived.
NO lifetime cap and NO idle timer exist anywhere.

Actions
  list        read-only dossier of every running background tree of this session (pid tree, command,
              age, cwd, output file + tail, what it waits on); declared/infrastructure ones listed apart
  declare     register a process meant to live long (purpose); never listed as a leftover
  undeclare   drop a declaration
  salvage     record the salvage for a process without stopping it: output tail saved OUTSIDE git
              (.claude/cache/bg-process/salvage/), reason, learnings
  stop        salvage (when reason+learnings are given and none exists) -> TERM the whole tree (root
              first, so a `while true` shell cannot respawn) -> wait -> KILL survivors -> verify no
              orphan remains. REFUSES to signal while no salvage record exists. Whoever stops records it.

Scope: only this session's own background shells + child trees (ancestry of its `claude` process, or a
detached shell whose command carries the session id path). A peer session's process is refused, as are
infrastructure (MCP servers, dev servers, steward loops, Claude app, IDEs, browsers) and live
declarations (undeclare first). Writes are dry-run unless confirm=True; `stop` and `salvage` go through
the toolkit-staleness fresh-subprocess gate.

KB § PATTERNS/common/background-agent-lifecycle.md (Background processes).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import toolkit_freshness as _toolkit_freshness

_HOOKS = Path(__file__).resolve().parents[5] / "scripts" / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import _bg_process_core as core  # noqa: E402  (stdlib-only module shared with the launch guard + wrapper)

ACTIONS = ("list", "declare", "undeclare", "salvage", "stop")
GUARD = "background-process"
_WRITE_ACTIONS = ("stop", "salvage")  # acting on stale logic against live processes is the case that hurts


def _refuse(status: str, error: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "status": status, "error": error, **extra}


def _event(outcome: str, reason: str, extra: dict[str, Any]) -> None:
    try:
        from _guard_failclosed import log_event
        log_event(GUARD, outcome, reason, None, extra={"kind": "lifecycle", "owner": "tooling-engineer",
                                                        "source": "KB § PATTERNS/common/background-agent-lifecycle.md",
                                                        **extra})
    except Exception:  # noqa: BLE001 - telemetry must never change a verdict
        pass


def _locate(procs, claude_pid: int, session_id: str | None, pid: int, own: set[int]):
    """The session root whose tree contains `pid`, plus that tree. None when it is not this session's."""
    idx = core.children_index(procs)
    for root in core.session_roots(procs, claude_pid, session_id, own):
        pids = core.tree_pids(procs, root.pid, idx)
        if pid in pids:
            return root, pids
    return None, []


def _need(label: str, value: str, minimum: int = 10) -> str | None:
    return None if len((value or "").strip()) >= minimum else f"{label} is required (>= {minimum} chars)"


def _run(*, action: str, pid: int | None, purpose: str, reason: str, learnings: str, term_grace_s: float,
         session_id: str | None, confirm: bool, seams: dict[str, Any]) -> dict[str, Any]:
    if action not in ACTIONS:
        return _refuse("error", f"unknown action {action!r}; one of {', '.join(ACTIONS)}")
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    now = float(seams["now"]()) if seams.get("now") else time.time()
    ps_text, lsof = seams.get("ps_text"), seams.get("lsof")
    d = core.store_dir()

    if action == "list":
        scan = core.scan_session(sid, ps_text=ps_text, lsof=lsof)
        if scan["status"] != "ok":
            return _refuse("unmeasured", scan.get("reason", "scan failed"))
        return {"ok": True, "status": "listed", "session_id": sid, "processes": scan["processes"],
                "protected": scan["protected"],
                "next_action": ("salvage + stop each leftover (`action=stop pid=.. reason=.. learnings=.. confirm=true`) "
                                "or `action=declare` it if it must live" if scan["processes"] else "nothing left running")}

    try:
        procs = core.snapshot(ps_text)
    except core.ProcError as exc:
        return _refuse("unmeasured", str(exc))
    cpid = core.find_claude_pid(procs)
    if cpid is None:
        return _refuse("unmeasured", "no claude ancestor process found: cannot establish which processes are this session's")
    own = set(core.ancestors(procs, os.getpid())) | {cpid}

    if action in ("declare", "undeclare"):
        live = {p.key for p in procs.values()}
        reg = {k: v for k, v in core.load_registry(d).items() if k in live}  # a declaration ends with its process
        if action == "declare":
            if not pid or pid not in procs or pid in own:
                return _refuse("error", f"declare needs a running background pid of this session (got {pid})")
            root, _ = _locate(procs, cpid, sid, pid, own)
            if root is None:
                return _refuse("refused_not_session_process", "pid is not in this session's background-process trees")
            if (e := _need("purpose", purpose, 10)):
                return _refuse("error", e)
            entry = {"purpose": purpose.strip(), "owner_session": sid, "pid": pid,
                     "command": core._short(procs[pid].command, 200), "declared_ts": now, "declared_by": "bg_process"}
            if confirm:
                reg[procs[pid].key] = entry
                core.save_registry(d, reg)
            return {"ok": True, "status": "declared" if confirm else "planned", "entry": entry,
                    "note": "no lease, no expiry: it stays declared until the process ends or action=undeclare"}
        keys = [k for k in reg if pid and procs.get(pid) and procs[pid].key == k]
        if not keys:
            return _refuse("not_found", "no live declaration matches that pid")
        if confirm:
            for k in keys:
                reg.pop(k)
            core.save_registry(d, reg)
        return {"ok": True, "status": "undeclared" if confirm else "planned", "matched": keys}

    # salvage / stop: the target must be in THIS session
    if not pid:
        return _refuse("error", f"{action} needs pid")
    if pid in own or pid <= 1:
        return _refuse("refused_forbidden_pid", "that pid is this session's own claude/tool chain or init")
    root, pids = _locate(procs, cpid, sid, pid, own)
    if root is None:
        return _refuse("refused_not_session_process",
                       "pid is not in this session's background-process trees (a peer session's process is never touched)")
    label = core.infra_in_tree(procs, pids)
    decl = core.declared_cover(core.load_registry(d), procs, pids)
    if label or decl:
        return _refuse("refused_protected", f"protected: {('infrastructure: ' + label) if label else 'declared long-lived: ' + decl['purpose']}"
                       + ("" if label else " (action=undeclare first if it should stop)"))

    dossier = core.build_dossier(procs, root, pids, session_id=sid, tdirs=core.tasks_dirs(sid), lsof=lsof, detail=True)
    existing = core.has_salvage(d, root.key)
    if action == "salvage" or not existing:
        problems = [p for p in (_need("reason", reason), _need("learnings", learnings)) if p]
        if problems and action == "stop":
            return _refuse("refused_no_salvage",
                           "no salvage record exists for this process; pass reason and learnings (stop records it) "
                           "or run action=salvage first: " + "; ".join(problems), dossier=dossier)
        if problems:
            return _refuse("error", "; ".join(problems))
    rec = existing
    if action == "salvage":
        if confirm:
            rec = core.write_salvage(d, session_id=sid, dossier=dossier, reason=reason.strip(), learnings=learnings.strip(),
                                     by="bg_process.salvage", now=now)
            _event("salvaged", f"pid {root.pid}", {"pid": root.pid})
        return {"ok": True, "status": "salvaged" if confirm else "planned", "dossier": dossier, "salvage": rec}

    plan = {"root_pid": root.pid, "tree": dossier["tree"], "signals": f"TERM root then descendants, wait {term_grace_s:.0f}s, "
            "KILL survivors, verify no orphan", "salvage_exists": bool(existing)}
    if not confirm:
        return {"ok": True, "status": "planned", "plan": plan, "dossier": dossier}
    if not existing:
        rec = core.write_salvage(d, session_id=sid, dossier=dossier, reason=reason.strip(), learnings=learnings.strip(),
                                 by="bg_process.stop", now=now)
    result = core.stop_tree(root.pid, ps_text=ps_text, kill=seams.get("kill") or core._default_kill,
                            sleep=seams.get("sleep") or time.sleep, term_grace_s=term_grace_s, forbidden=own)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "kind": "stop", "session_id": sid,
           "key": root.key, "pid": root.pid, "status": result.get("status"), "survivors": result.get("survivors", [])}
    with open(d / "salvage.ndjson", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    _event("stopped" if result.get("ok") else "stop-incomplete", f"pid {root.pid} {result.get('status')}",
           {"pid": root.pid, "survivors": len(result.get("survivors", []))})
    return {**result, "salvage": rec, "dossier_command": dossier["command"],
            "next_action": None if result.get("ok") else "survivors remain: inspect `survivors`, re-run stop on them or escalate"}


@_toolkit_freshness.refuse_gate(
    "bg_process", write_predicate=lambda a: bool(a.get("confirm")) and a.get("action") in _WRITE_ACTIONS)
def bg_process(
    *,
    action: str = "list",
    pid: int | None = None,
    purpose: str = "",
    reason: str = "",
    learnings: str = "",
    term_grace_s: float = core.TERM_GRACE_S,
    session_id: str | None = None,
    confirm: bool = False,
    seams: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lifecycle of this session's own background processes: list / declare / undeclare / salvage / stop."""
    return _run(action=action, pid=pid, purpose=purpose, reason=reason, learnings=learnings,
                term_grace_s=term_grace_s, session_id=session_id, confirm=confirm, seams=seams or {})


def session_report(session_id: str | None = None, *, seams: dict[str, Any] | None = None) -> dict[str, Any]:
    """The session-end leg: every running background tree of this session that is not declared long-lived or
    infrastructure. `clean_wrap` is True only when measured AND empty; unmeasured is None (never green, never red)."""
    s = seams or {}
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    scan = core.scan_session(sid, ps_text=s.get("ps_text"), lsof=s.get("lsof"))
    if scan["status"] != "ok":
        return {"status": "unmeasured", "reason": scan.get("reason"), "clean_wrap": None, "processes": []}
    procs = scan["processes"]
    return {"status": "ok", "clean_wrap": not procs, "count": len(procs), "processes": procs,
            "protected": scan["protected"],
            "next_action": ("each leftover background process must be salvaged and stopped "
                            "(`noctus.dev.bg_process action=stop pid=.. reason=.. learnings=.. confirm=true`) or kept by "
                            "`action=declare` (long-lived, with a purpose) before the session wraps; whoever ends the "
                            "session owns its leftovers" if procs else None)}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.bg_process",
        description=(
            "Safety net for THIS session's own background processes (Bash run_in_background shells + child trees); "
            "they should already end themselves via scripts/bg_run.py (purpose + done-condition). "
            "action=list (read-only dossier: pid tree, command, age, cwd, output tail, what it waits on) | "
            "declare pid purpose (a long-lived process; never a leftover; no lease, no expiry) | undeclare pid | "
            "salvage pid reason learnings (output tail saved outside git) | "
            "stop pid reason learnings: REFUSES to signal until a salvage record exists, then TERM of the whole tree "
            "(root first), wait, KILL survivors, verify no orphans. Refuses peer-session pids, infrastructure "
            "(MCP/dev servers, steward loops, Claude app, IDEs, browsers) and live declarations. "
            "No lifetime cap or idle timer exists. Writes are dry-run unless confirm=True. "
            "KB § PATTERNS/common/background-agent-lifecycle.md"
        ),
    )
    def _bg_process(
        action: str = "list",
        pid: int | None = None,
        purpose: str = "",
        reason: str = "",
        learnings: str = "",
        term_grace_s: float = core.TERM_GRACE_S,
        session_id: str | None = None,
        confirm: bool = False,
        allow_stale_toolkit: bool = False,
    ) -> dict:
        return bg_process(action=action, pid=pid, purpose=purpose, reason=reason, learnings=learnings,
                          term_grace_s=term_grace_s, session_id=session_id, confirm=confirm,
                          allow_stale_toolkit=allow_stale_toolkit)


__all__ = ["bg_process", "session_report", "register"]
