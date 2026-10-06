"""noctus.dev.harness_status / noctus.dev.harness_event — back-ends of the
`noc-harness` Claude Code mod (status line, reminders band, orchestration pane,
friction ledger).

MCP-first: the mod is a thin TS shell that shells out to ``cli.py
--harness-status`` / ``--harness-event``; ALL logic lives here and composes
existing mechanisms (auto_improvement, branch_pointer, refresh_all_caches
detect_stale_caches, memory dir resolver, git worktree porcelain) — nothing is
re-implemented.

``harness_status`` contract: schema ``noc.harness_status/v1``. It NEVER raises
and NEVER fetches: a failing section lands in ``errors`` (no silent errors) and
the section value degrades to ``null`` / empty. Fast mode (after every turn)
reads refs only; full mode adds caches / auto-improvement / pointers /
worktrees / dispatcher.

``harness_event`` records a friction event as an s1 auto-improvement entry via
the EXISTING ``auto_improvement.log_entry`` (same ledger as
``noctus.dev.auto_improvement_log``).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA = "noc.harness_status/v1"
SHARED_BRANCHES = frozenset({"dev", "main", "prod"})
EVENT_KINDS = frozenset({
    "gate_denied", "gate_timeout", "guard_error", "harness_invalid",
    "compaction_capture", "note",
})
_FULL_KEYS = ("caches", "auto_improvement", "branch_pointers", "worktrees", "dispatcher_pending")
_GIT_TIMEOUT = 20


def _git(args: list[str], cwd: str | Path) -> tuple[int, str]:
    r = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )
    return r.returncode, (r.stdout or "").strip()


def _git_ok(args: list[str], cwd: str | Path) -> str:
    rc, out = _git(args, cwd)
    if rc != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (rc={rc})")
    return out


def _primary_root(cwd: str | Path) -> Path:
    """The primary checkout: first entry of `git worktree list` (the common dir's owner)."""
    out = _git_ok(["worktree", "list", "--porcelain"], cwd)
    for line in out.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):]).resolve()
    raise RuntimeError("no worktree entries from git")


def _count(args: list[str], cwd: str | Path) -> int:
    return int(_git_ok(["rev-list", "--count", *args], cwd))


def _dirty(cwd: str | Path, *, untracked: bool = True) -> int:
    """Porcelain line count. ``untracked=False`` (-uno) is ~3x cheaper; the
    worktree pane uses it (tracked/staged changes only) to hold the full-mode
    budget across ~35 worktrees, the session tree keeps untracked files."""
    out = _git_ok(["status", "--porcelain"] + ([] if untracked else ["-uno"]), cwd)
    return len(out.splitlines()) if out else 0


# ── sections ──────────────────────────────────────────────────────────────────
def _section_session(cwd: Path, primary: Path) -> dict:
    cwd = cwd.resolve()
    s: dict[str, Any] = {"cwd": str(cwd), "tree": "outside", "worktree_slug": None,
                         "branch": None, "is_shared_branch": False, "dirty": 0}
    rc, top = _git(["rev-parse", "--show-toplevel"], cwd)
    if rc != 0 or not top:
        return s
    top_p = Path(top).resolve()
    if top_p == primary:
        s["tree"] = "primary"
    else:
        s["tree"] = "worktree"
        s["worktree_slug"] = top_p.name
    rc, br = _git(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
    s["branch"] = br if rc == 0 and br else None
    s["is_shared_branch"] = s["branch"] in SHARED_BRANCHES
    s["dirty"] = _dirty(cwd)
    return s


def _section_dev(primary: Path) -> dict:
    left, right = _git_ok(["rev-list", "--left-right", "--count", "dev...origin/dev"], primary).split()
    return {
        "local_ahead": int(left),
        "local_behind": int(right),
        "dev_ahead_of_main": _count(["origin/main..origin/dev"], primary),
    }


_REMINDER_RE = re.compile(r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+)\)")


def parse_reminders(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = _REMINDER_RE.match(line)
        if m:
            out.append({"title": m.group("title").strip(), "file": m.group("file").strip()})
    return out


def _section_reminders(memory_dir: Path | None) -> list[dict]:
    if memory_dir is None:
        from tools.noctus.dev.memory_embeddings import _resolve_memory_dir
        memory_dir = _resolve_memory_dir()
    if memory_dir is None:
        raise RuntimeError("agent memory dir not found (set NOCTUS_AGENT_MEMORY_DIR)")
    f = Path(memory_dir) / "MEMORY-reminders.md"
    if not f.is_file():
        raise RuntimeError(f"{f} not found")
    return parse_reminders(f.read_text(encoding="utf-8"))


# noc-graph's freshness keeper walks every file of the tree incl. nested
# .claude/worktrees (~40 s on a primary with many worktrees) — far past the
# full-mode budget. Skipped LOUDLY (errors[] entry), never silently.
_SLOW_CACHES = frozenset({"noc-graph"})


def _section_caches(root: Path, errors: list[dict]) -> dict:
    from tools.noctus.dev import refresh_all_caches as rac
    stale = rac.detect_stale_caches(repo_root=root, skip=_SLOW_CACHES)
    errors.append({"section": "caches.noc-graph",
                   "error": "skipped: freshness keeper too slow for the poll budget (run noctus.dev.detect_stale_caches)"})
    return {"stale": list(stale), "total": len(rac._ALL_CACHES) - len(_SLOW_CACHES)}


def _section_auto_improvement() -> dict:
    from tools.noctus.dev import auto_improvement as ai
    rows = ai.query(open_only=True, limit=500)
    top = [{"target": r.get("target"), "stage": r.get("status"),
            "summary": (r.get("description") or "")[:160]} for r in rows[:5]]
    return {
        "open_s1": sum(1 for r in rows if r.get("status") == "s1-emergent"),
        "open_s2": sum(1 for r in rows if r.get("status") == "s2-memory"),
        "top": top,
    }


def _section_pointers() -> list[dict]:
    from tools.noctus.dev import branch_pointer as bp
    out = []
    for r in bp.list_pointers(from_dev=True):
        out.append({
            "branch": r.get("branch"), "agent": r.get("agent"), "role": r.get("role"),
            "status": r.get("status"), "brief": r.get("brief"), "worktree": r.get("worktree"),
            "paths": r.get("paths", []), "updated_at": r.get("ts"),
        })
    return out


def _worktree_row(wt: dict, primary: Path) -> dict:
    path = wt["path"]
    rc, ahead = _git(["rev-list", "--count", "origin/dev..HEAD"], path)
    return {
        "slug": Path(path).name, "path": path, "branch": wt.get("branch"),
        "head": wt.get("head", "")[:9], "dirty": _dirty(path, untracked=False),
        "ahead_of_dev": int(ahead) if rc == 0 and ahead.isdigit() else 0,
    }


def _section_worktrees(primary: Path) -> list[dict]:
    out = _git_ok(["worktree", "list", "--porcelain"], primary)
    wts: list[dict] = []
    cur: dict = {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                wts.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[9:]
        elif line.startswith("HEAD "):
            cur["head"] = line[5:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].removeprefix("refs/heads/")
    wt_root = str(primary / ".claude" / "worktrees")
    mine = [w for w in wts if w.get("path", "").startswith(wt_root + "/")]
    with ThreadPoolExecutor(max_workers=16) as ex:
        return list(ex.map(lambda w: _worktree_row(w, primary), mine))


def _section_dispatcher(primary: Path) -> int:
    f = primary / ".claude" / "dispatcher.md"
    if not f.is_file():
        return 0
    n, in_pending = 0, False
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_pending = line[3:].strip().lower() == "pending"
            continue
        if in_pending and re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line):
            n += 1
    return n


# ── public API ────────────────────────────────────────────────────────────────
def harness_status(
    *, full: bool = False, cwd: str | None = None, repo_root: str | Path | None = None,
    memory_dir: Path | None = None,
    section_overrides: dict[str, Callable[[], Any]] | None = None,
) -> dict:
    """Build the ``noc.harness_status/v1`` object. Never raises.

    ``section_overrides`` is a DI seam (name -> zero-arg callable) so tests and
    callers can substitute a section provider; production passes nothing.
    """
    ov = section_overrides or {}
    errors: list[dict] = []
    cwd_p = Path(cwd or ".").expanduser().resolve()
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "full" if full else "fast",
        "repo_root": None,
        "session": {"cwd": str(cwd_p), "tree": "outside", "worktree_slug": None,
                    "branch": None, "is_shared_branch": False, "dirty": 0},
        "dev": {"local_ahead": 0, "local_behind": 0, "dev_ahead_of_main": 0},
        "reminders": [],
    }
    for k in _FULL_KEYS:
        out[k] = None

    def run(name: str, fn: Callable[[], Any], default: Any = None) -> Any:
        try:
            return ov[name]() if name in ov else fn()
        except Exception as exc:  # noqa: BLE001 — surfaced in errors[], never dropped
            errors.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
            return default

    start = Path(repo_root) if repo_root else cwd_p
    primary: Path | None = run("repo_root", lambda: _primary_root(start))
    out["repo_root"] = str(primary) if primary else None
    if primary is not None:
        out["session"] = run("session", lambda: _section_session(cwd_p, primary), out["session"])
        out["dev"] = run("dev", lambda: _section_dev(primary), out["dev"])
    out["reminders"] = run("reminders", lambda: _section_reminders(memory_dir), [])
    tree_root = Path(out["session"].get("cwd") or primary or ".")
    rc, top = _git(["rev-parse", "--show-toplevel"], tree_root) if primary else (1, "")
    tree_root = Path(top) if rc == 0 and top else (primary or tree_root)
    if full and primary is not None:
        out["caches"] = run("caches", lambda: _section_caches(tree_root, errors))
        out["auto_improvement"] = run("auto_improvement", _section_auto_improvement)
        out["branch_pointers"] = run("branch_pointers", _section_pointers)
        out["worktrees"] = run("worktrees", lambda: _section_worktrees(primary))
        out["dispatcher_pending"] = run("dispatcher_pending", lambda: _section_dispatcher(primary))
    out["errors"] = errors
    return out


def harness_event(payload: Any) -> dict:
    """Record one friction event as an s1 auto-improvement entry."""
    if not isinstance(payload, dict):
        return {"status": "error", "error": "payload must be a JSON object"}
    kind = payload.get("kind")
    if kind not in EVENT_KINDS:
        return {"status": "error",
                "error": f"kind must be one of {sorted(EVENT_KINDS)}; got {kind!r}"}
    for req in ("target", "summary"):
        if not isinstance(payload.get(req), str) or not payload[req].strip():
            return {"status": "error", "error": f"{req} is required (non-empty string)"}
    source = payload.get("source") or "noc-harness-mod"
    desc = f"[{kind}] {payload['summary'].strip()}"
    if payload.get("detail"):
        desc += f"\n\n{payload['detail']}"
    from tools.noctus.dev import auto_improvement as ai
    try:
        r = ai.log_entry(
            scope="scoped",
            kind="improvement" if kind in ("note", "compaction_capture") else "drift",
            target=payload["target"], description=desc, agent=source,
            status="s1-emergent",
            source_ref=(f"session:{payload['session_id']}" if payload.get("session_id") else source),
        )
    except Exception as exc:  # noqa: BLE001 — reported, exit 1 by the CLI
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    if not r.get("ok"):
        return {"status": "error", "error": r.get("error", "auto_improvement.log_entry refused")}
    e = r["entry"]
    eid = hashlib.sha1(f"{e['ts']}|{e['target']}|{desc}".encode()).hexdigest()[:12]
    return {"status": "logged", "id": eid, "ts": e["ts"], "ledger_path": r.get("ledger_path")}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.harness_status",
        description=(
            "Status snapshot for the noc-harness Claude Code mod (schema noc.harness_status/v1): "
            "session tree/branch/dirty, local-dev vs origin/dev vs origin/main drift (refs only, "
            "no fetch), open owner reminders; full=True adds stale caches, open auto-improvement, "
            "live branch pointers, worktrees, dispatcher pending. Never raises — section failures "
            "go in `errors`. Read-only."
        ),
    )
    def _status(full: bool = False, cwd: str | None = None) -> dict:
        return harness_status(full=full, cwd=cwd)

    @server.tool(
        name="noctus.dev.harness_event",
        description=(
            "Record a noc-harness friction event (kind ∈ gate_denied|gate_timeout|guard_error|"
            "harness_invalid|compaction_capture|note; target; summary; detail?; session_id?) as an "
            "s1 auto-improvement entry via the existing auto_improvement ledger."
        ),
    )
    def _event(kind: str, target: str, summary: str, detail: str | None = None,
               session_id: str | None = None, source: str = "noc-harness-mod") -> dict:
        return harness_event({"kind": kind, "target": target, "summary": summary,
                              "detail": detail, "session_id": session_id, "source": source})
