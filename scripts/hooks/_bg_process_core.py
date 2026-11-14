"""Shared core of the background-process lifecycle (launch wrapper `scripts/bg_run.py`, the
PreToolUse launch guard, `noctus.dev.bg_process`, the session-end sweep leg). Stdlib-only, so the
guard and the wrapper run under a bare `python3`.

DESIGN (owner, 2026-11-14, final): background processes END THEMSELVES when their purpose is done.
  - CONSTRUCTION: every background launch goes through the wrapper, which carries a purpose and an
    end condition the process checks itself, salvages its own output on exit and tree-stops its
    children, verifying none is orphaned.
  - REFUSAL AT LAUNCH: the guard refuses open-ended loops and bare long-running commands.
  - NO MAX LIFETIME and no idle timer anywhere: a lifetime cap could kill long in-flight work.
  - SAFETY NET: the session-end sweep lists this session's still-running background processes; each
    is salvaged and stopped through `noctus.dev.bg_process action=stop` (which refuses to signal
    without a salvage record) or kept because it is declared long-lived / known infrastructure.

Scope is only this session's own background shells and their child trees, never a session, never a
peer's process. Ownership = child of THIS session's `claude` process (found by walking up from the
current process), or a detached shell whose command carries `/<session_id>/`. "Parent is pid 1"
alone is never an ownership test (the steward's watchers detach on purpose).

KB § PATTERNS/common/background-agent-lifecycle.md ("Background processes").
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TERM_GRACE_S = 10.0
KILL_WAIT_S = 3.0
MIN_LIST_AGE_S = 30  # the session-end listing ignores shells younger than this (foreground tool calls)
SHELLS = frozenset({"zsh", "bash", "sh", "dash", "ksh", "fish"})
WRAPPER = "bg_run.py"

# An open-ended shape: a loop statement, a follow, a poll sleep. Used by the launch guard and the wrapper.
LOOP_RE = re.compile(
    r"""(?:^|[;&|({\n'"]|\bdo\b|\bthen\b)\s*(?:while|until)\b"""
    r"""|\btail\s+-[a-zA-Z]*[fF]\b|\bsleep\s+\d|(?:^|[;&|({\n])\s*watch\s+\S|--watch\b""")
# A bare long-running command (finite, but long): test/build runners, hw-admission, a CI watch.
LONG_RE = re.compile(
    r"\b(?:pytest|py\.test|vitest|playwright\s+test|vite\s+build)\b|hw_admission\.py\s+run|\bgh\s+run\s+watch\b"
    r"|\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:test|build)\b")

# Known infrastructure that legitimately lives long: never refused at launch, never a leftover.
# Matched against launch commands (guard) and against every command of a running tree (sweep/stop).
INFRA_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"--merge-queue\s+watch", "steward merge-queue watch loop"),
    (r"--release-steward\s+heartbeat", "steward heartbeat loop"),
    (r"@modelcontextprotocol|mcp-server|noctusai/server\.py|mcp/noctusai/cli\.py\s+--serve", "MCP server"),
    (r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:dev|start|serve)\b|\bvite(?:\s+(?:dev|serve|preview)\b|\s*$)|\buvicorn\b"
     r"|\./start\.sh|docker\s+compose\s+up|http\.server", "dev server"),
    (r"/Claude\.app/|chrome-native-host", "Claude app"),
    (r"Code Helper|/Visual Studio Code|/Cursor\.app/|/Xcode|/JetBrains|\bidea\b|\bpycharm\b|\bwebstorm\b|/Zed\.app/", "IDE"),
    (r"Google Chrome|/Safari|/Firefox|/Arc\.app/|/Brave Browser", "browser"),
)

_PS_FIELDS = "pid=,ppid=,pgid=,etime=,time=,stat=,lstart=,command="


def infra_label(command: str) -> str | None:
    for pat, label in INFRA_PATTERNS:
        if re.search(pat, command):
            return label
    return None


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    pgid: int
    etime_s: float
    cpu_s: float
    stat: str
    lstart: str
    command: str

    @property
    def key(self) -> str:
        """Identity that survives pid reuse: pid + start time."""
        return f"{self.pid}:{self.lstart}"

    @property
    def is_zombie(self) -> bool:
        return self.stat.startswith("Z")


class ProcError(RuntimeError):
    """`ps` could not be run or parsed: callers report `unmeasured`, never clean."""


def parse_clock(text: str) -> float:
    """`[[dd-]hh:]mm:ss[.ss]` (ps `etime` and `time`) -> seconds."""
    t = text.strip()
    days = 0
    if "-" in t:
        d, t = t.split("-", 1)
        days = int(d)
    secs = 0.0
    for part in t.split(":"):
        secs = secs * 60 + float(part)
    return days * 86400 + secs


def parse_ps(text: str) -> dict[int, Proc]:
    out: dict[int, Proc] = {}
    for line in text.splitlines():
        tok = line.split(None, 11)  # pid ppid pgid etime time stat + lstart(5 tokens) + command
        if len(tok) < 11:
            continue
        try:
            p = Proc(int(tok[0]), int(tok[1]), int(tok[2]), parse_clock(tok[3]), parse_clock(tok[4]), tok[5],
                     " ".join(tok[6:11]), tok[11] if len(tok) > 11 else "")
        except (ValueError, IndexError):
            continue
        out[p.pid] = p
    return out


def run_ps() -> str:
    try:
        r = subprocess.run(["ps", "-axo", _PS_FIELDS], capture_output=True, text=True, timeout=5,
                           env={**os.environ, "LC_ALL": "C", "LANG": "C"})
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcError(f"ps failed: {type(exc).__name__}") from exc
    if r.returncode != 0 or not r.stdout.strip():
        raise ProcError("ps returned no data")
    return r.stdout


def snapshot(ps_text: Callable[[], str] | None = None) -> dict[int, Proc]:
    return parse_ps((ps_text or run_ps)())


def _first_tokens(command: str, n: int) -> list[str]:
    return command.split(None, n)[:n]


def is_shell(p: Proc) -> bool:
    toks = _first_tokens(p.command, 1)
    return bool(toks) and os.path.basename(toks[0]).lstrip("-") in SHELLS


def is_claude(p: Proc) -> bool:
    toks = _first_tokens(p.command, 2)
    if not toks:
        return False
    if os.path.basename(toks[0]) == "claude":
        return True
    return os.path.basename(toks[0]) == "node" and len(toks) > 1 and os.path.basename(toks[1]) == "claude"


def ancestors(procs: dict[int, Proc], pid: int) -> list[int]:
    chain: list[int] = []
    seen: set[int] = set()
    while pid in procs and pid not in seen:
        seen.add(pid)
        chain.append(pid)
        pid = procs[pid].ppid
    return chain


def find_claude_pid(procs: dict[int, Proc], start_pid: int | None = None) -> int | None:
    """The `claude` process this very process runs under (MCP server, its CLI child, a hook)."""
    forced = os.environ.get("NOCTUS_BG_CLAUDE_PID")
    if forced and forced.isdigit() and int(forced) in procs:
        return int(forced)
    for pid in ancestors(procs, os.getpid() if start_pid is None else start_pid):
        if is_claude(procs[pid]):
            return pid
    return None


def children_index(procs: dict[int, Proc]) -> dict[int, list[int]]:
    idx: dict[int, list[int]] = {}
    for p in procs.values():
        idx.setdefault(p.ppid, []).append(p.pid)
    return idx


def tree_pids(procs: dict[int, Proc], root: int, idx: dict[int, list[int]] | None = None) -> list[int]:
    """root first, then descendants breadth-first."""
    idx = idx if idx is not None else children_index(procs)
    out, queue, seen = [], [root], {root}
    while queue:
        cur = queue.pop(0)
        out.append(cur)
        for c in idx.get(cur, ()):
            if c not in seen:
                seen.add(c)
                queue.append(c)
    return out


def session_roots(procs: dict[int, Proc], claude_pid: int, session_id: str | None,
                  exclude: set[int] | None = None) -> list[Proc]:
    """Shell roots owned by THIS session; own ancestors (the tool call's own shell) are excluded."""
    ex = exclude or set()
    roots = [p for p in procs.values()
             if p.pid not in ex and not p.is_zombie and is_shell(p)
             and (p.ppid == claude_pid or (p.ppid == 1 and session_id and f"/{session_id}/" in p.command))]
    return sorted(roots, key=lambda r: r.pid)


def infra_in_tree(procs: dict[int, Proc], pids: list[int]) -> str | None:
    for pid in pids:
        label = infra_label(procs[pid].command)
        if label:
            return label
    return None


# ---------------------------------------------------------------- registry (long-lived declarations)
def store_dir() -> Path:
    override = os.environ.get("NOCTUS_BG_PROCESS_DIR")
    if override:
        return Path(override)
    from _guard_failclosed import _primary_root  # type: ignore[import-not-found]
    return _primary_root() / ".claude" / "cache" / "bg-process"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def load_registry(d: Path) -> dict[str, dict[str, Any]]:
    r = _read_json(d / "registry.json").get("declared")
    return r if isinstance(r, dict) else {}


def save_registry(d: Path, declared: dict[str, dict[str, Any]]) -> None:
    _write_json(d / "registry.json", {"declared": declared})


def declared_cover(registry: dict[str, dict[str, Any]], procs: dict[int, Proc], pids: list[int]) -> dict[str, Any] | None:
    """The declaration covering any process of the tree, matched by pid + start identity so a reused
    pid never inherits protection. No lease, no expiry: a declaration ends with its process."""
    keys = {procs[p].key for p in pids}
    for key, entry in registry.items():
        if key in keys:
            return {"key": key, **entry}
    return None


# ---------------------------------------------------------------- dossier
def tasks_dirs(session_id: str | None) -> list[Path]:
    override = os.environ.get("NOCTUS_AGENT_TASKS_DIR")
    if override:
        return [Path(override)]
    if not session_id:
        return []
    import glob
    uid = os.getuid()
    seen: set[str] = set()
    out: list[Path] = []
    for pat in (f"/private/tmp/claude-{uid}/*/{session_id}/tasks", f"/tmp/claude-{uid}/*/{session_id}/tasks"):
        for p in sorted(glob.glob(pat)):
            rp = os.path.realpath(p)
            if rp not in seen:
                seen.add(rp)
                out.append(Path(p))
    return out


def run_lsof(args: list[str], timeout: float = 1.0) -> str:
    try:
        return subprocess.run(["lsof", "-w", *args], capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def output_file_of(pids: list[int], tdirs: list[Path], lsof: Callable[[list[str]], str] | None = None) -> Path | None:
    """The task `.output` file a tree has open; None when stdout is a socket or /dev/null."""
    if not tdirs or not pids:
        return None
    out = (lsof or run_lsof)(["-p", ",".join(str(p) for p in pids[:40]), "-Fn"])
    roots = [str(t) for t in tdirs] + [os.path.realpath(t) for t in tdirs]
    for line in out.splitlines():
        if line.startswith("n") and line.endswith(".output") and any(line[1:].startswith(r) for r in roots):
            return Path(line[1:])
    return None


def cwd_of(pid: int, lsof: Callable[[list[str]], str] | None = None) -> str | None:
    for line in (lsof or run_lsof)(["-a", "-d", "cwd", "-p", str(pid), "-Fn"]).splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def tail_text(path: Path, max_lines: int = 8, max_bytes: int = 4096) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - max_bytes))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(data.splitlines()[-max_lines:])


_PATH_RE = re.compile(r"(/[^\s'\"|;&<>()]+\.(?:log|out|output|txt))")


def referenced_files(commands: list[str]) -> list[Path]:
    seen: list[Path] = []
    for c in commands:
        for m in _PATH_RE.findall(c):
            p = Path(m)
            if p not in seen and p.is_file():
                seen.append(p)
    return seen[:4]


def infer_waiting(commands: list[str]) -> list[str]:
    """What the tree is most likely waiting on (best effort, never authoritative)."""
    notes: list[str] = []
    joined = "\n".join(commands)
    if "hw_admission" in joined:
        notes.append("hw-admission slot waiter (`waiting_for_slot`): looks idle by design; check "
                     "`noctus.dev.hw_admission status` before judging it dead")
    if re.search(r"\b(until|while)\b.*\bgrep\b", joined):
        notes.append("poll loop waiting for a pattern in a file (until/while ... grep)")
    elif re.search(r"\b(until|while)\b", joined) and re.search(r"\bsleep\b", joined):
        notes.append("poll/retry loop (until|while ... sleep)")
    if re.search(r"\bgh\s+(run|pr)\s+(watch|checks)\b", joined):
        notes.append("a CI run (gh run watch / pr checks)")
    m = re.search(r"\btail\s+-[a-zA-Z]*[fF]\w*\s+(\S+)", joined)
    if m:
        notes.append(f"following a file: {m.group(1)}")
    if re.search(r"\b(pytest|vitest|playwright|vite)\b", joined):
        notes.append("a test/build run: check whether it is blocked on I/O, a lock or a hw slot")
    m = re.match(r"\s*sleep\s+(\d+)", commands[-1] if commands else "")
    if m:
        notes.append(f"leaf is `sleep {m.group(1)}` (a wait inside a loop)")
    return notes


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def build_dossier(procs: dict[int, Proc], root: Proc, pids: list[int], *, session_id: str | None,
                  tdirs: list[Path], lsof: Callable[[list[str]], str] | None = None, detail: bool = True) -> dict[str, Any]:
    commands = [procs[p].command for p in pids]
    out_file = output_file_of(pids, tdirs, lsof) if detail else None
    refs = referenced_files(commands) if detail else []
    d: dict[str, Any] = {
        "pid": root.pid, "key": root.key, "session_id": session_id, "command": _short(root.command, 400),
        "age_s": int(root.etime_s), "cpu_s": round(sum(procs[p].cpu_s for p in pids), 2),
        "tree": [{"pid": p, "ppid": procs[p].ppid, "cpu_s": round(procs[p].cpu_s, 2), "age_s": int(procs[p].etime_s),
                  "command": _short(procs[p].command, 160)} for p in pids[:12]],
        "tree_size": len(pids), "waiting_on": infer_waiting(commands),
    }
    if detail:
        d["cwd"] = cwd_of(root.pid, lsof)
        d["output_file"] = str(out_file) if out_file else None
        d["output_note"] = None if out_file else "stdout is a socket or /dev/null: no output file to read"
        d["output_tail"] = tail_text(out_file) if out_file else ""
        d["referenced_files"] = [{"path": str(p), "tail": tail_text(p, 3, 600)} for p in refs]
    return d


def scan_session(session_id: str | None, *, ps_text: Callable[[], str] | None = None,
                 lsof: Callable[[list[str]], str] | None = None, detail_limit: int = 8) -> dict[str, Any]:
    """Every running background tree of THIS session. `unmeasured` (no claude ancestor / ps down) is
    never a clean verdict."""
    try:
        procs = snapshot(ps_text)
    except ProcError as exc:
        return {"status": "unmeasured", "reason": str(exc), "processes": [], "protected": []}
    cpid = find_claude_pid(procs)
    if cpid is None:
        return {"status": "unmeasured", "reason": "no claude ancestor process found", "processes": [], "protected": []}
    d = store_dir()
    registry = load_registry(d)
    own = set(ancestors(procs, os.getpid())) | {cpid}
    idx = children_index(procs)
    tdirs = tasks_dirs(session_id)
    rows: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    for root in session_roots(procs, cpid, session_id, own):
        pids = tree_pids(procs, root.pid, idx)
        label = infra_in_tree(procs, pids)
        decl = declared_cover(registry, procs, pids)
        if label or decl:
            protected.append({"pid": root.pid, "command": _short(root.command, 160),
                              "protected_by": f"infrastructure: {label}" if label else f"declared long-lived: {decl['purpose']}"})
            continue
        if root.etime_s < MIN_LIST_AGE_S:
            continue
        rows.append(build_dossier(procs, root, pids, session_id=session_id, tdirs=tdirs, lsof=lsof,
                                  detail=len(rows) < detail_limit))
    return {"status": "ok", "claude_pid": cpid, "processes": rows, "protected": protected}


# ---------------------------------------------------------------- salvage record
def salvage_rows(d: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        for line in (d / "salvage.ndjson").read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return rows


def has_salvage(d: Path, key: str) -> dict[str, Any] | None:
    for r in reversed(salvage_rows(d)):
        if r.get("key") == key and r.get("tail_path") and r.get("reason") and r.get("learnings"):
            return r
    return None


def write_salvage(d: Path, *, session_id: str | None, dossier: dict[str, Any], reason: str, learnings: str,
                  by: str, now: float | None = None) -> dict[str, Any]:
    """Save the output tail OUTSIDE git (.claude/cache is gitignored), then append the record."""
    now = time.time() if now is None else now
    sdir = d / "salvage"
    sdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now))
    tail_path = sdir / f"{(session_id or 'nosession')[:8]}-{dossier['pid']}-{stamp}.tail.txt"
    parts = [f"command: {dossier['command']}", f"cwd: {dossier.get('cwd')}", f"age_s: {dossier['age_s']}",
             f"reason: {reason}", f"learnings: {learnings}", ""]
    for label, path in [("output", dossier.get("output_file"))] + [("referenced", r["path"]) for r in dossier.get("referenced_files", [])]:
        if path:
            parts += [f"--- {label}: {path} (tail) ---", tail_text(Path(path), 200, 65536) or "(empty or unreadable)", ""]
    parts.append("--- tree ---")
    parts += [f"{t['pid']} <- {t['ppid']} cpu={t['cpu_s']}s age={t['age_s']}s {t['command']}" for t in dossier["tree"]]
    tail_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "session_id": session_id, "key": dossier["key"],
           "pid": dossier["pid"], "command": dossier["command"], "reason": reason, "learnings": learnings,
           "tail_path": str(tail_path), "by": by}
    with open(d / "salvage.ndjson", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


# ---------------------------------------------------------------- stop (tree-kill + verify)
def _default_kill(pid: int, sig: int) -> None:
    os.kill(pid, sig)


def _send(kill: Callable[[int, int], None], pid: int, sig: int, log: list[dict[str, Any]]) -> None:
    try:
        kill(pid, sig)
        log.append({"pid": pid, "signal": signal.Signals(sig).name})
    except ProcessLookupError:
        pass
    except PermissionError:
        log.append({"pid": pid, "signal": signal.Signals(sig).name, "error": "permission denied"})


def stop_tree(root_pid: int, *, ps_text: Callable[[], str] | None = None,
              kill: Callable[[int, int], None] = _default_kill, sleep: Callable[[float], None] = time.sleep,
              term_grace_s: float = TERM_GRACE_S, kill_wait_s: float = KILL_WAIT_S,
              forbidden: set[int] | None = None) -> dict[str, Any]:
    """TERM the whole tree (root first, so a `while true` shell cannot respawn), wait, KILL what is
    left, then verify nothing of it survives (orphans re-parented to init included).
    Never signals a pid in `forbidden` or pid <= 1."""
    forbidden = (forbidden or set()) | {0, 1}
    procs = snapshot(ps_text)
    if root_pid not in procs:
        return {"ok": True, "status": "already_gone", "signals": [], "survivors": [], "orphans_remaining": []}
    original = {p: procs[p].key for p in tree_pids(procs, root_pid)}
    if forbidden & set(original):
        return {"ok": False, "status": "refused_forbidden_pid",
                "error": f"tree contains a protected pid: {sorted(forbidden & set(original))}"}
    log: list[dict[str, Any]] = []

    def alive_now() -> dict[int, Proc]:
        cur = snapshot(ps_text)
        idx = children_index(cur)
        known = {p for p, k in original.items() if p in cur and cur[p].key == k}
        frontier = set(known)
        for r in known:
            frontier.update(tree_pids(cur, r, idx))  # children spawned since the first scan
        return {p: cur[p] for p in frontier if p in cur and not cur[p].is_zombie and p not in forbidden}

    for pid in original:  # insertion order: root, then descendants
        _send(kill, pid, signal.SIGTERM, log)
    waited, live = 0.0, alive_now()
    while live and waited < term_grace_s:
        sleep(0.5)
        waited += 0.5
        live = alive_now()
    escalated = bool(live)
    if live:
        for pid in sorted(live, key=lambda p: (p != root_pid, p)):
            _send(kill, pid, signal.SIGKILL, log)
        sleep(kill_wait_s)
        live = alive_now()
    survivors = [{"pid": p, "ppid": pr.ppid, "command": _short(pr.command, 160)} for p, pr in live.items()]
    return {"ok": not survivors, "status": "stopped" if not survivors else "survivors_remain",
            "escalated_to_kill": escalated, "waited_s": waited, "signals": log, "survivors": survivors,
            "orphans_remaining": [s for s in survivors if s["ppid"] == 1]}


# ---------------------------------------------------------------- launch wrapper
def validate_launch(*, purpose: str, done: str, command: str | None, done_when: str | None, long_lived: bool) -> str | None:
    """The refusal text for an open-ended launch, else None. Shared by the wrapper (runtime)."""
    if len((purpose or "").strip()) < 5:
        return "--purpose is required (what is this process for)"
    if long_lived:
        return None if command else "--long-lived needs a command"
    if len((done or "").strip()) < 5:
        return "--done is required (what counts as done), or --long-lived for infrastructure that lives on purpose"
    if not command and not done_when:
        return "give a command (done = it exits) and/or --done-when (a check the process runs; exit 0 = done)"
    if command and LOOP_RE.search(command) and not done_when:
        return "the command is an open-ended loop/poll: it needs --done-when (a shell check, exit 0 = done)"
    return None


def run_wrapped(*, purpose: str, done: str = "", command: str | None = None, done_when: str | None = None,
                long_lived: bool = False, learnings: str = "", interval_s: float = 15.0,
                term_grace_s: float = TERM_GRACE_S, session_id: str | None = None, out=None,
                ps_text: Callable[[], str] | None = None, kill: Callable[[int, int], None] = _default_kill,
                popen: Callable[..., Any] = subprocess.Popen) -> int:
    """Run `command` with a declared end condition. Ends when the command exits OR `done_when` (a shell
    check run every interval_s) succeeds, whichever is first; then tree-stops the command's process group,
    verifies nothing is orphaned and writes its own salvage record (output tail, reason, learnings).
    No lifetime cap and no idle timer: a process with a done condition runs as long as it needs."""
    out = out or sys.stdout
    problem = validate_launch(purpose=purpose, done=done, command=command, done_when=done_when, long_lived=long_lived)
    if problem:
        print(f"[bg_run] refused: {problem}", file=sys.stderr)
        return 2
    d = store_dir()
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or None
    t0 = time.time()
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(t0))
    (d / "runs").mkdir(parents=True, exist_ok=True)
    log_path = d / "runs" / f"{stamp}-{os.getpid()}.log"
    log = open(log_path, "ab")
    wake = threading.Event()
    got = {"sig": None}

    def _on_signal(signum, _frame):
        got["sig"] = signum
        wake.set()

    previous = {s: signal.signal(s, _on_signal) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}

    my_key = None
    try:
        me = snapshot(ps_text).get(os.getpid())
        my_key = me.key if me else None
    except ProcError:
        pass
    if long_lived and my_key:
        reg = load_registry(d)
        reg[my_key] = {"purpose": purpose.strip(), "owner_session": sid, "pid": os.getpid(),
                       "command": _short(command or "", 200), "declared_ts": t0, "declared_by": "bg_run"}
        save_registry(d, reg)

    child = None
    if command:
        child = popen(["/bin/sh", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      stdin=subprocess.DEVNULL, start_new_session=True)  # own process group = the orphan net

        def _pump():
            for chunk in iter(lambda: child.stdout.readline(), b""):
                log.write(chunk)
                log.flush()
                out.write(chunk.decode("utf-8", "replace"))
                out.flush()

        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()

    def _done_check() -> bool:
        try:
            return subprocess.run(["/bin/sh", "-c", done_when], stdin=subprocess.DEVNULL, capture_output=True,
                                  timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    how, rc = "", 0
    next_check = time.time() + min(interval_s, 2.0)  # first done-when check soon, then every interval_s
    while True:
        if child is not None and child.poll() is not None:
            rc = child.returncode
            how = f"command exited rc={rc}"
            break
        if got["sig"] is not None:
            rc = 128 + int(got["sig"])
            how = f"terminated by signal {got['sig']}"
            break
        if done_when and time.time() >= next_check:
            if _done_check():
                how = "done-when condition satisfied"
                break
            next_check = time.time() + interval_s
        wake.wait(min(0.25, interval_s))  # short tick: a command that exits is noticed at once
        wake.clear()
    if child is not None:
        pump.join(timeout=2)

    pgid = child.pid if child is not None else None
    survivors: list[dict[str, Any]] = []
    if pgid is not None:
        for _ in range(3):  # a stopped member can leave a re-parented sibling: sweep the group until empty
            members = [p for p in snapshot(ps_text).values()
                       if p.pgid == pgid and not p.is_zombie and p.pid not in (os.getpid(), 1)]
            if not members:
                break
            for p in members:
                res = stop_tree(p.pid, ps_text=ps_text, kill=kill, term_grace_s=term_grace_s, forbidden={os.getpid()})
                survivors = res.get("survivors", [])
        else:
            members = [p for p in snapshot(ps_text).values() if p.pgid == pgid and not p.is_zombie and p.pid != os.getpid()]
            survivors = [{"pid": p.pid, "command": _short(p.command, 160)} for p in members]

    dur = int(time.time() - t0)
    dossier = {"pid": os.getpid(), "key": my_key or f"{os.getpid()}:unknown", "command": _short(f"bg_run: {purpose} :: {command or done_when}", 400),
               "cwd": os.getcwd(), "age_s": dur, "output_file": str(log_path), "referenced_files": [],
               "tree": [{"pid": os.getpid(), "ppid": os.getppid(), "cpu_s": 0.0, "age_s": dur,
                         "command": _short(command or done_when or "", 160)}]}
    rec = write_salvage(d, session_id=sid, dossier=dossier, reason=f"{purpose.strip()}: {how}",
                        learnings=(learnings.strip() or f"auto: {how} after {dur}s; done = {done.strip() or 'long-lived'}"),
                        by="bg_run")
    if long_lived and my_key:
        reg = load_registry(d)
        reg.pop(my_key, None)
        save_registry(d, reg)
    for sg, handler in previous.items():
        signal.signal(sg, handler)
    log.close()
    print(f"[bg_run] {how}; salvage: {rec['tail_path']}" + (f"; SURVIVORS: {survivors}" if survivors else ""), file=sys.stderr)
    return 3 if survivors else rc


def wrapper_main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="bg_run.py", description="Run a background command with a declared end condition.")
    ap.add_argument("--purpose", required=False, default="")
    ap.add_argument("--done", default="", help="what counts as done (human sentence)")
    ap.add_argument("--done-when", default=None, help="shell check the process runs itself; exit 0 = done")
    ap.add_argument("--long-lived", action="store_true", help="infrastructure that lives on purpose: purpose only, no end condition")
    ap.add_argument("--learnings", default="")
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--command", default=None, help="shell string to run (or pass it after --)")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    rest = [r for r in a.rest if r != "--"] if a.rest and a.rest[0] == "--" else a.rest
    command = a.command or (rest[0] if len(rest) == 1 else shlex.join(rest) if rest else None)
    return run_wrapped(purpose=a.purpose, done=a.done, command=command, done_when=a.done_when,
                       long_lived=a.long_lived, learnings=a.learnings, interval_s=a.interval)
