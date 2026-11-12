"""The release steward: ONE elected leader session per machine handles CI queueing AND deploy.

WHY THIS EXISTS
===============
2026-11-05: an agent had to be paused so it would not push to `dev` and get in
another agent's way. The CI merge queue serialises the MERGES but not the
SESSIONS - N sessions still raced to enqueue, bless, promote and deploy, and a
queue is not coordination. Gate<->methodology sync: the rule "one session owns
the shared lane" ships with its mechanism (this module), not as discipline.

THE MODEL (KB § PATTERNS/devops/release-steward.md)
===================================================
* ONE lease per machine (`~/.noctus/release-steward.json`, flock + atomic
  replace). Holder = a LEADER session (interactive, top-level), never a
  dispatched subagent. A steward's own subagents act under its lease.
* Steward-only: `task_branch enqueue|integrate|landed` (confirm), `release
  bless|promote|backmerge` (confirm), `deploy_pull` / `deploy_image` /
  `migrate_product` / `record_applied_migrations` / `vps recreate` (confirm),
  and `git push` to dev|main|prod|mq/*. Reads, dry-runs and
  `release_steward` itself stay open to everyone.
* Gated != blocked. A non-steward FILES its delivery in the shared outbox
  (`action=request`, non-blocking, latest head_sha wins) and KEEPS BUILDING.
  The steward drains the whole outbox at once (`inbox` -> batched enqueue ->
  `ack`) and reports LANDED / EJECTED / DEPLOYED back (SendMessage is sugar on
  top; the outbox + the hook are the record).

SESSION BINDING (how the tool knows who is calling)
===================================================
Claude Code starts ONE MCP server process per session and gives it
`CLAUDE_CODE_SESSION_ID` in its environment (verified 2026-11-05 on three
live servers: each value differs and matches its own session). So the tool
layer needs no hook cooperation: identity = that env var. The PreToolUse hook
gets the same id as `session_id` in its stdin JSON, so both ends compare the
SAME value against the lease. Via Bash (the CLI) the env var is in the Bash
environment too. A subagent shares its parent's server and session id - it
acts as the steward when the parent is the steward (intended).
After `/clear` the session id may change while the server env does not: the
old lease then no longer matches the hook's id; re-claim (a claim takes over
a same-process lease via `claude_pid`).

LEASE LIVENESS
==============
A lease is stale when its holder process (`claude_pid`) is gone, OR no
heartbeat for `ttl_s` (default 7200s: a steward's quiet stretch is a
merge-queue drain + a deploy - tens of minutes - and every steward call, plus
every steward-class call the hook lets through, refreshes the heartbeat; 2h
frees the lane the same working day after a forgotten session without ever
expiring under a live drain). Override per lease with `ttl_s=` or fleet-wide
with NOCTUS_STEWARD_TTL_S.

ESCAPE
======
`NOC_STEWARD_OVERRIDE=<reason >=10 chars>` (inline Bash prefix, or in the
hook/server environment). Never silent: recorded in
`~/.noctus/release-steward.ndjson`.

Stdlib-only at import (loaded BY PATH by the hook; `register()` is the only
place that touches the server). Every decision takes injected seams
(`store`, `env`, clock, pid probe) so tests never monkeypatch the guard.
"""
from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

KB_POINTER = "KB § PATTERNS/devops/release-steward.md"
OVERRIDE_ENV = "NOC_STEWARD_OVERRIDE"
OVERRIDE_MIN_CHARS = 10
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
DEFAULT_TTL_S = 7200
QUEUE_PREFIX = "mq/"
PROTECTED_BRANCHES = {"dev", "main", "prod", "prod-backup"}

#: The exact instruction every deny carries. Gated != blocked: never "wait".
REQUEST_CMD = "queue it with release_steward action=request slug=<slug> and keep building — do not wait"

_MCP_NAMES = {
    "mcp__noctusai__noctus_dev_task_branch": "noctus.dev.task_branch",
    "mcp__noctusai__noctus_dev_release": "noctus.dev.release",
    "mcp__noctusai__noctus_dev_deploy_pull": "noctus.dev.deploy_pull",
    "mcp__noctusai__noctus_dev_deploy_image": "noctus.dev.deploy_image",
    "mcp__noctusai__noctus_dev_migrate_product": "noctus.dev.migrate_product",
    "mcp__noctusai__noctus_dev_record_applied_migrations": "noctus.dev.record_applied_migrations",
    "mcp__noctusai__noctus_vps_recreate": "noctus.vps.recreate",
    "mcp__noctusai__noctus_dev_supabase_breaker": "noctus.dev.supabase_breaker",
    "mcp__noctusai__noctus_dev_release_steward": "noctus.dev.release_steward",
}
_TASK_BRANCH_GATED = {"enqueue", "integrate", "landed"}
_RELEASE_GATED = {"bless", "promote", "backmerge"}
OUTCOMES = ("enqueued", "landed", "ejected", "deployed", "withdrawn", "needs_resync")
NEEDS_INFO_DEFAULT_MIN = 30
_ADVANCED = {"enqueued", "landed", "deployed"}
#: a request is CLOSED once landed, deployed or withdrawn; every other status (queued_for_steward, and the outcomes a
#: delivery can be left at - enqueued, ejected, needs_resync) is OPEN and may already be in origin/dev. Derived from
#: OUTCOMES, never hand-listed: only the closed set is named (2026-11-10, rows stuck at `enqueued`/`ejected`).
_CLOSED = {"landed", "deployed", "withdrawn"}
_OPEN_STATUSES = {"queued_for_steward", *OUTCOMES} - _CLOSED


# -- time / ids -------------------------------------------------------------

def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return True  # unknown pid: liveness falls back to the heartbeat TTL
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def _short(session_id: str | None) -> str:
    return (session_id or "?")[:8]


def default_root(env: dict[str, str] | None = None) -> Path:
    e = env if env is not None else os.environ
    return Path(e.get("NOCTUS_STEWARD_DIR") or Path.home() / ".noctus")


def default_ttl(env: dict[str, str] | None = None) -> int:
    e = env if env is not None else os.environ
    try:
        return max(60, int(e.get("NOCTUS_STEWARD_TTL_S") or DEFAULT_TTL_S))
    except ValueError:
        return DEFAULT_TTL_S


def _err(msg: str) -> dict[str, Any]:
    return {"ok": False, "status": "error", "error": msg}


def _label(lease: dict[str, Any] | None) -> str:
    if not lease:
        return "nobody"
    return (f"{lease.get('session_name') or _short(lease.get('session_id'))} "
            f"(session {_short(lease.get('session_id'))}, since {lease.get('claimed_at')}, "
            f"last heartbeat {lease.get('heartbeat_at')})")


def _brief(lease: dict[str, Any] | None) -> dict[str, Any] | None:
    if not lease:
        return None
    return {k: lease.get(k) for k in ("session_id", "session_name", "claimed_at", "heartbeat_at")}


def _git_resolve_head(branch: str) -> str | None:
    """Best-effort head sha of a local branch (branches are shared across a clone's worktrees)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                             capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", sha) else None


def git_landed_check(cwd: Path | str | None = None, base: str = "origin/dev") -> Callable[[str, str | None], dict[str, Any]]:
    """Real seam for `StewardStore.landed_check`: is a delivery already in `base`?

    Resolves refs/heads/<branch>, then refs/remotes/origin/<branch>, then `head_sha`; the first that
    resolves is judged with `git cherry <base> <ref>` - zero '+' lines means every commit is already
    in base (method=cherry). When cherry leaves commits unmatched, falls back to post-image blob equality
    (method=post_image) then `git range-diff` (method=range_diff); a partial match is state=uncertain with
    evidence, never landed. state: landed | pending | uncertain | unresolvable (never silent).
    `dev_sha` = the ref's own sha when it is an ancestor of base, else base's tip."""
    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=60, check=False,
                              cwd=str(cwd) if cwd else None)

    def _rev(ref: str) -> str | None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            out = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
            sha = out.stdout.strip()
            if out.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", sha):
                return sha
        return None

    def _blob(ref: str, path: str) -> str | None:
        out = _git("rev-parse", "--verify", "--quiet", f"{ref}:{path}")
        return out.stdout.strip() if out.returncode == 0 else None

    def _fallback(sha: str, base_tip: str) -> dict[str, Any]:
        """`git cherry` (patch-ids) missed it: a rebase with conflict resolution, a squash or a --no-ff train
        changes patch-ids while the CONTENT landed. Judge content: post-image blobs, then range-diff.
        Read-only plumbing; cwd is the git common dir, never the primary checkout's work tree."""
        mb = _git("merge-base", base_tip, sha).stdout.strip()
        if not mb:
            return {"state": "pending"}
        diff = _git("diff", "--no-renames", "--name-only", "-z", mb, sha)
        if diff.returncode != 0:
            return {"state": "unresolvable", "reason": (diff.stderr or "git diff failed").strip()[:200]}
        files = [f for f in diff.stdout.split("\0") if f]
        matched = [f for f in files if _blob(sha, f) == _blob(base_tip, f)]
        unmatched = [f for f in files if f not in set(matched)]
        if files and not unmatched:
            return {"state": "landed", "dev_sha": base_tip, "method": "post_image"}
        rd = _git("range-diff", "--no-color", f"{mb}..{sha}", f"{mb}..{base_tip}")
        marks = []
        if rd.returncode == 0:
            for ln in rd.stdout.splitlines():
                m = re.match(r"^\s*(\d+|-):\s+\S+\s+([=!<>])\s+(\d+|-):", ln)
                if m and m.group(1) != "-":
                    marks.append(m.group(2))
        if marks and all(x == "=" for x in marks):
            return {"state": "landed", "dev_sha": base_tip, "method": "range_diff"}
        if matched or any(x in ("=", "!") for x in marks):
            return {"state": "uncertain", "method": "post_image",
                    "evidence": {"matched_files": matched[:50], "unmatched_files": unmatched[:50],
                                 "range_diff": "".join(marks)[:200] or "none"}}
        return {"state": "pending"}

    def check(branch: str, head_sha: str | None) -> dict[str, Any]:
        try:
            base_tip = _rev(base)
            if not base_tip:
                return {"state": "unresolvable", "reason": f"{base} not resolvable"}
            sha = None
            for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}", head_sha or ""):
                sha = _rev(ref) if ref else None
                if sha:
                    break
            if not sha:
                return {"state": "unresolvable", "reason": f"neither {branch} nor head_sha resolve"}
            cherry = _git("cherry", base, sha)
            if cherry.returncode != 0:
                return {"state": "unresolvable", "reason": (cherry.stderr or "git cherry failed").strip()[:200]}
            anc = _git("merge-base", "--is-ancestor", sha, base_tip)
            dev_sha = sha if anc.returncode == 0 else base_tip
            if any(ln.startswith("+") for ln in cherry.stdout.splitlines()):
                return _fallback(sha, base_tip)
            return {"state": "landed", "dev_sha": dev_sha, "method": "cherry"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"state": "unresolvable", "reason": str(exc)[:200]}
    return check


_ROLE_RE = re.compile(r"[A-Za-z0-9._:/-]+")
_TOGETHER_RE = re.compile(r"\btogether\b|\btwo branches\b|\b2 branches\b", re.IGNORECASE)
_FEAT_RE = re.compile(r"feat/[A-Za-z0-9._/-]*[A-Za-z0-9_]")


# -- the store: lease + audit + outbox --------------------------------------

class StewardStore:
    """Machine-wide lease, audit log and ship-request outbox.

    Mutations take an exclusive flock on a sibling `.lock` file and replace
    atomically (lease) or append (ndjson), so concurrent sessions never read a
    torn write. Seams: `clock`, `pid_alive`, `resolve_head`, `inline_gate`.
    """

    def __init__(self, root: Path | None = None, *, clock: Callable[[], float] = time.time,
                 pid_alive: Callable[[int | None], bool] = _pid_alive,
                 resolve_head: Callable[[str], str | None] | None = None,
                 default_ttl_s: int | None = None,
                 landed_check: Callable[[str, str | None], dict[str, Any]] | None = None,
                 inline_gate: Callable[[str, str | None, str | None], dict[str, Any]] | None = None,
                 deliverable_check: Callable[[str, str | None, str | None], dict[str, Any]] | None = None,
                 resolve_branch: Callable[[str], dict[str, Any]] | None = None,
                 scoped_check: Callable[[str, str], dict[str, Any]] | None = None,
                 repo_cwd: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()
        # Same posture as inline_gate/landed_check: production runs the real delivery-contract preflight
        # (`deliverable`) at filing; a store built on an explicit root (tests) skips it unless it injects one.
        self._deliverable_check = deliverable_check if deliverable_check is not None else (
            (lambda b, h, v: deliverable(b, head_sha=h, verdict_ref=v)) if root is None else None)
        self._resolve_branch = resolve_branch if resolve_branch is not None else (
            resolve_branch_name if root is None else None)
        self.repo_cwd = repo_cwd  # where the landed-by-branch-steward rule reads git (None = the process cwd)
        # `request(run_scoped=True)` runs the CI-parity check (minutes) and files with the ref it mints. Production runs
        # the real one; an explicit-root store (tests) has none unless it injects one - and then REFUSES the flag.
        self._scoped_check = scoped_check if scoped_check is not None else (
            export_ci_parity_check() if root is None else None)
        # Production (root=None -> ~/.noctus) runs the real gate; a store built on an explicit root
        # (tests, tooling) opts out unless it injects one - the gate reads the shared pointer ledger.
        self._inline_gate = inline_gate if inline_gate is not None else (
            None if root is None else (lambda _b, _r, _n: {"applicable": False}))
        # Same posture as inline_gate: production runs the real `git cherry` check; an explicit-root
        # store (tests) reports "pending" (unmeasured) unless it injects one.
        self.landed_check = landed_check if landed_check is not None else (
            git_landed_check() if root is None else (lambda _b, _h: {"state": "pending"}))
        self.clock = clock
        self.pid_alive = pid_alive
        self.resolve_head = resolve_head if resolve_head is not None else _git_resolve_head
        self.default_ttl_s = default_ttl_s if default_ttl_s is not None else default_ttl()

    @property
    def lease_path(self) -> Path:
        return self.root / "release-steward.json"

    @property
    def audit_path(self) -> Path:
        return self.root / "release-steward.ndjson"

    @property
    def outbox_path(self) -> Path:
        return self.root / "ship-requests.ndjson"

    @property
    def roles_path(self) -> Path:
        return self.root / "release-steward-roles.json"

    @contextlib.contextmanager
    def _locked(self, name: str) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / f"{name}.lock", "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def audit(self, event: str, **fields: Any) -> None:
        row = {"ts": _iso(self.clock()), "event": event, **fields}
        with self._locked("release-steward-audit"), open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    # lease I/O (read-modify-write callers hold the "release-steward" lock)
    def _read_lease(self) -> dict[str, Any] | None:
        try:
            doc = json.loads(self.lease_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return {"corrupt": True}
        return doc if isinstance(doc, dict) and doc.get("session_id") else None

    def _write_lease(self, lease: dict[str, Any] | None) -> None:
        if lease is None:
            with contextlib.suppress(FileNotFoundError):
                self.lease_path.unlink()
            return
        tmp = self.lease_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lease, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.lease_path)

    def _state(self, lease: dict[str, Any] | None) -> str:
        if not lease:
            return "none"
        if lease.get("corrupt"):
            return "stale"  # an unreadable lease must not wedge the lane
        ttl = int(lease.get("ttl_s") or self.default_ttl_s)
        if self.clock() - float(lease.get("heartbeat_ts") or 0) > ttl:
            return "stale"
        if not self.pid_alive(lease.get("claude_pid")):
            return "stale"
        return "live"

    def holder(self) -> tuple[dict[str, Any] | None, str]:
        """(lease, state) with state in none|live|stale. Reads need no lock (atomic replace)."""
        lease = self._read_lease()
        return lease, self._state(lease)

    def public_holder(self) -> dict[str, Any] | None:
        lease, state = self.holder()
        if not lease or lease.get("corrupt"):
            return None
        return {
            "session_id": lease.get("session_id"), "session_name": lease.get("session_name"),
            "claimed_at": lease.get("claimed_at"), "heartbeat_at": lease.get("heartbeat_at"),
            "reason": lease.get("reason"), "ttl_s": lease.get("ttl_s"), "state": state,
            "handoff_to": lease.get("handoff_to"),
        }

    # lease actions
    def claim(self, session_id: str, name: str | None = None, reason: str | None = None,
              claude_pid: int | None = None, ttl_s: int | None = None,
              child_session: bool = False) -> dict[str, Any]:
        if not session_id:
            return _err(f"no session identity: run inside a Claude Code session ({SESSION_ENV} unset) "
                        "or pass --steward-session-id")
        now = self.clock()
        with self._locked("release-steward"):
            cur = self._read_lease()
            state = self._state(cur)
            how, previous = "claimed", None
            if state == "live" and cur is not None:
                offer = cur.get("handoff_to") or {}
                accepts_offer = bool(offer) and (offer.get("session_id") == session_id
                                                 or (offer.get("name") and offer.get("name") == name))
                same_process = bool(claude_pid) and cur.get("claude_pid") == claude_pid
                if cur.get("session_id") == session_id:
                    how = "already_steward"
                elif accepts_offer:
                    how, previous = "accepted_handoff", _brief(cur)
                elif same_process:
                    how, previous = "reclaimed_same_process", _brief(cur)
                else:
                    return {"ok": False, "status": "refused_steward_exists", "steward": self.public_holder(),
                            "error": (f"a live steward already holds the lane: {_label(cur)}. Run ListAgents, "
                                      "coordinate with them (SendMessage), and file your delivery with "
                                      f"release_steward action=request. Or ask them to hand off. {KB_POINTER}")}
            elif state == "stale" and cur is not None and not cur.get("corrupt"):
                how, previous = "took_over_stale", _brief(cur)
            keep = how == "already_steward"
            lease = {
                "session_id": session_id,
                "session_name": name or ((cur or {}).get("session_name") if keep else None) or _short(session_id),
                "claimed_at": (cur or {}).get("claimed_at") if keep else _iso(now),
                "heartbeat_at": _iso(now), "heartbeat_ts": now,
                "reason": reason or ((cur or {}).get("reason") if keep else None),
                "claude_pid": claude_pid, "ttl_s": int(ttl_s or (cur or {}).get("ttl_s") or self.default_ttl_s)
                if keep else int(ttl_s or self.default_ttl_s),
                "child_session": bool(child_session),
            }
            self._write_lease(lease)
        self.audit(how, session_id=session_id, name=lease["session_name"], reason=reason, previous=previous)
        out: dict[str, Any] = {
            "ok": True, "status": how, "steward": self.public_holder(),
            "next": ("ANNOUNCE yourself to every peer now: ListAgents, then SendMessage each session "
                     "'I am the release steward; queue deliveries with release_steward action=request slug=<slug> "
                     "and keep building; I reply LANDED <dev sha> / EJECTED <reason> / DEPLOYED'. "
                     "Then RE-MAP ROLES: ask each peer for its role and record it (release_steward action=role "
                     "role=<role> name=<session>; action=roles lists them and flags dead sessions) - session "
                     "names change on reboot, roles do not. Then drain release_steward action=inbox."),
        }
        if child_session:
            out["warning"] = ("this process looks like a dispatched subagent (CLAUDE_CODE_CHILD_SESSION=1); "
                              "the steward must be a leader session - hand off to your leader")
        return out

    def _require_holder(self, session_id: str | None, action: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        cur = self._read_lease()
        state = self._state(cur)
        if state == "live" and cur is not None and session_id and cur.get("session_id") == session_id:
            return cur, None
        who = f"the steward is {_label(cur)}" if state == "live" and cur else "no live steward is elected"
        return None, {"ok": False, "status": "refused_not_steward", "steward": self.public_holder(),
                      "error": f"release_steward action={action} is steward-only; {who}. {KB_POINTER}"}

    def heartbeat(self, session_id: str | None) -> dict[str, Any]:
        with self._locked("release-steward"):
            cur, err = self._require_holder(session_id, "heartbeat")
            if err or cur is None:
                return err or _err("no lease")
            now = self.clock()
            cur["heartbeat_at"], cur["heartbeat_ts"] = _iso(now), now
            self._write_lease(cur)
        return {"ok": True, "status": "heartbeat", "steward": self.public_holder()}

    def release(self, session_id: str | None, note: str | None = None) -> dict[str, Any]:
        with self._locked("release-steward"):
            cur = self._read_lease()
            state = self._state(cur)
            if state == "none":
                return {"ok": True, "status": "no_steward", "steward": None}
            if state == "live" and cur is not None and (not session_id or cur.get("session_id") != session_id):
                return {"ok": False, "status": "refused_not_steward", "steward": self.public_holder(),
                        "error": f"only the steward ({_label(cur)}) can release the lane"}
            self._write_lease(None)
        self.audit("released", session_id=session_id, previous=_brief(cur), note=note, was=state)
        return {"ok": True, "status": "released",
                "next": "tell your peers the lane is open (SendMessage); the next leader claims it."}

    def handoff(self, session_id: str | None, to_session_id: str | None = None,
                to_name: str | None = None, note: str | None = None) -> dict[str, Any]:
        if not to_session_id and not to_name:
            return _err("handoff needs to_session_id and/or to_name")
        with self._locked("release-steward"):
            cur, err = self._require_holder(session_id, "handoff")
            if err or cur is None:
                return err or _err("no lease")
            now = self.clock()
            if to_session_id:
                cur.update(session_id=to_session_id, session_name=to_name or _short(to_session_id),
                           claimed_at=_iso(now), heartbeat_at=_iso(now), heartbeat_ts=now,
                           claude_pid=None, handoff_to=None, reason=note or cur.get("reason"))
                status = "handed_off"
            else:
                cur["handoff_to"] = {"name": to_name, "offered_at": _iso(now)}
                status = "handoff_offered"
            self._write_lease(cur)
        self.audit(status, session_id=session_id, to_session_id=to_session_id, to_name=to_name, note=note)
        nxt = ("the target must run release_steward action=claim to take the lane; you stay steward until they do"
               if status == "handoff_offered" else
               "tell the new steward (SendMessage) and ask it to run release_steward action=claim to bind its process")
        return {"ok": True, "status": status, "steward": self.public_holder(), "next": nxt}

    def touch(self, session_id: str | None) -> None:
        """Best-effort heartbeat (the hook calls it when the steward passes a steward-class call)."""
        with contextlib.suppress(Exception):
            self.heartbeat(session_id)

    # outbox
    def _events(self) -> list[dict[str, Any]]:
        try:
            text = self.outbox_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            with contextlib.suppress(ValueError):
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    def _append_event(self, row: dict[str, Any]) -> None:
        with open(self.outbox_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def requests(self) -> dict[str, dict[str, Any]]:
        """Fold the append-only event log into the current state per slug (latest wins)."""
        state: dict[str, dict[str, Any]] = {}
        for ev in self._events():
            slug = ev.get("slug")
            if not slug:
                continue
            if ev.get("event") == "request":
                cur = state.get(slug)
                same_head = bool(cur) and bool(ev.get("head_sha")) and cur.get("head_sha") == ev.get("head_sha")
                if cur and cur["status"] in _ADVANCED and same_head:
                    cur["rerequested_at"] = ev["ts"]  # nothing new to ship
                    continue
                state[slug] = {
                    "slug": slug, "branch": ev.get("branch"), "head_sha": ev.get("head_sha"),
                    "branches": ev.get("branches") or [],
                    "products": ev.get("products") or [], "migrations": bool(ev.get("migrations")),
                    "notes": ev.get("notes"), "verdict_ref": ev.get("verdict_ref"), "requester": ev.get("requester") or {},
                    "requested_at": ev["ts"], "status": "queued_for_steward", "kind": "request",
                    "revision": (cur or {}).get("revision", 0) + 1, "dev_sha": None, "ack_note": None,
                    "requeued": bool(cur and cur["status"] != "queued_for_steward"),
                }
            elif ev.get("event") == "request_refused":
                cur = state.get(slug)
                if cur and cur["status"] in _ADVANCED and bool(ev.get("head_sha")) and cur.get("head_sha") == ev.get("head_sha"):
                    continue  # the same already-advanced head was re-filed: nothing new to refuse
                state[slug] = {
                    "slug": slug, "branch": ev.get("branch"), "head_sha": ev.get("head_sha"),
                    "branches": ev.get("branches") or [], "products": ev.get("products") or [],
                    "migrations": bool(ev.get("migrations")), "notes": ev.get("notes"),
                    "verdict_ref": ev.get("verdict_ref"), "requester": ev.get("requester") or {},
                    "requested_at": ev["ts"], "status": "needs_resync", "kind": "request",
                    "revision": (cur or {}).get("revision", 0) + 1, "dev_sha": None, "ack_note": None,
                    "requeued": False, "needs_resync": {"failing": ev.get("failing") or [], "items": ev.get("items") or []},
                }
            elif ev.get("event") == "ack" and slug in state:
                s = state[slug]
                s["status"], s["acked_at"], s["acked_by"] = ev["outcome"], ev["ts"], ev.get("acked_by")
                if ev.get("dev_sha"):
                    s["dev_sha"] = ev["dev_sha"]
                s["ack_note"] = ev.get("note")
        return state

    def request(self, session_id: str | None, slug: str, *, name: str | None = None,
                branch: str | None = None, head_sha: str | None = None,
                products: list[str] | None = None, migrations: bool = False,
                notes: str | None = None, inline_reason: str | None = None,
                inline_note: str | None = None, branches: list[str] | None = None,
                verdict_ref: str | None = None, run_scoped: bool = False) -> dict[str, Any]:
        """NON-BLOCKING: file a delivery for the steward and return at once.

        DELIVERY CONTRACT: the filing first runs the read-only `deliverable(branch)` preflight; a branch that
        fails is NOT filed as pending - it is recorded as `needs_resync` (visible in `mine`) and the refusal
        names the failing item(s). `verdict_ref` = where the scoped keepers/tests verdict lives (item 5).

        Inline-cutoff gate (shadow): an over-cutoff delivery by an inline agent wants an
        ``inline_reason``; its absence is a WARNING naming who to dispatch, never a refusal."""
        slug = (slug or "").strip()
        if not slug or not re.fullmatch(r"[A-Za-z0-9._/-]+", slug):
            return _err("request needs slug=<slug> (the feat/<slug> name; letters, digits, . _ / -)")
        branches = [b.strip() for b in (branches or []) if b and b.strip()]
        if branches and any(not re.fullmatch(r"[A-Za-z0-9._/-]+", b) for b in branches):
            return _err("branches=[...] entries must be branch names (letters, digits, . _ / -)")
        if not branch and not branches and self._resolve_branch is not None:
            res = self._resolve_branch(slug)
            if res.get("error"):
                return _err(res["error"])
            branch = res.get("branch")
        branch = branch or (branches[0] if branches else f"feat/{slug}")
        warnings: list[str] = []
        if not branches and notes and (_TOGETHER_RE.search(notes)
                                       or any(f != branch for f in _FEAT_RE.findall(notes))):
            warnings.append("notes suggest a split delivery (together / two branches / a second feat/ name) but "
                            "no branches=[...] was given: a split delivery filed as one branch lands half. "
                            "Re-request with branches=[feat/a, feat/b] (ordered) so the steward merges them "
                            "as ONE train and enqueues once")
        if not head_sha:
            head_sha = self.resolve_head(branch)
            if not head_sha:
                warnings.append(f"could not resolve {branch}'s head; pass head_sha=<sha> so the steward "
                                "enqueues the right commit")
        contract: dict[str, Any] | None = None
        scoped_run: dict[str, Any] | None = None
        if run_scoped:
            # NEVER silently ignored: run it, or refuse with the reason.
            if branches and len(branches) > 1:
                return _err("run_scoped=true is per branch: file each branch of a split delivery with its own run_scoped request "
                            "(a verdict record judges ONE head), or run `release_steward action=deliverable run_scoped=true` per branch")
            if self._scoped_check is None:
                return _err("run_scoped=true: no CI-parity runner is configured on this store (refusing rather than ignoring the flag)")
            full_head = self.resolve_head(branch)
            if not full_head:
                return _err(f"run_scoped=true: cannot resolve {branch}'s head to judge (is the branch local?)")
            head_sha = full_head
            scoped_run = self._scoped_check(branch, full_head)
            if scoped_run.get("verdict_ref"):
                verdict_ref = scoped_run["verdict_ref"]  # green OR red: item 5 resolves the record and judges it
            else:  # UNMEASURED run: no record was minted - needs_resync naming item 5 with the reason
                contract = {"ok": False, "verdict": "needs_resync", "head_sha": full_head, "failing": ["scoped_green"],
                            "items": [{"n": 5, "name": "scoped_green", "ok": False, "detail": scoped_run.get("detail", "")}]}
        if contract is None and self._deliverable_check is not None:
            for b in (branches or [branch]):
                contract = self._deliverable_check(b, head_sha if b == branch else None, verdict_ref)
                if not contract.get("ok"):
                    break
            if contract is not None and not contract.get("ok"):
                requester = {"session_id": session_id, "name": name or _short(session_id)}
                with self._locked("ship-requests"):
                    self._append_event({
                        "ts": _iso(self.clock()), "event": "request_refused", "slug": slug, "branch": branch,
                        "head_sha": contract.get("head_sha") or head_sha, "products": products or [],
                        "migrations": bool(migrations), "notes": notes, "verdict_ref": verdict_ref,
                        "requester": requester, "branches": branches,
                        "failing": contract.get("failing") or [],
                        "items": [{k: i[k] for k in ("n", "name", "ok", "detail")} for i in contract.get("items", [])],
                    })
                    refused = self.requests()[slug]
                self.audit("request_refused", slug=slug, by=session_id, failing=contract.get("failing"))
                return {"ok": False, "status": "needs_resync", "request": refused, "deliverable": contract,
                        "failing": contract.get("failing") or [],
                        "error": f"{slug}: {deliverable_refusal(contract)}",
                        "next": ("fix the failing item(s) on the branch (you are its steward: the guardian never edits it), "
                                 "push, and re-run release_steward action=request. release_steward action=deliverable "
                                 f"slug={slug} re-checks read-only without filing.")}
        with self._locked("ship-requests"):
            before = self.requests().get(slug)
            self._append_event({
                "ts": _iso(self.clock()), "event": "request", "slug": slug, "branch": branch,
                "head_sha": head_sha, "products": products or [], "migrations": bool(migrations),
                "notes": notes, "verdict_ref": verdict_ref,
                "requester": {"session_id": session_id, "name": name or _short(session_id)},
                "branches": branches,
            })
            after = self.requests()[slug]
        holder = self.public_holder()
        out: dict[str, Any] = {
            "ok": True, "status": "queued_for_steward", "request": after,
            "deliverable": ({"verdict": contract["verdict"], "items": [{k: i[k] for k in ("n", "name", "ok")} for i in contract["items"]]}
                            if contract else None),
            "scoped": ({"ok": scoped_run.get("ok"), "detail": scoped_run.get("detail"), "verdict_ref": scoped_run.get("verdict_ref")}
                       if scoped_run is not None else None),
            "updated_head": bool(before) and before.get("head_sha") != after.get("head_sha"),
            "steward": holder if holder and holder["state"] == "live" else None,
            "next": "KEEP BUILDING the remaining work; do not wait. release_steward action=mine shows the outcome.",
        }
        if before and before["status"] in _ADVANCED and not after["requeued"]:
            out["status"], out["unchanged"] = before["status"], True
        if out["steward"] is None:
            out["hint"] = ("no live steward yet - your request is safely in the outbox. If you are a LEADER "
                           "session with shipping work, run ListAgents then release_steward action=claim and "
                           "announce it; otherwise carry on, the next steward drains the outbox.")
        gate = self.inline_gate(branch, inline_reason, inline_note)
        if gate.get("applicable"):
            out["inline_cutoff"] = {k: v for k, v in gate.items() if k != "warnings"}
            warnings.extend(gate.get("warnings") or [])
        if warnings:
            out["warnings"] = warnings
        return out

    def landed_by_branch_steward(self, slug: str, branch_hint: str | None, session_id: str | None) -> tuple[bool, str]:
        """May a NON-lease session run `task_branch landed` for `slug`? Under the guardian spec the requester owns its worktree,
        so landed's post-landing tail (pointer, primary FF, worktree cleanup) is the BRANCH STEWARD's. Allowed only when ALL hold:
        the caller is the branch's requester / pointer session / worktree-claim holder, the branch's work is already on
        refs/remotes/origin/dev, and its worktree is clean. Fails closed (any probe error -> not allowed, with the reason)."""
        if not session_id or not slug:
            return False, "no session identity"
        try:
            git = _subprocess_git(self.repo_cwd)
            req = self.requests().get(slug) or {}
            branch = branch_hint or req.get("branch")
            if not branch:
                res = resolve_branch_name(slug, git=git)
                branch = res.get("branch")
            if not branch:
                return False, f"cannot resolve {slug!r} to a branch"
            wt = _worktree_of(git, branch)
            who = None
            if (req.get("requester") or {}).get("session_id") == session_id and (not req.get("branch") or req.get("branch") == branch):
                who = "requester"
            if who is None and wt:
                with contextlib.suppress(Exception):
                    pwg = _sibling("primary_write_guard")
                    rc, gd, _e = git("rev-parse", "--path-format=absolute", "--git-common-dir")
                    primary = os.path.dirname(gd.strip().splitlines()[0]) if rc == 0 and gd.strip() else ""
                    claim = pwg.read_claims(primary).get(session_id) if primary else None
                    if claim and os.path.realpath(str(claim.get("worktree", ""))) == os.path.realpath(wt):
                        who = "worktree claim holder"
            if who is None:
                with contextlib.suppress(Exception):
                    from tools.noctus.dev import branch_pointer as bp
                    ptr = bp._latest_per_branch(bp._read_dev_ledger()).get(branch) or {}
                    if ptr.get("session") == session_id:
                        who = "pointer session"
            if who is None:
                return False, f"{session_id[:12]} is not the branch's requester, pointer session or worktree claim holder for {branch}"
            rc, head, _e = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")
            if rc != 0:
                return False, f"{branch} does not exist locally"
            state = git_landed_check(self.repo_cwd, base="refs/remotes/origin/dev")(branch, head.strip()).get("state")
            if state != "landed":
                return False, f"{branch}'s work is not on origin/dev yet (landed-check: {state}); the guardian runs landed after the queue lands it"
            if wt:
                rc, out, _e = git("--no-optional-locks", "status", "--porcelain", cwd=wt)
                if rc != 0:
                    return False, f"cannot read the worktree status of {wt}"
                _benign, real = _sibling("_benign_stash").classify_porcelain(out or "")
                if real:
                    return False, f"the worktree {wt} is dirty ({', '.join(real[:4])})"
            return True, f"{who} of {branch}, already on origin/dev, clean"
        except Exception as exc:  # noqa: BLE001 - fail closed, say why
            return False, f"could not verify ({type(exc).__name__}: {str(exc)[:120]})"

    def check_deliverable(self, slug: str | None = None, branch: str | None = None, head_sha: str | None = None,
                          verdict_ref: str | None = None, run_scoped: bool = False) -> dict[str, Any]:
        """READ-ONLY, open to every session: run the delivery contract on a branch without filing anything.
        The branch steward uses it to pre-check; the guardian re-runs it before it enqueues. A filed
        request for `slug` supplies the branch, the pinned head and the verdict_ref unless overridden."""
        slug = (slug or "").strip() or None
        req = self.requests().get(slug) if slug else None
        if not branch and req:
            branch = req.get("branch")
        if not branch and slug:
            res = (self._resolve_branch or (lambda s: {"branch": f"feat/{s}"}))(slug)
            if res.get("error"):
                return _err(res["error"])
            branch = res.get("branch")
        if not branch:
            return _err("deliverable needs slug=<slug> or branch=<branch>")
        head_sha = head_sha or (req or {}).get("head_sha")
        verdict_ref = verdict_ref or (req or {}).get("verdict_ref")
        if run_scoped:  # minutes: judge the head the way CI does (CI-blocking keepers + real-tree tests, env-scrubbed)
            res = deliverable(branch, head_sha=head_sha, verdict_ref=verdict_ref, scoped_check=export_ci_parity_check())
        else:
            check = self._deliverable_check or (lambda b, h, v: deliverable(b, head_sha=h, verdict_ref=v))
            res = check(branch, head_sha, verdict_ref)
        return {"ok": True, "status": res.get("verdict", "needs_resync"), "deliverable": res,
                "failing": res.get("failing") or [],
                "next": ("deliverable: the guardian can enqueue (pure push)" if res.get("ok")
                         else "needs_resync: the branch steward fixes the failing item(s) on the branch, pushes, re-requests")}

    def inline_gate(self, branch: str, inline_reason: str | None, inline_note: str | None) -> dict[str, Any]:
        """Injectable seam (tests assign ``store.inline_gate``): the real gate looks up the branch's
        pointer and measures its delivery. Never raises - a failure is a warning."""
        if self._inline_gate is not None:
            return self._inline_gate(branch, inline_reason, inline_note)
        try:
            from tools.noctus.dev import branch_pointer as bp
            from tools.noctus.dev import orchestrator_inline_cutoff as oic
            pointer = bp._latest_per_branch(bp._read_dev_ledger()).get(branch)
            return oic.gate_delivery(branch, pointer=pointer, inline_reason=inline_reason,
                                     inline_note=inline_note, root=Path(__file__).resolve().parents[5])
        except Exception as exc:  # noqa: BLE001 - shadow gate: loud, never a refusal
            return {"applicable": True, "warnings": [f"inline cutoff unmeasured: {exc}"]}

    def mine(self, session_id: str | None, include_done: bool = False) -> dict[str, Any]:
        rows = [r for r in self.requests().values() if r["requester"].get("session_id") == session_id]
        if not include_done:
            rows = [r for r in rows if r["status"] not in ("deployed", "withdrawn")]
        ni = [n for n in self.needs_info() if n["state"] in ("open", "expired")
              and n["addressed_to"].get("session_id") == session_id]
        return {"ok": True, "status": "mine", "requests": sorted(rows, key=lambda r: r["requested_at"]),
                "needs_info": ni}

    def _classify(self, r: dict[str, Any]) -> dict[str, Any]:
        """landed | pending | unresolvable for one request (a train is landed only when ALL its branches are)."""
        names = r.get("branches") or [r.get("branch") or f"feat/{r['slug']}"]
        results = []
        for b in names:
            try:
                results.append(self.landed_check(b, r.get("head_sha") if len(names) == 1 else None))
            except Exception as exc:  # noqa: BLE001 - a failed probe is surfaced, never read as "landed"
                results.append({"state": "unresolvable", "reason": str(exc)[:200]})
        states = [x.get("state") for x in results]
        if "unresolvable" in states:
            return {"state": "unresolvable", "reason": next(x.get("reason") for x in results
                                                            if x.get("state") == "unresolvable")}
        if "uncertain" in states:
            return {"state": "uncertain", "evidence": [x.get("evidence") for x in results if x.get("state") == "uncertain"]}
        if all(st == "landed" for st in states):
            return {"state": "landed", "dev_sha": results[-1].get("dev_sha"),
                    "method": "+".join(sorted({str(x.get("method") or "cherry") for x in results}))}
        return {"state": "pending"}

    def _partition(self, pending: list[dict[str, Any]]) -> tuple[list, list, list, list]:
        todo, landed, unres, unsure = [], [], [], []
        for r in pending:
            c = self._classify(r)
            if c["state"] == "landed":
                landed.append({**r, "landed_detected": c.get("dev_sha") or "origin/dev",
                               "method": c.get("method") or "cherry"})
            else:
                todo.append(r)
                if c["state"] == "unresolvable":
                    unres.append({**r, "unresolvable_reason": c.get("reason")})
                elif c["state"] == "uncertain":
                    unsure.append({**r, "evidence": c.get("evidence")})
        return todo, landed, unres, unsure

    def inbox(self, include_done: bool = False) -> dict[str, Any]:
        rows = list(self.requests().values())
        open_rows = sorted((r for r in rows if r["status"] in _OPEN_STATUSES), key=lambda r: r["requested_at"])
        todo, already_landed, unresolvable, uncertain = self._partition(open_rows)
        # only never-enqueued requests drain; an `enqueued`/`ejected` row not yet in dev is the queue's, not the inbox's
        pending = [r for r in todo if r["status"] == "queued_for_steward"]
        unresolvable = [r for r in unresolvable if r["status"] == "queued_for_steward"]
        shown = sorted(rows, key=lambda r: r["requested_at"]) if include_done else pending
        grouped: dict[str, list[str]] = {}
        for r in shown:
            grouped.setdefault(r["requester"].get("name") or _short(r["requester"].get("session_id")), []).append(r["slug"])
        drain: list[str] = []
        for r in pending:
            if len(r.get("branches") or []) > 1:
                names = ",".join(b.removeprefix("feat/") for b in r["branches"])
                drain.append(f"task_branch action=train slug=train-{r['slug']} slugs=[{names}] confirm=True")
                drain.append(f"task_branch action=enqueue slug=train-{r['slug']} confirm=True")
                self.audit("train_drain", slug=r["slug"], branches=r["branches"])
            else:
                drain.append(f"task_branch action=enqueue slug={r['slug']} confirm=True")
        decided = {d["slug"] for d in self.decisions()}
        threads = [n for n in self.needs_info() if n["state"] in ("answered", "expired") and n["slug"] not in decided]
        escalate = [n for n in threads if n["state"] == "expired" and n.get("owner_fallback")]
        out: dict[str, Any] = {
            "ok": True, "status": "inbox", "pending": len(pending), "by_requester": grouped,
            "needs_info": threads, "escalate_to_owner": escalate,
            "requests": shown, "already_landed": already_landed, "unresolvable": unresolvable,
            "uncertain": uncertain,
            "drain": drain,
            "next": ("drain ALL pending in one pass (enqueue each so riders batch in the merge queue; a multi-branch "
                     "delivery is ONE train then ONE enqueue), ack each "
                     "as enqueued, ack landed/ejected/deployed as they resolve, and SendMessage each requester "
                     "LANDED <dev sha> / EJECTED <reason> / DEPLOYED") if pending else "inbox empty",
        }
        if already_landed:
            out["next"] += (f" | {len(already_landed)} request(s) are ALREADY in origin/dev (method per row: cherry|post_image|range_diff): ack them "
                            "landed in one call with release_steward action=reconcile confirm=True")
        if uncertain:
            out["next"] = (f"UNCERTAIN: {len(uncertain)} request(s) are PARTIALLY in origin/dev (see `uncertain[].evidence`: "
                           "matched/unmatched files) - NEVER auto-acked; decide by hand (ask the requester / diff the "
                           "unmatched files) | ") + out["next"]
            self.audit("reconcile_uncertain", slugs=[r["slug"] for r in uncertain])
        if any(n["state"] == "answered" for n in threads):
            out["next"] += " | needs_info ANSWERED (see needs_info[]): read the answer, then act or action=decision"
        if escalate:
            out["next"] += (f" | escalate_to_owner: {len(escalate)} needs_info expired with no position "
                            f"({', '.join(n['id'] for n in escalate)}) - tell the owner; nothing was sent for you")
            self.audit("needs_info_escalate", ids=[n["id"] for n in escalate])
        if unresolvable:
            out["next"] += (f" | {len(unresolvable)} request(s) could not be resolved to a branch/sha: "
                            "ask the requester to re-request with head_sha=")
        return out

    def reconcile(self, session_id: str | None, confirm: bool = False) -> dict[str, Any]:
        """Ack every request whose commits are already in origin/dev as `landed` (steward-only)."""
        with self._locked("release-steward"):
            _cur, err = self._require_holder(session_id, "reconcile")
        if err:
            return err
        open_rows = [r for r in self.requests().values() if r["status"] in _OPEN_STATUSES]
        _todo, landed, _unres, uncertain = self._partition(sorted(open_rows, key=lambda r: r["requested_at"]))
        slugs = [r["slug"] for r in landed]
        if not confirm:
            return {"ok": True, "status": "planned", "would_ack": slugs,
                    "methods": {r["slug"]: r["method"] for r in landed},
                    "uncertain": [{"slug": r["slug"], "evidence": r["evidence"]} for r in uncertain],
                    "next": "re-run with confirm=True to ack them landed" if slugs else "nothing already landed"}
        for r in landed:
            self.ack(session_id, r["slug"], "landed", dev_sha=r["landed_detected"], note=f"reconciled: already in origin/dev ({r['method']})")
        if slugs:
            self.audit("reconcile", session_id=session_id, slugs=slugs,
                       methods={r["slug"]: r["method"] for r in landed})
        return {"ok": True, "status": "reconciled", "acked": slugs,
                "uncertain": [{"slug": r["slug"], "evidence": r["evidence"]} for r in uncertain],
                "next": "SendMessage each requester LANDED" if slugs else "nothing already landed"}

    # roles (durable ROLE -> session map: names change on reboot, roles do not)
    def _read_roles(self) -> dict[str, dict[str, Any]]:
        try:
            doc = json.loads(self.roles_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _write_roles(self, roles: dict[str, dict[str, Any]]) -> None:
        tmp = self.roles_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(roles, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.roles_path)

    def _role_state(self, row: dict[str, Any]) -> str:
        if self.clock() - float(row.get("heartbeat_ts") or 0) > self.default_ttl_s:
            return "stale"
        if not self.pid_alive(row.get("claude_pid")):
            return "stale"
        return "live"

    def role_set(self, session_id: str | None, role: str, name: str | None = None,
                 claude_pid: int | None = None, to_session_id: str | None = None) -> dict[str, Any]:
        role = (role or "").strip()
        if not role or not _ROLE_RE.fullmatch(role):
            return _err("role needs role=<role> (letters, digits, . _ : / -), e.g. agents | products/sw | "
                        "assistant | branch-steward:<branch>")
        if role == "dev-steward":
            return _err("dev-steward is derived from the steward lease (release_steward action=claim), not settable")
        if role.startswith("branch-steward:") and not role.split(":", 1)[1]:
            return _err("branch-steward needs a branch: role=branch-steward:<branch>")
        target = to_session_id or session_id
        if not target:
            return _err(f"no session identity ({SESSION_ENV} unset)")
        other = bool(to_session_id) and to_session_id != session_id
        if other:
            with self._locked("release-steward"):
                _cur, err = self._require_holder(session_id, "role (for another session)")
            if err:
                return err
        now = self.clock()
        row = {"session_id": target, "name": name or _short(target), "set_at": _iso(now), "heartbeat_ts": now,
               "set_by": session_id, "claude_pid": None if other else claude_pid}
        with self._locked("release-steward-roles"):
            roles = self._read_roles()
            previous = roles.get(role)
            roles[role] = row
            self._write_roles(roles)
        self.audit("role_set", role=role, session_id=target, name=row["name"], set_by=session_id,
                   previous=(previous or {}).get("name"))
        return {"ok": True, "status": "role_set", "role": {**row, "state": "live"}}

    def role_clear(self, session_id: str | None, role: str) -> dict[str, Any]:
        with self._locked("release-steward-roles"):
            roles = self._read_roles()
            row = roles.get(role)
            if row is None:
                return _err(f"no role {role!r} is registered")
            if row.get("session_id") != session_id:
                with self._locked("release-steward"):
                    _cur, err = self._require_holder(session_id, "role clear (someone else's)")
                if err:
                    return err
            roles.pop(role)
            self._write_roles(roles)
        self.audit("role_clear", role=role, session_id=session_id, was=row.get("name"))
        return {"ok": True, "status": "role_cleared", "role": role}

    # Refreshed between release_steward calls by scripts/hooks/claude-guard-session-heartbeat.py (SessionStart +
    # UserPromptSubmit; advisory, throttled, own-role-only).
    def role_touch(self, session_id: str | None, claude_pid: int | None = None) -> None:
        """Best-effort liveness refresh of the roles this session holds (every action calls it): the heartbeat
        and, when the caller's pid is known, the pid (a restart changes it; a stale pid must not read as dead)."""
        if not session_id:
            return
        with contextlib.suppress(Exception), self._locked("release-steward-roles"):
            roles = self._read_roles()
            hit = False
            for row in roles.values():
                if row.get("session_id") == session_id:
                    row["heartbeat_ts"], hit = self.clock(), True
                    if claude_pid:  # the caller's own pid, for a row that names the caller's session
                        row["claude_pid"] = claude_pid
            if hit:
                self._write_roles(roles)

    def session_state(self, session_id: str | None) -> str:
        """`live` | `dead` | `unknown` for a session, from the steward registry (role rows + the lease).

        `dead` is the claim that lets someone else's worktree be removed, so it needs BOTH signals: the recorded
        process is gone AND the heartbeat is older than the TTL (every action refreshes both - `role_touch` also
        re-records the caller's pid, which changes across /clear or a restart). A fresh heartbeat or a live pid
        is `live`. A stale heartbeat with no recorded pid is `unknown` (no evidence either way), and so is no
        record at all - callers that must not act on someone else's work treat `unknown` as live."""
        if not session_id:
            return "unknown"
        rows = [r for r in self._read_roles().values() if r.get("session_id") == session_id]
        lease = self._read_lease()
        if lease and lease.get("session_id") == session_id and not lease.get("corrupt"):
            rows.append(lease)
        if not rows:
            return "unknown"
        now, all_dead = self.clock(), True
        for r in rows:
            ttl = int(r.get("ttl_s") or self.default_ttl_s)
            if now - float(r.get("heartbeat_ts") or 0) <= ttl:
                return "live"
            pid = r.get("claude_pid")
            if pid and self.pid_alive(pid):
                return "live"
            if not pid:
                all_dead = False
        return "dead" if all_dead else "unknown"

    def roles(self) -> dict[str, Any]:
        out: dict[str, dict[str, Any]] = {}
        stale: list[str] = []
        lease, state = self.holder()
        if lease and not lease.get("corrupt"):
            out["dev-steward"] = {"session_id": lease.get("session_id"), "name": lease.get("session_name"),
                                  "derived": True, "state": state}
            if state != "live":
                stale.append("dev-steward")
        for role, row in sorted(self._read_roles().items()):
            st = self._role_state(row)
            out[role] = {**{k: v for k, v in row.items() if k != "heartbeat_ts"}, "state": st}
            if st != "live":
                stale.append(role)
        return {"ok": True, "status": "roles", "roles": out, "stale_roles": stale,
                "next": ("stale roles: the session is gone - ask who took it over (ListAgents) and re-map with "
                         "release_steward action=role") if stale else "all mapped roles live"}

    def ack(self, session_id: str | None, slug: str, outcome: str, dev_sha: str | None = None,
            note: str | None = None) -> dict[str, Any]:
        if outcome not in OUTCOMES:
            return _err(f"outcome must be one of {'|'.join(OUTCOMES)}")
        if outcome in ("withdrawn", "needs_resync") and not (note or "").strip():
            return _err(f"outcome={outcome} needs notes=<the reason>")
        with self._locked("release-steward"):
            _cur, err = self._require_holder(session_id, "ack")
        if err:
            return err
        with self._locked("ship-requests"):
            if self.requests().get(slug) is None:
                return _err(f"no request for slug {slug!r} in the outbox")
            self._append_event({"ts": _iso(self.clock()), "event": "ack", "slug": slug, "outcome": outcome,
                                "dev_sha": dev_sha, "note": note, "acked_by": session_id})
            after = self.requests()[slug]
        self.touch(session_id)
        words = {"enqueued": "ENQUEUED", "landed": f"LANDED {dev_sha or ''}".strip(),
                 "ejected": f"EJECTED {note or ''}".strip(), "deployed": "DEPLOYED",
                 "withdrawn": f"WITHDRAWN {note or ''}".strip(),
                 "needs_resync": f"NEEDS_RESYNC {note or ''}".strip()}
        return {"ok": True, "status": f"acked_{outcome}", "request": after,
                "next": f"SendMessage {after['requester'].get('name')}: {words[outcome]} (slug {slug})"}

    def withdraw(self, session_id: str | None, slug: str, note: str | None = None) -> dict[str, Any]:
        """The requesting session (or the steward) takes a request back; it leaves pending/drain."""
        with self._locked("ship-requests"):
            cur = self.requests().get(slug)
            if cur is None:
                return _err(f"no request for slug {slug!r} in the outbox")
            with self._locked("release-steward"):
                _l, not_steward = self._require_holder(session_id, "withdraw")
            if not session_id or (cur["requester"].get("session_id") != session_id and not_steward):
                return {"ok": False, "status": "refused_not_requester", "steward": self.public_holder(),
                        "error": f"only the requesting session or the steward may withdraw {slug!r}. {KB_POINTER}"}
            if cur["status"] == "withdrawn":
                return {"ok": True, "status": "withdrawn", "unchanged": True, "request": cur}
            self._append_event({"ts": _iso(self.clock()), "event": "ack", "slug": slug, "outcome": "withdrawn",
                                "dev_sha": None, "note": (note or "").strip() or "withdrawn by requester",
                                "acked_by": session_id})
            after = self.requests()[slug]
        self.audit("withdraw", slug=slug, by=session_id, was=cur["status"], note=after["ack_note"])
        return {"ok": True, "status": "withdrawn", "request": after,
                "next": "nothing more to do; request the slug again to re-open it as a new revision"}

    # -- steward<->requester exchange records (append-only, same outbox) --------
    def _kind_events(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self._events() if e.get("event") == kind]

    def decisions(self, slug: str | None = None) -> list[dict[str, Any]]:
        return [{**e, "kind": "decision"} for e in self._kind_events("decision") if slug in (None, e.get("slug"))]

    def needs_info(self, slug: str | None = None) -> list[dict[str, Any]]:
        """Fold needs_info + position rows into threads: open | answered | expired (answered wins)."""
        positions = self._kind_events("position")
        now = self.clock()
        out = []
        for e in self._kind_events("needs_info"):
            if slug not in (None, e.get("slug")):
                continue
            ans = next((p for p in positions if p.get("ref") == e["id"]), None)
            expired = now >= float(e.get("deadline_epoch") or 0)
            out.append({**e, "kind": "needs_info",
                        "state": "answered" if ans else ("expired" if expired else "open"),
                        "answer": ans.get("text") if ans else None, "answered_by": ans.get("by") if ans else None})
        return out

    def ask(self, session_id: str | None, slug: str, question: str, addressed_to: str | None = None,
            deadline_min: float | None = None) -> dict[str, Any]:
        """Steward-only: ONE bounded question about a slug (kind=needs_info)."""
        with self._locked("release-steward"):
            _cur, err = self._require_holder(session_id, "needs_info")
        if err:
            return err
        question = (question or "").strip()
        if not question:
            return _err("needs_info needs question=<one bounded question>")
        with self._locked("ship-requests"):
            req = self.requests().get(slug)
            if req is None:
                return _err(f"no request for slug {slug!r} in the outbox")
            target: dict[str, Any] = {"role": None, "session_id": req["requester"].get("session_id")}
            warn = None
            if addressed_to:
                row = self._read_roles().get(addressed_to)
                if addressed_to == "dev-steward":
                    row = self._read_lease()
                if row and row.get("session_id"):
                    target = {"role": addressed_to, "session_id": row["session_id"]}
                else:
                    warn = f"role {addressed_to!r} is not registered; addressed to the requester session instead"
            now = self.clock()
            minutes = float(deadline_min) if deadline_min else NEEDS_INFO_DEFAULT_MIN
            n = len(self._kind_events("needs_info")) + 1
            row = {"ts": _iso(now), "event": "needs_info", "id": f"ni-{n}", "slug": slug, "question": question,
                   "addressed_to": target, "asked_by": session_id, "deadline_ts": _iso(now + minutes * 60),
                   "deadline_epoch": now + minutes * 60, "owner_fallback": True}
            self._append_event(row)
        self.audit("needs_info", id=row["id"], slug=slug, by=session_id, addressed_to=target)
        out = {"ok": True, "status": "needs_info_asked", "needs_info": {**row, "kind": "needs_info", "state": "open"},
               "next": f"SendMessage the addressee: needs_info {row['id']} on {slug} (answer: action=position ref={row['id']})"}
        if warn:
            out["warnings"] = [warn]
        return out

    def position(self, session_id: str | None, slug: str, text: str, ref: str | None = None) -> dict[str, Any]:
        """A requester's answer to a needs_info, or any session's stance on a slug (kind=position)."""
        text = (text or "").strip()
        if not text:
            return _err("position needs notes=<your answer or stance>")
        if not session_id:
            return _err(f"no session identity ({SESSION_ENV} unset)")
        with self._locked("ship-requests"):
            if self.requests().get(slug) is None:
                return _err(f"no request for slug {slug!r} in the outbox")
            if ref is None:  # default: the latest unanswered needs_info on this slug addressed to me
                mine = [n for n in self.needs_info(slug) if n["state"] != "answered"
                        and n["addressed_to"].get("session_id") == session_id]
                ref = mine[-1]["id"] if mine else None
            elif not any(n["id"] == ref and n["slug"] == slug for n in self.needs_info()):
                return _err(f"no needs_info {ref!r} on slug {slug!r}")
            row = {"ts": _iso(self.clock()), "event": "position", "slug": slug, "ref": ref, "text": text, "by": session_id}
            self._append_event(row)
        self.audit("position", slug=slug, ref=ref, by=session_id)
        return {"ok": True, "status": "position_recorded", "position": {**row, "kind": "position"},
                "next": "KEEP BUILDING; the steward reads this from its inbox"}

    def decide(self, session_id: str | None, slug: str, text: str) -> dict[str, Any]:
        """Steward-only: the final call on a slug (kind=decision). Does not change the request's status."""
        with self._locked("release-steward"):
            _cur, err = self._require_holder(session_id, "decision")
        if err:
            return err
        text = (text or "").strip()
        if not text:
            return _err("decision needs notes=<the call>")
        with self._locked("ship-requests"):
            if self.requests().get(slug) is None:
                return _err(f"no request for slug {slug!r} in the outbox")
            row = {"ts": _iso(self.clock()), "event": "decision", "slug": slug, "text": text, "decided_by": session_id}
            self._append_event(row)
        self.audit("decision", slug=slug, by=session_id)
        return {"ok": True, "status": "decision_recorded", "decision": {**row, "kind": "decision"},
                "next": f"SendMessage the requester: DECISION on {slug}: {text}"}

    def status(self, session_id: str | None) -> dict[str, Any]:
        lease, state = self.holder()
        reqs = list(self.requests().values())
        queued = [r for r in reqs if r["status"] == "queued_for_steward"]
        _todo, landed, unres, unsure = self._partition([r for r in reqs if r["status"] in _OPEN_STATUSES])
        unres = [r for r in unres if r["status"] == "queued_for_steward"]
        roles = self.roles()
        return {
            "ok": True, "status": "status", "state": state, "steward": self.public_holder(),
            "i_am_steward": bool(lease and state == "live" and session_id and lease.get("session_id") == session_id),
            "session_id": session_id, "ttl_default_s": self.default_ttl_s,
            "roles": roles["roles"], "stale_roles": roles["stale_roles"],
            "outbox": {"pending": len(queued) - sum(1 for r in landed if r["status"] == "queued_for_steward"),
                       "already_landed": len(landed),
                       "unresolvable": len(unres), "uncertain": len(unsure),
                       "enqueued": sum(1 for r in reqs if r["status"] == "enqueued")},
            "mine": self.mine(session_id)["requests"],
            "next": ("no live steward: ListAgents; the leader with shipping work claims + announces; everyone "
                     "else files deliveries with action=request and keeps building") if state != "live" else
                    "file deliveries with action=request; the steward drains the outbox",
        }


# -- classification: what is a steward-class call? --------------------------

@dataclass(frozen=True)
class Gated:
    kind: str
    slug: str | None = None
    branch: str | None = None


def tool_key(tool_name: str) -> str | None:
    """Canonical dotted name for an MCP tool_name or an already-dotted one."""
    if tool_name in _MCP_NAMES:
        return _MCP_NAMES[tool_name]
    return tool_name if tool_name.startswith("noctus.") else None


def classify_tool(tool_name: str, tool_input: dict[str, Any] | None) -> Gated | None:
    """Is this MCP call (with these arguments) steward-only? Reads and dry-runs: None."""
    key = tool_key(tool_name)
    args = tool_input or {}
    if key is None or key == "noctus.dev.release_steward":
        return None
    confirm = bool(args.get("confirm", False))
    if key == "noctus.dev.task_branch":
        action = args.get("action") or "status"
        return (Gated(f"task_branch {action}", args.get("slug"), args.get("branch"))
                if action in _TASK_BRANCH_GATED and confirm else None)
    if key == "noctus.dev.release":
        stage = args.get("stage") or "status"
        return Gated(f"release {stage}") if stage in _RELEASE_GATED and confirm else None
    if key == "noctus.dev.record_applied_migrations":
        return Gated("record_applied_migrations")  # always a write (it integrates to dev)
    if key == "noctus.dev.supabase_breaker":
        # F11b (2026-11-10): re-arming/tripping the prod Supabase breaker - incl. the fleet key that stops every
        # product's background workers - is a prod mutation. Applied = guardian-only; status and plans stay open. The
        # urgent single-product case keeps the platform-admin route (AAL2), which already refuses source=fleet.
        action = args.get("action") or "status"
        return Gated(f"supabase_breaker {action}") if action in {"rearm", "trip"} and confirm else None
    if key in {"noctus.dev.deploy_pull", "noctus.dev.deploy_image", "noctus.dev.migrate_product", "noctus.vps.recreate"}:
        return Gated(key.removeprefix("noctus.").replace(".", " ")) if confirm else None
    return None


def _sibling(name: str):
    """Load a sibling guard module (works as a package member and when this file is loaded by path)."""
    mod = sys.modules.get(f"noc_{name}")
    if mod is not None:
        return mod
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"noc_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_OVERRIDE_INLINE = re.compile(rf"(?:^|[\s;&|(]){OVERRIDE_ENV}=('[^']*'|\"[^\"]*\"|[^\s;&|)]*)")
#: cli.py flag -> (allowed values or None, its confirm flag, label)
_CLI_GATES: dict[str, tuple[set[str] | None, str, str]] = {
    "--task-branch": (_TASK_BRANCH_GATED, "--task-branch-confirm", "task_branch"),
    "--release": (_RELEASE_GATED, "--release-confirm", "release"),
    "--deploy-pull": (None, "--deploy-confirm", "deploy_pull"),
    "--deploy-image": (None, "--deploy-image-confirm", "deploy_image"),
    "--migrate-product": (None, "--migrate-product-confirm", "migrate_product"),
    # F11b P1-3: the breaker's CLI is a bare switch; the action lives in its own flag (see _CLI_GATE_VALUE_FLAG)
    "--supabase-breaker": ({"rearm", "trip"}, "--supabase-breaker-confirm", "supabase_breaker"),
}
#: gates whose gated VALUE is carried by a separate flag instead of the gate flag itself
_CLI_GATE_VALUE_FLAG = {"--supabase-breaker": "--supabase-breaker-action"}
#: every flag a CLI gate reads - an abbreviation of any of them is judged as the flag itself (argparse accepts
#: unambiguous prefixes unless allow_abbrev=False: `--deploy-image-conf` ran as --deploy-image-confirm, ungated,
#: 2026-11-10; cli.py now refuses abbreviations, and this backstop covers a checkout with an older cli.py)
_CLI_GATE_FLAGS = ({f for f in _CLI_GATES} | {c for _a, c, _l in _CLI_GATES.values()}
                   | set(_CLI_GATE_VALUE_FLAG.values()))


def _gate_flag_names(flag: str) -> set[str]:
    """`flag` itself when it is a gate flag, else every gate flag it abbreviates (over-gating is the safe side)."""
    if flag in _CLI_GATE_FLAGS or len(flag) < 4:
        return {flag}
    return {k for k in _CLI_GATE_FLAGS if k.startswith(flag)} or {flag}
_GIT_FLAGS_WITH_OPERAND = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_PUSH_FLAGS_WITH_OPERAND = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


def _push_dst(refspec: str) -> str:
    spec = refspec.lstrip("+")
    dst = spec.rsplit(":", 1)[1] if ":" in spec else spec
    return dst.removeprefix("refs/heads/")


def _git_push_gate(args: list[str]) -> Gated | None:
    i = 0
    while i < len(args):  # find the subcommand, skipping git's global flags
        if args[i] in _GIT_FLAGS_WITH_OPERAND:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            break
    if i >= len(args) or args[i] != "push":
        return None
    rest = args[i + 1:]
    if any(a in {"-n", "--dry-run"} for a in rest):
        return None
    if any(a in {"--all", "--mirror"} for a in rest):
        return Gated("git push --all/--mirror (includes dev)")
    pos: list[str] = []
    j = 0
    while j < len(rest):
        if rest[j] in _PUSH_FLAGS_WITH_OPERAND:
            j += 2
            continue
        if not rest[j].startswith("-"):
            pos.append(rest[j])
        j += 1
    for spec in pos[1:]:  # pos[0] is the remote
        dst = _push_dst(spec)
        if dst in PROTECTED_BRANCHES or dst.startswith(QUEUE_PREFIX):
            return Gated(f"git push -> {dst}")
    return None


def _cli_gate(words: list[str]) -> Gated | None:
    if not any(os.path.basename(w) == "cli.py" for w in words[:4]):
        return None
    vals: dict[str, str | None] = {}
    flags: set[str] = set()
    value_flags = set(_CLI_GATE_VALUE_FLAG.values())
    for idx, w in enumerate(words):
        if not w.startswith("--"):
            continue
        raw, eq, val = w.partition("=")
        for flag in _gate_flag_names(raw):
            flags.add(flag)
            if flag in _CLI_GATES or flag in value_flags:
                nxt = words[idx + 1] if idx + 1 < len(words) else None
                vals[flag] = val if eq else (nxt if nxt and not nxt.startswith("--") else None)
    for flag, (allowed, confirm_flag, label) in _CLI_GATES.items():
        value_flag = _CLI_GATE_VALUE_FLAG.get(flag)
        if value_flag is not None and flag in flags:
            vals[flag] = vals.get(value_flag)
        if flag in vals and confirm_flag in flags and (allowed is None or vals[flag] in allowed):
            if flag == "--task-branch":  # carry the slug/branch so `landed` can be judged per branch (branch-steward rule)
                extra = {}
                for w in words:
                    k, eq, v = w.partition("=")
                    if k in ("--task-branch-slug", "--task-branch-branch") and eq:
                        extra[k] = v
                for idx, w in enumerate(words[:-1]):
                    if w in ("--task-branch-slug", "--task-branch-branch") and not words[idx + 1].startswith("--"):
                        extra[w] = words[idx + 1]
                return Gated(f"{label} {vals[flag]}", extra.get("--task-branch-slug"), extra.get("--task-branch-branch"))
            return Gated(f"{label} {vals[flag]}" if allowed else label)
    return None


def _scan_segments(command: str, found: list[Gated], depth: int = 0) -> None:
    h = _sibling("heavy_run_guard")
    for seg in h._segments(command):
        words, _env = h._strip_prefix(seg)
        if not words:
            continue
        cmd = os.path.basename(words[0])
        if cmd in h._SHELLS and depth < 3 and "-c" in words:
            idx = words.index("-c")
            if idx + 1 < len(words):
                _scan_segments(words[idx + 1], found, depth + 1)
            continue
        hit = _git_push_gate(words[1:]) if cmd == "git" else _cli_gate(words)
        if hit:
            found.append(hit)


def classify_bash(command: str) -> Gated | None:
    """First steward-class action in a Bash command, else None (false positives are the failure to avoid)."""
    if not command.strip():
        return None
    h = _sibling("heavy_run_guard")
    found: list[Gated] = []
    text, bodies = h._split_heredocs(command)
    try:
        for chunk in h._chunks(text):
            _scan_segments(chunk, found)
        for feeder, body in bodies:
            if h._feeds_a_shell(feeder):
                for chunk in h._chunks(body):
                    _scan_segments(chunk, found)
    except ValueError:
        # unparseable: refuse only when the dangerous words are plainly there
        if re.search(r"git\s+push\b.*\b(dev|main|prod|mq/)", text) or re.search(
                r"--(task-branch[ =](enqueue|integrate|landed)|release[ =](bless|promote|backmerge)).*-confirm", text):
            found.append(Gated("unparseable steward-class command"))
    return found[0] if found else None


def is_claim_call(tool_name: str, tool_input: dict[str, Any] | None) -> bool:
    if tool_key(tool_name) == "noctus.dev.release_steward":
        return (tool_input or {}).get("action") == "claim"
    if tool_name == "Bash":
        return bool(re.search(r"--release-steward[ =]claim\b", (tool_input or {}).get("command") or ""))
    return False


# -- the ONE decision (hook end AND tool end) --------------------------------

def _override_reason(command: str | None, env: dict[str, str]) -> str:
    if command:
        for m in _OVERRIDE_INLINE.finditer(command):
            val = m.group(1).strip("'\"").strip()
            if val:
                return val
    return (env.get(OVERRIDE_ENV) or "").strip()


def decide_call(gated: Gated, session_id: str | None, *, store: StewardStore,
                env: dict[str, str] | None = None, command: str | None = None) -> dict[str, Any] | None:
    """None = allow; else `{"reason", "status": "refused_not_steward", "steward": ...}`."""
    env = env if env is not None else dict(os.environ)
    lease, state = store.holder()
    if state == "live" and lease and session_id and lease.get("session_id") == session_id:
        store.touch(session_id)
        return None
    branch_steward_note = ""
    if gated.kind == "task_branch landed" and gated.slug and session_id:
        ok, why = store.landed_by_branch_steward(gated.slug, gated.branch, session_id)
        if ok:
            store.audit("landed_by_branch_steward", session_id=session_id, slug=gated.slug, via=why)
            return None
        branch_steward_note = (" `landed` is the BRANCH STEWARD's post-landing tail once its work is on origin/dev, its worktree is "
                               f"clean and it is the branch's requester / pointer session / claim holder - not allowed here: {why}.")
    override = _override_reason(command, env)
    short_note = ""
    if override:
        if len(override) >= OVERRIDE_MIN_CHARS:
            store.audit("override", session_id=session_id, action=gated.kind, reason=override,
                        steward=_brief(lease) if state == "live" else None)
            sys.stderr.write(f"[noc-guard:release-steward] override accepted ({gated.kind}): {override!r}\n")
            return None
        short_note = f" {OVERRIDE_ENV} needs a written reason of at least {OVERRIDE_MIN_CHARS} chars (got {len(override)})."
    ask = REQUEST_CMD.replace("<slug>", gated.slug or "<slug>")
    escape = f"Override (recorded): prefix {OVERRIDE_ENV}=<reason of 10+ chars>.{short_note}"
    if state == "live" and lease:
        reason = (f"{gated.kind} is steward-only: ONE elected session handles CI queueing AND deploy, and that is "
                  f"{_label(lease)} - not you. Gated is not blocked: {ask}. "
                  f"Reads and dry-runs stay open.{branch_steward_note} {escape} {KB_POINTER}")
    else:
        why = "the previous steward's lease is stale" if state == "stale" else "no release steward is elected"
        reason = (f"{gated.kind} is steward-only and {why}. Run ListAgents and `release_steward action=status`; if you "
                  "are a LEADER session (interactive, top-level, not a dispatched subagent) with shipping work and no "
                  "other leader holds the lane, run `release_steward action=claim` and announce it to every peer with "
                  f"SendMessage. Otherwise {ask}.{branch_steward_note} {escape} {KB_POINTER}")
    return {"reason": reason, "status": "refused_not_steward", "steward": store.public_holder()}


def decide(payload: dict[str, Any], *, store: StewardStore | None = None,
           env: dict[str, str] | None = None) -> dict[str, Any] | None:
    """The PreToolUse verdict for one hook payload (None = allow)."""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    env = env if env is not None else dict(os.environ)
    store = store or StewardStore()
    command = tool_input.get("command") if tool_name == "Bash" else None
    if is_claim_call(tool_name, tool_input) and payload.get("agent_id"):
        return {"reason": ("the release steward must be a LEADER session (interactive, top-level), never a "
                           "dispatched subagent - ask your leader to claim; its subagents act under its lease. "
                           f"{KB_POINTER}"), "status": "refused_subagent_claim", "steward": store.public_holder()}
    gated = classify_bash(command or "") if tool_name == "Bash" else classify_tool(tool_name, tool_input)
    if gated is None:
        return None
    return decide_call(gated, payload.get("session_id"), store=store, env=env, command=command)


def tool_refusal(tool_name: str, args: dict[str, Any], *, store: StewardStore | None = None,
                 env: dict[str, str] | None = None) -> dict[str, Any] | None:
    """Backstop at the MCP tool layer: the same decision, identity from the server's own env.

    Returns a tool-result dict (`ok: False, status: 'refused_not_steward'`) or None. A caller with
    NO session identity (CI, ops script, non-Claude client) is outside the steward protocol:
    allowed, but audited as `unattributed` - never silent.
    """
    gated = classify_tool(tool_name, args)
    if gated is None:
        return None
    env = env if env is not None else dict(os.environ)
    store = store or StewardStore()
    session_id = env.get(SESSION_ENV)
    if not session_id:
        store.audit("unattributed", action=gated.kind)
        return None
    verdict = decide_call(gated, session_id, store=store, env=env)
    if verdict is None:
        return None
    return {"ok": False, "status": "refused_not_steward", "exit_code": 1,
            "error": verdict["reason"], "steward": verdict["steward"]}


# -- the delivery contract: deliverable(branch) -----------------------------
#
# ONE read-only preflight (ratified guardian spec, 2026-11-10; KB § PATTERNS/devops/
# release-steward.md § Delivery contract). `request` runs it at filing, the guardian
# runs it again before it enqueues, and `task_branch enqueue` is then a PURE PUSH.
# It is the reason the guardian never has to edit, rebase, merge or renumber a
# delivery branch: a branch that fails goes BACK to its branch steward as
# `needs_resync`, naming the item.
#
# Read-only by construction: every git call goes through `_ReadOnlyGit` (a
# subcommand allowlist: no checkout/merge/rebase/commit/add/push, `worktree`
# only as `list`), `status` is run with --no-optional-locks (a plain `git
# status` refreshes the index of the worktree it reads), and the trial merge
# runs with its cwd INSIDE the git dir (merge drivers drop `.merge_file_*`
# scratch files in the process cwd). The only state it touches: `fetch` updates
# the remote-tracking refs of `origin/<dev>`, and `merge-tree` writes loose
# objects to the object database - never a work tree, an index, HEAD or a branch.

DELIVERABLE_ITEMS = ("head_pushed_clean", "merge_buildable", "migrations_free", "derived_current", "scoped_green")
BRANCH_PREFIXES = ("feat/", "fix/", "docs/", "chore/", "refactor/", "test/", "perf/", "ci/", "build/", "style/")
_READONLY_GIT = frozenset({"rev-parse", "ls-remote", "merge-base", "merge-tree", "rev-list", "diff",
                           "ls-tree", "status", "worktree", "fetch", "cat-file", "show", "for-each-ref"})
GitFn = Callable[..., "tuple[int, str, str]"]

#: Derived artifacts a delivery must carry up to date AT its head. Each is regenerated in `--check`
#: mode against an EXPORT of the head tree (never the branch's worktree). `{python}`/`{tree}` are
#: filled in; a non-zero exit = stale. Mirrors what the pre-commit hook / integrate regenerate
#: (propagate is deliberately absent: the hook runs it only when the seed is staged).
DERIVED_ARTIFACTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kb-counts", ("{python}", "{tree}/mcp/noctusai/cli.py", "--update-kb-counts", "--check", "--worktree-path", "{tree}")),
    ("project-history", ("{python}", "{tree}/mcp/noctusai/cli.py", "--render-project-history", "--check", "--worktree-path", "{tree}")),
    ("promotions-index", ("{python}", "{tree}/mcp/noctusai/cli.py", "--gen-promotions-index", "--check", "--worktree-path", "{tree}")),
)


def _git_toplevel(cwd: str | Path | None) -> str | None:
    """The repository toplevel for `cwd` (None = the process cwd), or None outside a repository. Path arguments to
    git (`ls-tree <tree> <dir>/`, `archive`) are cwd-RELATIVE: from a subdirectory they silently match nothing or
    only that subdirectory, so every deliverable git call runs here (2026-11-10, the MCP fresh-subprocess cwd)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30,
                           check=False, cwd=str(cwd) if cwd else None)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def _subprocess_git(base_cwd: str | Path | None = None, timeout: int = 120) -> GitFn:
    base_cwd = _git_toplevel(base_cwd) or base_cwd

    def git(*args: str, cwd: str | Path | None = None) -> tuple[int, str, str]:
        try:
            r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout, check=False,
                               cwd=str(cwd or base_cwd) if (cwd or base_cwd) else None)
        except (OSError, subprocess.SubprocessError) as exc:
            return 127, "", f"git {args[:1]} failed to run: {exc}"
        return r.returncode, r.stdout or "", r.stderr or ""
    return git


class _ReadOnlyGit:
    """Wraps a git seam so `deliverable` is structurally unable to mutate a work tree."""

    def __init__(self, git: GitFn) -> None:
        self._git = git

    def __call__(self, *args: str, cwd: str | Path | None = None) -> tuple[int, str, str]:
        rest = [a for a in args if a != "--no-optional-locks" and not a.startswith("--attr-source=")]
        sub = rest[0] if rest else ""
        if sub not in _READONLY_GIT:
            raise ValueError(f"deliverable is read-only: git {sub!r} is not allowed ({sorted(_READONLY_GIT)})")
        if sub == "worktree" and rest[1:2] != ["list"]:
            raise ValueError("deliverable is read-only: only `git worktree list` is allowed")
        return self._git(*args, cwd=cwd)


def trial_merge_tree(git: GitFn, *args: str, attr_tree: str | None = None) -> tuple[int, str, str]:
    """`git merge-tree --write-tree <args>` run with cwd INSIDE the git dir, attributes taken from `attr_tree`.

    Why the cwd: when a merge driver runs it creates `.merge_file_*` scratch files in the PROCESS cwd; a work
    tree as cwd gets littered (2026-11-09: the primary, blamed on whichever session ran next). A cwd inside
    the git dir is a bare context. When the git dir cannot be resolved the probe is SKIPPED (rc 2).

    Why `attr_tree`: a bare context has no work tree and no index, so NOTHING reads `.gitattributes` - not
    `merge=union`, not the registered drivers (kb-counts, lgpd-warnings, gate-inventory) - and every append-only
    ledger or counts block becomes a text conflict. That forced "0 commits behind dev" (the livelock). Pass the
    tip of DEV and the attributes (and so the drivers) are read from dev's tree via `--attr-source`. Never pass the
    head: a branch must not be able to declare its own conflict away (`*.x merge=union`). The merge drivers then
    run with cwd = the git dir; `scripts/hooks/merge-kb-counts.sh` resolves the toolkit from the common dir."""
    rc, gd, _e = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    gitdir = gd.strip().splitlines()[0] if rc == 0 and gd.strip() else ""
    if not gitdir or not os.path.isabs(gitdir):
        return 2, "", "git dir unresolved; trial merge skipped"
    pre = (f"--attr-source={attr_tree}",) if attr_tree else ()
    return git(*pre, "merge-tree", "--write-tree", *args, cwd=gitdir)


def resolve_branch_name(slug: str, git: GitFn | None = None, explicit: str | None = None,
                        default_prefix: str = "feat/") -> dict[str, Any]:
    """Slug -> the real branch name. `explicit` wins. Otherwise the slug itself when it is already a
    branch name, else `<prefix><slug>` for the conventional prefixes (feat/ fix/ docs/ ...) that exist
    locally or on origin. Zero matches -> `<default_prefix><slug>` (a not-yet-created branch keeps the old
    behaviour); several -> `ambiguous` (the caller must pass branch=). Never raises."""
    if explicit:
        return {"branch": explicit, "source": "explicit", "candidates": [explicit]}
    git = git or _subprocess_git()
    found: list[str] = []
    with contextlib.suppress(OSError, subprocess.SubprocessError, ValueError):
        # ONE call: every local/remote ref ending in /<slug>, filtered to the conventional prefixes.
        rc, out, _e = git("for-each-ref", "--format=%(refname)", f"refs/heads/*/{slug}", f"refs/remotes/origin/*/{slug}")
        if rc == 0:
            for ref in out.split():
                name = ref.removeprefix("refs/heads/").removeprefix("refs/remotes/origin/")
                if name.endswith(f"/{slug}") and f"{name[:-len(slug)]}" in BRANCH_PREFIXES and name not in found:
                    found.append(name)
        if "/" in slug and slug not in found:  # the slug IS already a branch name (docs/x)
            for ref in (f"refs/heads/{slug}", f"refs/remotes/origin/{slug}"):
                if git("rev-parse", "--verify", "--quiet", ref)[0] == 0:
                    found.insert(0, slug)
                    break
    order = [default_prefix, *[p for p in BRANCH_PREFIXES if p != default_prefix]]
    found.sort(key=lambda n: (0 if n == slug else 1, next((i for i, p in enumerate(order) if n == f"{p}{slug}"), 99)))
    if len(found) == 1:
        return {"branch": found[0], "source": "resolved", "candidates": found}
    if not found:
        return {"branch": f"{default_prefix}{slug}", "source": "default", "candidates": []}
    # feat/<slug> existing next to a same-slug sibling is the common clash; never guess.
    return {"branch": None, "source": "ambiguous", "candidates": found,
            "error": f"slug {slug!r} matches several branches {found}; pass branch=<the one to deliver>"}


def _worktree_of(git: GitFn, branch: str) -> str | None:
    rc, out, _e = git("worktree", "list", "--porcelain")
    if rc != 0:
        return None
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
        elif line.strip() == f"branch refs/heads/{branch}":
            return path
    return None


def _item(n: int, name: str, ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {"n": n, "name": name, "ok": bool(ok), "detail": detail, **extra}


def _unmeasured(n: int, name: str, exc: BaseException) -> dict[str, Any]:
    return _item(n, name, False, f"UNMEASURED ({type(exc).__name__}: {str(exc)[:200]}) - not measured is never green")


def _export_tree(head: str, tree: str, cwd: str | Path | None, timeout: int) -> str | None:
    """`git archive <head>` into `tree` (no work tree, index or ref touched). Returns an error or None.

    The export must be EXACTLY the tree: `export-ignore` / `export-subst` attributes make `git archive` drop or
    rewrite files, and the checks would then judge a different tree. The extracted file list is compared with
    `git ls-tree -r <head>` (submodule entries aside); any difference is an error (UNMEASURED upstream).

    Every git call runs at the repository TOPLEVEL: from a subdirectory `git archive` and `git ls-tree` both see
    only that subdirectory, and agree with each other, so the export silently became `mcp/noctusai/` alone when the
    MCP fresh-subprocess fallback ran from there (2026-11-10, b5's false "regenerator missing at the head")."""
    top = _git_toplevel(cwd)
    if not top:
        return f"cannot resolve the repository toplevel to export {head[:9]} (cwd={cwd or os.getcwd()})"
    cwd = top
    arch = subprocess.Popen(["git", "archive", head], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    untar = subprocess.run(["tar", "-x", "-C", tree], stdin=arch.stdout, capture_output=True, timeout=timeout, check=False)
    if arch.stdout:
        arch.stdout.close()
    arch_err = (arch.stderr.read() if arch.stderr else b"").decode("utf-8", "replace")
    if arch.wait() != 0 or untar.returncode != 0:
        return f"could not export {head[:9]}: {(arch_err or untar.stderr.decode('utf-8', 'replace'))[:200]}"
    ls = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", head], capture_output=True, text=True,
                        timeout=timeout, check=False, cwd=cwd)
    if ls.returncode != 0:
        return f"cannot list {head[:9]} to verify the export: {ls.stderr.strip()[:120]}"
    # submodule entries (mode 160000) are directories in the export, not files
    modes = subprocess.run(["git", "ls-tree", "-r", "-z", head], capture_output=True, text=True, timeout=timeout,
                           check=False, cwd=cwd).stdout
    submodules = {e.split("\t", 1)[1] for e in modes.split("\0") if e.startswith("160000") and "\t" in e}
    expected = {n for n in ls.stdout.split("\0") if n and n not in submodules}
    got: set[str] = set()
    for root, dirs, files in os.walk(tree):
        for name in [*files, *[d for d in dirs if os.path.islink(os.path.join(root, d))]]:
            got.add(os.path.relpath(os.path.join(root, name), tree).replace(os.sep, "/"))
    got.discard("pax_global_header")
    if got != expected:
        missing, extra = sorted(expected - got), sorted(got - expected)
        return (f"the export of {head[:9]} differs from the tree (export-ignore / export-subst?): "
                f"missing {missing[:5]}{' ...' if len(missing) > 5 else ''}, extra {extra[:5]}")
    return None


def seed_pythonpath(tree: str | Path) -> list[str]:
    """The seed packages the toolkit imports (noctusai_lib, noctusai_seed ...), as paths INSIDE the export:
    derived from the `-e <relpath>` lines of the head's own `mcp/noctusai/requirements.txt`, never hand-listed.
    Without them the venv's editable installs resolve to the PRIMARY checkout and the checks judge ITS seed lib."""
    req = Path(tree) / "mcp" / "noctusai" / "requirements.txt"
    out: list[str] = []
    try:
        lines = req.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        m = re.match(r"^\s*(?:-e|--editable)\s+(\S+)", line)
        if m:
            path = (req.parent / m.group(1)).resolve()
            if path.is_dir() and str(path).startswith(str(Path(tree).resolve())):
                out.append(str(path))
    return out


def export_env(tree: str | Path, base_env: dict[str, str] | None, workflow_text: str = "") -> dict[str, str]:
    """The hermetic env (OS basics + the CI job's own env) PLUS `PYTHONPATH` = the head's seed packages."""
    env = hermetic_env(base_env, workflow_text)
    seeds = seed_pythonpath(tree)
    if seeds:
        env["PYTHONPATH"] = os.pathsep.join(seeds)
    return env


def seed_isolation_error(py: str, tree: str | Path, env: dict[str, str]) -> str | None:
    """Every seed package the HEAD ships must import from inside the export, else the checks would judge the primary's
    copy: each top-level package under every path the head's requirements name (`seed_pythonpath`), plus `noctusai_lib`
    and `noctusai_seed` whenever the head carries them (a head that ships one but does not put it on the path resolves
    to the venv's editable install = the primary checkout). Returns an UNMEASURED reason or None (None too when the head
    has no seed packages at all)."""
    root = Path(tree)
    names: list[str] = []
    for base in seed_pythonpath(root):
        names += sorted(d.name for d in Path(base).iterdir() if (d / "__init__.py").is_file())
    for pkg, rel in (("noctusai_lib", "seed/lib/backend"), ("noctusai_seed", "seed/framework/backend")):
        if (root / rel / pkg / "__init__.py").is_file():
            names.append(pkg)
    names = sorted(dict.fromkeys(names))
    if not names:
        return None
    probe = ("import importlib, sys\n"
             "for n in sys.argv[1:]:\n"
             "    m = importlib.import_module(n)\n"
             "    print(n + '\\t' + str(getattr(m, '__file__', '')))\n")
    r = subprocess.run([py, "-c", probe, *names], capture_output=True, text=True, timeout=120, check=False,
                       cwd=str(tree), env=env)
    if r.returncode != 0:
        return f"cannot import the head's seed packages {names} in the export: {r.stderr.strip()[-160:]}"
    base = os.path.realpath(str(tree))
    outside = [f"{n} -> {f}" for n, _, f in (ln.partition("\t") for ln in r.stdout.splitlines())
               if not f or not os.path.realpath(f).startswith(base)]
    if outside:
        return (f"seed package(s) resolve OUTSIDE the export ({'; '.join(outside)[:240]}): the checks would judge the "
                "primary's copy, not the head's")
    return None


CLI_REL = "mcp/noctusai/cli.py"


def _emit_gate_event(gate: str, outcome: str, target: str = "", reason: str = "") -> None:
    """One row in the SAME sink as every other gate event (gate_alignment.record_event). Never raises."""
    try:
        from tools.noctus.dev.gate_alignment import record_event
        record_event(gate, outcome, kind="deliverable", target=target[:200], reason=reason[:300], source="deliverable")
    except Exception:  # noqa: BLE001 - telemetry never changes a verdict
        pass


def export_cli_help_check(cwd: str | Path | None = None, *, python: str | None = None, timeout: int = 120,
                          base_env: dict[str, str] | None = None) -> Callable[[str], dict[str, Any]]:
    """`cli.py --help` of the HEAD, run in an export of the head (never the worktree) in the hermetic env with the head's
    seed packages. argparse %-formats every help string, so a literal `%A` (a merge-driver placeholder in a new --help text)
    crashes the whole CLI, and with it every `cli.py --<flag>` gate (merge-loss-gate was ejected on exactly that, 2026-11-10).
    A non-zero exit fails, naming the stderr tail."""
    py = python or sys.executable

    def check(head: str) -> dict[str, Any]:
        tree = tempfile.mkdtemp(prefix="noc-cli-help-")
        try:
            err = _export_tree(head, tree, cwd, timeout)
            if err:
                return {"ok": False, "measured": False, "detail": f"UNMEASURED: {err}"}
            cli = Path(tree) / CLI_REL
            if not cli.is_file():
                return {"ok": False, "measured": False, "detail": f"UNMEASURED: {CLI_REL} missing at the head"}
            wf = Path(tree) / CI_WORKFLOW_REL
            env = export_env(tree, base_env, wf.read_text(encoding="utf-8") if wf.is_file() else "")
            iso = seed_isolation_error(py, tree, env)
            if iso:
                return {"ok": False, "measured": False, "detail": f"UNMEASURED: {iso}"}
            r = subprocess.run([py, str(cli), "--help"], capture_output=True, text=True, timeout=timeout, check=False,
                               cwd=tree, env=env)
            if r.returncode != 0:
                tail = " ".join((r.stderr or r.stdout).strip().splitlines()[-2:])[:240]
                return {"ok": False, "measured": True, "detail": f"`cli.py --help` exits {r.returncode}: {tail}"}
            return {"ok": True, "measured": True, "detail": "`cli.py --help` exits 0"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "measured": False, "detail": f"UNMEASURED: {type(exc).__name__}: {exc}"[:240]}
        finally:
            shutil.rmtree(tree, ignore_errors=True)
    return check


def sandbox_env(env: dict[str, str], home: str | Path, ci_env: dict[str, str] | None = None) -> dict[str, str]:
    """`env` re-pointed into the throwaway `home`: HOME, no system/global git config (an EMPTY global file), and EVERY
    inherited `NOCTUS_*` key dropped unless the CI job's own env declares it (`ci_env` = `ci_job_env(workflow)`; derived,
    never a hand-kept list of state dirs). With HOME in the sandbox the toolkit's state defaults land there too.
    Raises OSError when the sandbox cannot be set up (-> UNMEASURED)."""
    h = Path(home)
    (h / ".noctus").mkdir(parents=True, exist_ok=True)
    gitconfig = h / "empty.gitconfig"
    gitconfig.write_text("", encoding="utf-8")
    out = dict(env)
    out["HOME"] = str(h)
    out["GIT_CONFIG_NOSYSTEM"] = "1"
    out["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    declared = ci_env or {}
    for key in [k for k in out if k.startswith("NOCTUS_") and k not in declared]:
        out.pop(key)
    for key in [k for k in out if k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_", "GIT_CONFIG_COUNT"))]:
        out.pop(key)
    return out


# Residual (2026-11-10): the sandbox is environmental (HOME + state-dir overrides + no git config), not a kernel
# sandbox - macOS has no unprivileged FS sandbox, so a delivery hard-coding an absolute path can still write it.
# That is covered by the per-delivery review + the checks running in a `git archive` export, not by this leg.


def _missing_regenerator_diagnostics(tree: str, regenerator: str) -> dict[str, Any]:
    """Where item 4 looked when a regenerator was not a file, so the verdict diagnoses itself.

    2026-11-10: a guardian enqueue on the MCP fresh-subprocess path reported every regenerator "missing at the
    head" for a head that ships cli.py; from a shell the same check was green. The suspects are the process's
    cwd / TMPDIR, not the head, so record them with the export's real contents (read-only)."""
    probe = Path(regenerator)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        top = sorted(os.listdir(tree))
    except OSError as exc:
        top = [f"<unreadable: {type(exc).__name__}>"]
    return {"export_dir": tree, "export_dir_existed": os.path.isdir(tree), "expected": regenerator,
            "nearest_existing": str(probe), "cwd": os.getcwd(),
            "tmpdir": os.environ.get("TMPDIR", "") or tempfile.gettempdir(), "export_top": top[:40]}


def export_derived_check(cwd: str | Path | None = None, *, artifacts: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
                         python: str | None = None, timeout: int = 300,
                         base_env: dict[str, str] | None = None) -> Callable[[str], dict[str, Any]]:
    """Real default for `deliverable(derived_check=)`: export the head tree (`git archive`, no work tree
    touched) into a temp dir and run each artifact's `--check` regenerator against the export. A missing
    regenerator or a timeout is UNMEASURED (fails), never skipped."""
    arts = artifacts if artifacts is not None else DERIVED_ARTIFACTS
    py = python or sys.executable

    def check(head: str) -> dict[str, Any]:
        tree = tempfile.mkdtemp(prefix="noc-deliverable-")
        sandbox = tempfile.mkdtemp(prefix="noc-sandbox-home-")
        results: list[dict[str, Any]] = []
        try:
            err = _export_tree(head, tree, cwd, timeout)
            if err:
                return {"ok": False, "measured": False, "results": [], "detail": f"UNMEASURED: {err}"}
            wf = Path(tree) / CI_WORKFLOW_REL
            try:
                wf_text = wf.read_text(encoding="utf-8") if wf.is_file() else ""
                env = sandbox_env(export_env(tree, base_env, wf_text), sandbox, ci_job_env(wf_text))
            except OSError as exc:
                return {"ok": False, "measured": False, "results": [], "detail": f"UNMEASURED: sandbox setup failed: {exc}"[:240]}
            err = seed_isolation_error(py, tree, env)
            if err:
                return {"ok": False, "measured": False, "results": [], "detail": f"UNMEASURED: {err}"}
            for name, template in arts:
                argv = [t.format(python=py, tree=tree) for t in template]
                regenerator = next((a for a in argv[1:] if a.startswith(tree) and a.endswith(".py")), None)
                if regenerator and not os.path.isfile(regenerator):
                    diag = _missing_regenerator_diagnostics(tree, regenerator)
                    results.append({"name": name, "ok": False, "measured": False, "diagnostics": diag,
                                    "detail": (f"regenerator missing at the head ({regenerator[len(tree) + 1:]}); "
                                               f"export={diag['export_dir']} existed={diag['export_dir_existed']} "
                                               f"nearest={diag['nearest_existing']} cwd={diag['cwd']} "
                                               f"tmpdir={diag['tmpdir']} top={','.join(diag['export_top'][:12])}")})
                    continue
                try:
                    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, cwd=tree, env=env)
                except (OSError, subprocess.SubprocessError) as exc:
                    results.append({"name": name, "ok": False, "measured": False, "detail": f"{type(exc).__name__}: {exc}"[:200]})
                    continue
                tail = " ".join((r.stdout or r.stderr or "").strip().splitlines()[-2:])[:200]
                results.append({"name": name, "ok": r.returncode == 0, "measured": True,
                                "detail": tail or ("up to date" if r.returncode == 0 else f"exit {r.returncode}")})
        finally:
            shutil.rmtree(tree, ignore_errors=True)
            shutil.rmtree(sandbox, ignore_errors=True)
        stale = [x["name"] for x in results if not x["ok"]]
        return {"ok": bool(results) and not stale, "measured": all(x["measured"] for x in results), "results": results,
                "detail": ("all derived artifacts current at the head" if results and not stale
                           else f"stale or unmeasured at the head: {', '.join(stale) or 'none ran'}")}
    return check


# -- item 5: scoped keepers/tests THE WAY CI JUDGES THEM ------------------------------------------
#
# 2026-11-10, merge-queue run 42753204233 (D1): a delivery that was green locally was ejected by CI.
# Two causes, both about WHAT item 5 ran, not whether it ran:
#   (a) keepers that only WARN in pre-commit but BLOCK in CI - the mcp-first-scripts manifest rows
#       (`check_new_script_lacks_mcp_analog`, asserted `== []` on the live tree by a CI-run test) and
#       `check_gate_triad`'s inventory row. CI blocks them because the sharded pytest job runs a
#       "real tree is clean" test for each, and because test.yml runs `cli.py --check-*` steps.
#   (b) a test that passed locally only because CLAUDE_CODE_SESSION_ID was set; CI runners have no
#       such variable.
# So the CI-blocking set is DERIVED from the head's own CI definition (never hand-listed), and the
# whole leg runs in a hermetic env built the way CI builds it.

CI_WORKFLOW_REL = ".github/workflows/test.yml"
CI_TOOLKIT_JOB = "mcp-toolkit-tests"
#: OS basics that survive the scrub. Everything else (CLAUDE_*, ANTHROPIC_*, OPENAI_*, SUPABASE_*, NOC*, ...)
#: is absent on a CI runner and is therefore absent here; the toolkit job's own `env:` is then layered on.
HERMETIC_BASE_ENV = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM", "SHELL",
                     "VIRTUAL_ENV", "SYSTEMROOT")
#: What a verdict RECORD asserts (set only by `export_ci_parity_check`): the run was env-scrubbed and covered the CI-blocking keepers.
VERDICT_MARKERS = ("env-scrubbed", "ci-keepers")


def _workflow_steps(text: str) -> list[str]:
    return [c for c in re.split(r"(?m)^\s*- (?=(?:name|uses|run|id|if|env):)", text)[1:]]


def ci_blocking_flags(workflow_text: str) -> list[str]:
    """Every `cli.py --check-*` keeper CI runs as a step of the workflow, in order: a step with
    `continue-on-error: true` does not block and is skipped; so is an invocation that needs a CI-resolved
    argument (`--doc-range ${{ ... }}`, `--actionlint-require`): it cannot be replayed locally."""
    out: list[str] = []
    for step in _workflow_steps(workflow_text):
        if re.search(r"continue-on-error:\s*true", step):
            continue
        for m in re.finditer(r"cli\.py\s+(--check-[a-z0-9-]+)([^\n]*)", step):
            if re.search(r"\s--[a-z]", m.group(2)) or "${{" in m.group(2):
                continue
            if m.group(1) not in out:
                out.append(m.group(1))
    return out


def ci_prime_flags(workflow_text: str) -> list[str]:
    """The `cli.py --<flag>` lines of CI's "Prime hermetic state" step (version stamp + structural caches):
    the generated state the suite's real-tree tests assert, which a fresh checkout lacks."""
    out: list[str] = []
    for step in _workflow_steps(workflow_text):
        if "Prime hermetic state" in step:
            out += [f for f in re.findall(r"python\s+cli\.py\s+(--[a-z0-9-]+)", step) if f not in out]
    return out


def ci_job_env(workflow_text: str, job: str = CI_TOOLKIT_JOB) -> dict[str, str]:
    """The `env:` mapping the toolkit job sets at JOB level (what every step of CI's run inherits)."""
    m = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow_text)
    env: dict[str, str] = {}
    if m:
        block = re.search(r"(?m)^    env:\n((?:      [A-Za-z0-9_]+:.*\n)+)", m.group(1))
        for line in (block.group(1).splitlines() if block else []):
            k, _, v = line.strip().partition(":")
            env[k.strip()] = v.strip().strip("\"'")
    return env


def hermetic_env(base: dict[str, str] | None = None, workflow_text: str = "") -> dict[str, str]:
    """The environment CI gives the toolkit suite: OS basics only + the job's own `env:` + CI=true."""
    base = os.environ if base is None else base
    env = {k: base[k] for k in HERMETIC_BASE_ENV if k in base}
    env.update(ci_job_env(workflow_text))
    env["CI"] = "true"
    return env


def ci_keeper_test_ids(tests_dir: str | Path) -> list[str]:
    """Pytest node ids (relative to the toolkit dir) of every test that asserts a `check_*` keeper returns
    `[]` on the live tree - the CI-blocking form of a keeper that is only `warning` in pre-commit.
    Derived by AST (`assert check_x(...) == []`, plain or `module.check_x`), never hand-listed."""
    import ast
    root = Path(tests_dir)
    ids: list[str] = []

    def callee(node: ast.AST) -> str:
        f = node.func if isinstance(node, ast.Call) else None
        return (f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "") if f else ""

    def asserts_clean_keeper(fn: ast.AST) -> bool:
        for n in ast.walk(fn):
            if isinstance(n, ast.Assert) and isinstance(n.test, ast.Compare) and len(n.test.ops) == 1 \
                    and isinstance(n.test.ops[0], ast.Eq):
                sides = (n.test.left, n.test.comparators[0])
                for call, empty in (sides, sides[::-1]):
                    if callee(call).startswith("check_") and isinstance(empty, ast.List) and not empty.elts:
                        return True
        return False

    for path in sorted(root.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        rel = f"{root.name}/{path.name}"
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test") \
                    and asserts_clean_keeper(node):
                ids.append(f"{rel}::{node.name}")
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                ids += [f"{rel}::{node.name}::{m.name}" for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test")
                        and asserts_clean_keeper(m)]
    return ids


# ─── item 5 runs the Python suites CI would run for this diff (owner decision 2026-11-11) ──────────────
# Three deliveries went 5/5 and were ejected by the merge queue on suites the DIFF selected in CI but item 5
# never ran: test_all_products_compliant[core] (a seeded product icon), the seed backend suite + test_vps_exec
# (a seed read_only_lines change), a product's FE vitest. The owner chose "run CI's suites" over a fast proxy.
# So the scope is CI's own classifier (`ci_scope`, which the workflow's `changes` job also calls), the suite
# lists come from the head's workflow matrices. NARROWED the same day (owner, after a 2h04m local measurement
# vs ~15-25 min in CI's parallel jobs): locally only the keeper tests + the seed roots / awake products the diff
# touches directly. Trade-off, stated: a toolkit-only red (the test_all_products_compliant[core] shape) and the
# shared-root fan-out are judged by the merge queue again, not here.
# NOC-REMEDIATE[scoped-green-fe-and-tooling]: FE vitest (product-frontend-tests / seed-frontend-tests) and the
# bespoke tooling-tests job are still CI-judged only - the export has no node_modules and tooling-tests renders
# a template in bash. Destination: the item-5 section of KB § PATTERNS/devops/release-steward.md (tooling steward).

@dataclass(frozen=True)
class CiSuite:
    label: str
    cwd: str            # relative to the export root
    argv: tuple[str, ...]  # after the interpreter: `python <argv...>`
    env: tuple[tuple[str, str], ...] = ()


def _matrix(workflow_text: str, job: str, key: str) -> list[str]:
    import yaml  # the toolkit venv carries PyYAML; only item 5's runner needs it
    doc = yaml.safe_load(workflow_text) or {}
    vals = (((doc.get("jobs") or {}).get(job) or {}).get("strategy") or {}).get("matrix", {}).get(key) or []
    return [str(v) for v in vals]


def _active_products(tree: Path) -> set[str] | None:
    """`deploy/fleet/active-scope.txt` at the head; None = missing = every product (CI fails toward coverage)."""
    f = tree / "deploy" / "fleet" / "active-scope.txt"
    if not f.is_file():
        return None
    return {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")}


def local_suites(tree: str | Path, scope: Any, workflow_text: str, changed: list[str]) -> list[CiSuite]:
    """The NARROW local share of CI's Python suites for item 5 (owner decision 2026-11-11, after the full CI
    split measured 2h04m locally vs ~15-25 min in CI's parallel jobs): only the suites of what the diff
    touches DIRECTLY - a seed backend root (seed-backend-tests matrix) the diff edits, and an awake product
    backend (product-backend-tests matrix, active-scope.txt) the diff edits. The toolkit split and the
    shared-root fan-out ("a seed change runs every product") stay CI-only: the merge queue runs them.
    NOC-REMEDIATE[scoped-green-fe-and-tooling]. Nothing when the scope is not heavy."""
    root = Path(tree)
    if not scope.run_heavy:
        return []
    out: list[CiSuite] = []
    for r in _matrix(workflow_text, "seed-backend-tests", "root"):
        prefix = r.rstrip("/") + "/"
        if (root / r).is_dir() and any(c.startswith(prefix) for c in changed):
            out.append(CiSuite(f"seed:{r}", r, ("-m", "pytest", "--tb=short", "-q")))
    awake = _active_products(root)
    direct = set(getattr(scope, "changed_products", ()) or ())
    for slug in _matrix(workflow_text, "product-backend-tests", "product"):
        d = f"products/{slug}/backend"
        if slug in direct and (awake is None or slug in awake) and (root / d).is_dir():
            out.append(CiSuite(f"product:{slug}", d, ("-m", "pytest", "--tb=short", "-q")))
    return out


#: Migration -> DB-guard edge (owner-approved speedup 1, 2026-11-11): a toolkit-only red stalled the queue 2h
#: (agents 079 added DB guards; mcp test_verify_db_guards::TestAgentsStudioProbes failed). A diff that adds or edits
#: `products/<p>/backend/migrations/*.sql` also runs the DB-guard suite + that product's PGlite replay tests.
_MIGRATION_RE = re.compile(r"^products/([^/]+)/backend/migrations/[^/]+\.sql$")
DB_GUARDS_TEST = "mcp/noctusai/tests/test_verify_db_guards.py"
#: replay-test filename prefix per product slug, where it is not the slug itself (`test_<prefix>_..._on_replay.py`)
_REPLAY_PREFIX = {"social-wiring": "sw", "erp-imobiliario": "erp"}
PGLITE_NODE_DIR = "mcp/noctusai/node"


def migration_guard_suite(tree: str | Path, changed: list[str]) -> CiSuite | None:
    """The DB-guard suite for a diff that touches product migrations: `test_verify_db_guards.py` + the replay tests
    of each touched product (`test_<prefix>_*on_replay*.py`) + the generic `test_migration_*replay*` ones. None when
    no migration is touched. Run from the repo root, like CI's toolkit job. Needs PGlite (`needs_pglite`)."""
    root = Path(tree)
    products = sorted({m.group(1) for c in changed if (m := _MIGRATION_RE.match(c))})
    if not products:
        return None
    tests_dir = root / "mcp" / "noctusai" / "tests"
    replay = sorted(p.name for p in tests_dir.glob("test_*replay*.py"))
    prefixes = {_REPLAY_PREFIX.get(p, p.replace("-", "_")) for p in products} | {"migration"}
    mine = [f"mcp/noctusai/tests/{n}" for n in replay if any(n.startswith(f"test_{x}_") for x in prefixes)]
    files = ([DB_GUARDS_TEST] if (root / DB_GUARDS_TEST).is_file() else []) + mine
    if not files:
        return None
    return CiSuite(f"db-guards:{','.join(products)}", ".", ("-m", "pytest", "-q", "-p", "no:cacheprovider", *files))


def link_pglite(tree: str | Path, source_repo: str | Path) -> str:
    """Give the export the SAME PGlite CI installs (`npm ci` in mcp/noctusai/node): symlink the source checkout's
    node_modules ONLY when its package-lock.json is byte-identical to the export's. Returns "" on success, else why.
    In the export CI=true, so a missing PGlite FAILS the replay tests - a false red; mismatch = UNMEASURED instead."""
    dst, src = Path(tree) / PGLITE_NODE_DIR, Path(source_repo) / PGLITE_NODE_DIR
    lock_d, lock_s = dst / "package-lock.json", src / "package-lock.json"
    mods = (src / "node_modules").resolve()
    if not (mods / "@electric-sql" / "pglite").is_dir():
        return f"PGlite is not installed in {src} (run `npm ci` there)"
    try:
        if lock_d.read_bytes() != lock_s.read_bytes():
            return f"{PGLITE_NODE_DIR}/package-lock.json differs between the head and {src} - its node_modules is not what CI installs"
    except OSError as exc:
        return f"cannot compare {PGLITE_NODE_DIR}/package-lock.json: {exc}"
    if not (dst / "node_modules").exists():
        (dst / "node_modules").symlink_to(mods, target_is_directory=True)
    return ""


VERDICT_STORE_NAME = "deliverable-verdicts.ndjson"
_VERDICT_REF_RE = re.compile(r"^ci-parity:([0-9a-f]{32})$")
_FULL_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def default_verdict_store(env: dict[str, str] | None = None) -> Path:
    return default_root(env) / VERDICT_STORE_NAME


def record_verdict(store: str | Path | None, *, head: str, tree: str, workflow_blob: str, interpreter: str,
                   flags: list[str], tests: list[str], ok: bool, clock: Callable[[], float] = time.time) -> str:
    """Append ONE verdict record to the append-only store and return its ref (`ci-parity:<id>`).

    Only `export_ci_parity_check` (a run that actually executed the CI-blocking keepers + real-tree keeper
    tests, env-scrubbed) writes these; the ref is the only thing a request may carry for item 5, because
    `validate_verdict_ref` resolves it to this record. A string a caller typed resolves to nothing."""
    path = Path(store) if store is not None else default_verdict_store()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"id": uuid.uuid4().hex, "ts": _iso(clock()), "head": head, "tree": tree, "workflow_blob": workflow_blob,
           "interpreter": interpreter, "flags": flags, "tests": tests, "ok": bool(ok),
           "env_scrubbed": True, "ci_keepers": True}
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return f"ci-parity:{rec['id']}"


def read_verdict(store: str | Path | None, vid: str) -> dict[str, Any] | None:
    path = Path(store) if store is not None else default_verdict_store()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        with contextlib.suppress(ValueError):
            rec = json.loads(line)
            if isinstance(rec, dict) and rec.get("id") == vid:
                return rec
    return None


def validate_verdict_ref(ref: str | None, head: str | None, store: str | Path | None = None,
                         tree: str | None = None) -> tuple[bool, str]:
    """A verdict pointer counts for item 5 only if it RESOLVES to a record in the verdict store written by a
    CI-parity run (`export_ci_parity_check`) for EXACTLY this head (full sha; the head tree too when known),
    with `ok` true and the env-scrubbed + CI-keeper markers set by that run. Free-form strings, short shas and
    substring markers are refused: they were forgeable (adversarial review, fix round 1)."""
    ref = (ref or "").strip()
    if not ref:
        return False, ("no verdict_ref and no scoped check ran: run `release_steward action=deliverable run_scoped=true` "
                       "(CI-blocking keepers + real-tree keeper tests, env-scrubbed) and file the `ci-parity:<id>` it returns")
    m = _VERDICT_REF_RE.match(ref)
    if not m:
        return False, (f"free-form verdict_ref {ref[:80]!r} refused: a verdict_ref is `ci-parity:<id>` minted by a "
                       "run_scoped=true run and resolved against the verdict record store")
    rec = read_verdict(store, m.group(1))
    if rec is None:
        return False, f"verdict record {ref} not found in the verdict store (never minted by a CI-parity run, or the store is unreadable)"
    if not head or not _FULL_SHA_RE.match(head) or rec.get("head") != head:
        return False, (f"verdict record {ref} judged head {str(rec.get('head'))[:9]}, not {str(head)[:9]}: "
                       "re-run run_scoped=true on this exact head (full-sha match required)")
    if tree and rec.get("tree") != tree:
        return False, f"verdict record {ref} judged tree {str(rec.get('tree'))[:9]}, not this head's tree {tree[:9]}"
    if not (rec.get("env_scrubbed") and rec.get("ci_keepers")):
        return False, f"verdict record {ref} does not record an env-scrubbed run with the CI-blocking keeper set"
    if not rec.get("ok"):
        return False, f"verdict record {ref} is RED ({len(rec.get('flags') or [])} keeper flag(s) + {len(rec.get('tests') or [])} test(s) ran, the result was not ok)"
    return True, (f"verdict record {ref}: head {head[:9]}, env-scrubbed, {len(rec.get('flags') or [])} CI-blocking keeper flag(s) "
                  f"+ {len(rec.get('tests') or [])} real-tree keeper test(s), green")


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_NOISE_RE = re.compile(r"[\u2550-\u257f]|NoctusAI Dev Toolkit|\|\s*INFO\s*\||env_bootstrap")


def meaningful_tail(text: str | None, max_lines: int = 20) -> str:
    """The last `max_lines` MEANINGFUL lines of a command's output: ANSI escapes stripped, the toolkit banner (box-drawing
    lines + its title), INFO log lines and blank lines dropped. A failure used to report only the banner (the first live use:
    'UNMEASURED: prime step failed (<banner>)'), which names no cause."""
    lines = [_ANSI_RE.sub("", ln).rstrip() for ln in (text or "").splitlines()]
    keep = [ln for ln in lines if ln.strip() and not _NOISE_RE.search(ln)]
    return "\n".join(keep[-max_lines:])


def _last_line(text: str | None) -> str:
    tail = meaningful_tail(text, 1)
    return tail[:200]


def _git_init_export(tree: str | Path, head: str, timeout: int = 300) -> str | None:
    """CI runs in a CHECKOUT: `--stamp-seed-version` needs git ('git not available - skipping stamp', exit 1 in a bare export) and
    the keeper-mirror caches live under `<git-common-dir>`. Give the export a throwaway repository: a fresh `git init` of the
    export with one commit, in the temp dir (never the requester's worktree, never the real repository, so its caches stay
    the export's own). Global/system git config is ignored so no inherited hooks path or identity leaks in. Returns an error or None."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "noc-ci-parity", "GIT_AUTHOR_EMAIL": "noc-ci-parity@localhost",
           "GIT_COMMITTER_NAME": "noc-ci-parity", "GIT_COMMITTER_EMAIL": "noc-ci-parity@localhost"}
    for argv in (["git", "init", "-q", "-b", "dev"], ["git", "add", "-A"],
                 ["git", "commit", "-q", "-m", f"ci-parity export of {head[:12]}"]):
        r = subprocess.run(argv, cwd=str(tree), capture_output=True, text=True, timeout=timeout, check=False, env=env)
        if r.returncode != 0:
            return f"could not make the export a git checkout (`{' '.join(argv[:2])}`): {meaningful_tail(r.stderr or r.stdout, 5)}"
    return None


def _hw_slot(job: str):
    return _sibling("hw_admission").heavy_slot(job)


class _CiParityTimeout(Exception):
    """A CI-parity stage exhausted its budget and its one x1.5 retry: no verdict (UNMEASURED), never a pass."""

    def __init__(self, gate: str, budgets: list[int]) -> None:
        super().__init__(f"stage `{gate}` timed out after {budgets[0]}s and again after the x1.5 retry ({budgets[-1]}s); "
                         "no verdict. Retry on a quieter machine, or set NOCTUS_GATE_BUDGETS_JSON='{\"%s\": <seconds>}'." % gate)


def export_ci_parity_check(cwd: str | Path | None = None, *, python: str | None = None, timeout: int | None = None,
                           base_env: dict[str, str] | None = None,
                           verdict_store: str | Path | None = None,
                           admit: Callable[[str], Any] | None = None) -> Callable[[str, str], dict[str, Any]]:
    """Real default for `deliverable(scoped_check=)`: judge the head the way CI does. Export it, prime the
    hermetic state CI primes, then - in a SCRUBBED environment - run (1) every `cli.py --check-*` keeper CI
    runs as a blocking step, (2) the real-tree keeper tests (`ci_keeper_test_ids`) and (3) the suites of the
    seed roots / awake products the diff touches DIRECTLY (`local_suites`, scoped by `ci_scope` - the
    classifier the workflow's `changes` job calls - over `origin/dev...head`). The toolkit split and the
    shared-root fan-out stay CI-only (2h04m measured locally, 2026-11-11). A ledger-only diff runs no suite. Everything is
    derived from the head's own workflow + tests. Runs inside ONE machine-wide heavy slot (`admit`, default
    hw_admission.heavy_slot); not admitted = UNMEASURED, never green. Minutes: the
    branch steward runs it once and files the `ci-parity:<id>` ref it returns; the run APPENDS a verdict record
    to the store (full head sha, head tree, test.yml blob, interpreter, flags, tests/suites, result) and the
    guardian only resolves the ref (`validate_verdict_ref`).

    Time limits are the SAME declared per-gate budgets the merged-tip gates use (`gate_budget`: `ci_parity:export`,
    `ci_parity:prime:<flag>`, `ci_parity:keeper:<flag>`, `ci_parity:pytest`, `ci_parity:suite:<label>`), each with ONE
    retry at x1.5 when it times out; a stage that times out twice is `UNMEASURED` naming the stage (never green).
    `timeout=` overrides every stage."""
    py = python or sys.executable
    slot = admit or _hw_slot
    cs = _sibling("ci_scope")

    def budget(gate: str) -> int:
        # Lazy, at RUN time: the steward PreToolUse hook loads this module by path with only the stdlib on sys.path and
        # builds this closure eagerly, so a `tools.` import here (or at module top) crashes every steward-class call closed.
        from tools.noctus.dev import gate_budget as _gate_budget
        return timeout if timeout is not None else _gate_budget.resolve_gate_budget(gate)

    def check(branch: str, head: str) -> dict[str, Any]:
        rc_d, diff_out, diff_err = _subprocess_git(cwd)("diff", "--name-only", f"origin/dev...{head}")
        if rc_d != 0:
            return {"ok": False, "detail": f"UNMEASURED: cannot list the paths the head changes vs origin/dev "
                                           f"(CI's suite selection depends on it): {_last_line(diff_err or '')}"}
        changed = diff_out.splitlines()
        scope = cs.classify(changed)
        with slot(f"deliverable:{branch}") as adm:
            if adm is not None and not getattr(adm, "admitted", True):
                return {"ok": False, "detail": f"UNMEASURED: no machine-wide heavy slot ({getattr(adm, 'verdict', '?')}) - "
                                               "item 5 runs CI's suites and is never judged green unrun"}
            return _parity_run(head, scope, changed)

    def _parity_run(head: str, scope: Any, changed: list[str]) -> dict[str, Any]:
        tree = tempfile.mkdtemp(prefix="noc-ci-parity-")
        sandbox = tempfile.mkdtemp(prefix="noc-sandbox-home-")
        try:
            err = _export_tree(head, tree, cwd, budget("ci_parity:export"))
            if err:
                return {"ok": False, "detail": f"UNMEASURED: {err}"}
            wf = Path(tree) / CI_WORKFLOW_REL
            if not wf.is_file():
                return {"ok": False, "detail": f"UNMEASURED: {CI_WORKFLOW_REL} missing at the head - the CI-blocking set cannot be derived"}
            text = wf.read_text(encoding="utf-8")
            try:
                env = sandbox_env(export_env(tree, base_env, text), sandbox, ci_job_env(text))
            except OSError as exc:
                return {"ok": False, "detail": f"UNMEASURED: sandbox setup failed: {exc}"[:240]}
            iso = seed_isolation_error(py, tree, env)
            if iso:
                return {"ok": False, "detail": f"UNMEASURED: {iso}"}
            gerr = _git_init_export(tree, head, budget("ci_parity:export"))
            if gerr:
                return {"ok": False, "detail": f"UNMEASURED: {gerr}"}
            flags, prime = ci_blocking_flags(text), ci_prime_flags(text)
            tool_dir = Path(tree) / "mcp" / "noctusai"
            failed: list[str] = []

            def run(gate: str, argv: list[str], where: Path,
                    extra: tuple[tuple[str, str], ...] = ()) -> subprocess.CompletedProcess:
                from tools.noctus.dev import gate_budget as _gate_budget
                first = budget(gate)
                budgets = [first, _gate_budget.retry_budget(first)]
                for b in budgets:
                    try:
                        return subprocess.run(argv, capture_output=True, text=True, timeout=b, check=False, cwd=str(where),
                                              env={**env, **dict(extra)})
                    except subprocess.TimeoutExpired:
                        continue
                raise _CiParityTimeout(gate, budgets)

            def pytest_failures(r: subprocess.CompletedProcess, label: str) -> list[str]:
                names = re.findall(r"^FAILED (\S+)", r.stdout or "", flags=re.M)
                return [f"{label} {n}" for n in names] or [f"{label} pytest exit {r.returncode}: {_last_line((r.stdout or '') + chr(10) + (r.stderr or ''))}"]

            for f in prime:
                r = run(f"ci_parity:prime:{f}", [py, "cli.py", f], tool_dir)
                if r.returncode != 0:
                    return {"ok": False, "detail": f"UNMEASURED: CI's prime step `cli.py {f}` failed in the hermetic export "
                                                   f"(exit {r.returncode}):\n{meaningful_tail((r.stdout or '') + chr(10) + (r.stderr or ''))}"}
            for f in flags:
                r = run(f"ci_parity:keeper:{f}", [py, "mcp/noctusai/cli.py", f], Path(tree))
                if r.returncode != 0:
                    failed.append(f"keeper {f}: {_last_line((r.stdout or '') + chr(10) + (r.stderr or ''))}")
            tests = ci_keeper_test_ids(tool_dir / "tests")
            if tests:
                r = run("ci_parity:pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], tool_dir)
                if r.returncode != 0:
                    failed += pytest_failures(r, "test")
            suites = local_suites(tree, scope, text, changed)
            guard = migration_guard_suite(tree, changed)
            if guard is not None:
                why = link_pglite(tree, cwd or Path.cwd())
                if why:
                    return {"ok": False, "detail": f"UNMEASURED: the diff touches migrations, so {guard.label} must run, "
                                                   f"but {why}"}
                suites = suites + [guard]
            for s in suites:
                r = run(f"ci_parity:suite:{s.label}", [py, *s.argv], Path(tree) / s.cwd, s.env)
                if r.returncode != 0:
                    failed += pytest_failures(r, s.label)
            n_tests = len(tests)
            tests = tests + [s.label for s in suites]
            ran = (f"{len(flags)} CI-blocking keeper flag(s) + {n_tests} real-tree keeper test(s) + {len(suites)} "
                   f"directly-touched suite(s){' incl. ' + guard.label if guard is not None else ''} "
                   f"({cs.describe(scope)}; toolkit split + shared fan-out left to CI), env-scrubbed")
            git = _subprocess_git(cwd)
            rc_t, head_tree, _e = git("rev-parse", "--verify", "--quiet", f"{head}^{{tree}}")
            rc_b, wf_blob, _e = git("rev-parse", "--verify", "--quiet", f"{head}:{CI_WORKFLOW_REL}")
            if rc_t != 0 or rc_b != 0:
                return {"ok": False, "detail": "UNMEASURED: cannot resolve the head tree / test.yml blob to record the verdict"}
            ref = record_verdict(verdict_store, head=head, tree=head_tree.strip(), workflow_blob=wf_blob.strip(),
                                 interpreter=f"{py} {sys.version.split()[0]}", flags=flags, tests=tests, ok=not failed)
            if failed:
                return {"ok": False, "detail": f"{ran}; RED: {', '.join(failed[:8])}", "failed": failed,
                        "ran": {"flags": flags, "tests": tests}, "verdict_ref": ref}
            return {"ok": True, "detail": f"{ran}; green", "ran": {"flags": flags, "tests": tests}, "verdict_ref": ref}
        except _CiParityTimeout as exc:
            return {"ok": False, "detail": f"UNMEASURED: {exc}"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "detail": f"UNMEASURED: {type(exc).__name__}: {exc}"[:240]}
        finally:
            shutil.rmtree(tree, ignore_errors=True)
            shutil.rmtree(sandbox, ignore_errors=True)
    return check


def deliverable(branch: str, *, git: GitFn | None = None, cwd: str | Path | None = None,
                remote: str = "origin", dev_branch: str = "dev", head_sha: str | None = None,
                verdict_ref: str | None = None, fetch: bool = True,
                derived_check: Callable[[str], dict[str, Any]] | None = None,
                scoped_check: Callable[[str, str], dict[str, Any]] | None = None,
                verdict_store: str | Path | None = None,
                cli_help_check: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """The delivery contract: five read-only checks, `verdict` deliverable | needs_resync.

    1 head_pushed_clean - local head == origin/<branch> AND the branch's worktree has no real dirt.
    2 merge_buildable   - origin/<dev> is an ancestor of the head OR `git merge-tree` against it is clean
                          (NOT strictly 0-behind: demanding that livelocks while dev moves).
    3 migrations_free   - no migration number the branch adds is claimed by a different file in the
                          composed tree (the head, or the merge-tree result when it is behind).
    4 derived_current   - kb-counts & the other regenerated artifacts are already current AT the head.
    5 scoped_green      - a `scoped_check(branch, head)` passes (`export_ci_parity_check`: the CI-blocking
                          keeper set + the real-tree keeper tests, env-scrubbed, both DERIVED from the head's
                          CI definition) OR the request's `verdict_ref` records exactly that run
                          (`validate_verdict_ref`: a `ci-parity:<id>` that resolves to a verdict record for this exact head); neither -> fails.

    Never raises (a probe that cannot run fails its item as UNMEASURED) and never writes a work tree."""
    git = _ReadOnlyGit(git or _subprocess_git(cwd))
    items: list[dict[str, Any]] = []
    out: dict[str, Any] = {"branch": branch, "head_sha": None, "dev_sha": None, "introduced_migrations": []}

    def local_ref(ref: str) -> str | None:
        rc, o, _e = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return o.strip() if rc == 0 and o.strip() else None

    # -- 1. head pushed + tree clean ------------------------------------------------------------
    head = None
    try:
        head = local_ref(f"refs/heads/{branch}")
        out["head_sha"] = head
        problems: list[str] = []
        notes: list[str] = []
        if not head:
            problems.append(f"branch {branch} does not exist locally")
        else:
            if head_sha:
                # FULL-sha equality (an abbreviation is expanded first): a 7-char prefix is forgeable by grinding
                rc_h, full_h, _e = git("rev-parse", "--verify", "--quiet", f"{head_sha}^{{commit}}")
                if rc_h != 0 or full_h.strip() != head:
                    problems.append(f"the request names head {head_sha[:9]} but {branch} is at {head[:9]} (re-request)")
            rc, o, e = git("ls-remote", "--heads", remote, f"refs/heads/{branch}")
            remote_sha = o.split()[0] if rc == 0 and o.strip() else None
            if rc != 0:
                problems.append(f"cannot read {remote}/{branch} ({(e or o).strip()[:120]})")
            elif not remote_sha:
                problems.append(f"{branch} is not pushed to {remote}")
            elif remote_sha != head:
                problems.append(f"unpushed: local {branch} is {head[:9]}, {remote}/{branch} is {remote_sha[:9]}")
            wt = _worktree_of(git, branch)
            if wt:
                rc, o, e = git("--no-optional-locks", "status", "--porcelain", cwd=wt)
                if rc != 0:
                    problems.append(f"cannot read the worktree status of {wt} ({e.strip()[:120]})")
                else:
                    benign, real = _sibling("_benign_stash").classify_porcelain(o or "")
                    untracked = sum(1 for ln in (o or "").splitlines() if ln.startswith("??"))
                    if real:
                        problems.append(f"dirty tree in {wt}: {', '.join(real[:6])}{' ...' if len(real) > 6 else ''}")
                    else:
                        notes.append(f"worktree clean ({len(benign)} benign artifact(s), {untracked} untracked, none part of the head)")
            else:
                notes.append("no worktree holds the branch (nothing to dirty)")
        items.append(_item(1, DELIVERABLE_ITEMS[0], not problems,
                           "; ".join(problems) if problems else f"{head[:9]} is pushed to {remote}; " + "; ".join(notes)))
    except Exception as exc:  # noqa: BLE001 - an unmeasurable item fails, loudly
        items.append(_unmeasured(1, DELIVERABLE_ITEMS[0], exc))

    # -- 2. merge-buildable -------------------------------------------------------------------
    composed_tree: str | None = None
    dev = None
    try:
        if fetch:
            git("fetch", "--quiet", "--no-write-fetch-head", remote, dev_branch)
        dev = local_ref(f"refs/remotes/{remote}/{dev_branch}")  # fully qualified: a branch/tag NAMED origin/dev must not win
        out["dev_sha"] = dev
        if not head or not dev:
            items.append(_item(2, DELIVERABLE_ITEMS[1], False,
                               f"cannot resolve {'the branch head' if not head else f'{remote}/{dev_branch}'}"))
        elif git("merge-base", "--is-ancestor", dev, head)[0] == 0:
            rc, o, _e = git("rev-parse", "--verify", "--quiet", f"{head}^{{tree}}")
            composed_tree = o.strip() if rc == 0 and o.strip() else None
            items.append(_item(2, DELIVERABLE_ITEMS[1], True, f"contains {remote}/{dev_branch} ({dev[:9]})"))
        else:
            rc, behind, _e = git("rev-list", "--count", f"{head}..{dev}")
            n_behind = behind.strip() if rc == 0 else "?"
            rc, o, e = trial_merge_tree(git, "--name-only", dev, head, attr_tree=dev)
            lines = (o or "").splitlines()
            if rc == 0 and lines:
                composed_tree = lines[0].strip()
                items.append(_item(2, DELIVERABLE_ITEMS[1], True,
                                   f"{n_behind} behind {remote}/{dev_branch}, `git merge-tree` is clean (the queue composes it; no rebase needed)"))
            elif rc == 1:
                files = []
                for ln in lines[1:]:
                    if not ln.strip():
                        break
                    files.append(ln.strip())
                items.append(_item(2, DELIVERABLE_ITEMS[1], False,
                                   f"{n_behind} behind {remote}/{dev_branch} and the merge CONFLICTS in "
                                   f"{', '.join(files[:8]) or '(see git merge-tree)'}: the branch steward must merge "
                                   f"{remote}/{dev_branch} into the branch, resolve, push, and re-request", conflicts=files))
            else:
                items.append(_item(2, DELIVERABLE_ITEMS[1], False,
                                   f"UNMEASURED: merge-tree exit {rc}: {(e or o).strip()[:160]}"))
    except Exception as exc:  # noqa: BLE001
        items.append(_unmeasured(2, DELIVERABLE_ITEMS[1], exc))

    # -- 3. migration numbers free -----------------------------------------------------------
    try:
        if not (head and dev and composed_tree):
            items.append(_item(3, DELIVERABLE_ITEMS[2], False, "not measurable: no composed tree (see merge_buildable)"))
        else:
            rc, mb, _e = git("merge-base", dev, head)
            base = mb.strip() if rc == 0 and mb.strip() else dev
            rc, o, e = git("diff", "--no-renames", "--name-only", "--diff-filter=A", base, head)
            if rc != 0:
                raise RuntimeError(f"git diff failed: {e.strip()[:120]}")
            introduced = sorted(p.strip() for p in o.splitlines()
                                if p.strip().endswith(".sql") and "/backend/migrations/" in p.strip())
            out["introduced_migrations"] = introduced
            if not introduced:
                items.append(_item(3, DELIVERABLE_ITEMS[2], True, "the branch adds no migration"))
            else:
                dirs = sorted({p.rsplit("/", 1)[0] for p in introduced})
                listing: dict[str, list[str]] = {d: [] for d in dirs}
                for d in dirs:
                    rc, o, e = git("ls-tree", "--name-only", composed_tree, f"{d}/")
                    if rc != 0:
                        raise RuntimeError(f"git ls-tree {d} failed: {e.strip()[:120]}")
                    listing[d] = [x.rsplit("/", 1)[-1] for x in o.splitlines() if x.strip()]
                from tools.noctus.dev.task_branch import migration_number_collisions
                clashes = migration_number_collisions(listing, introduced)
                if clashes:
                    items.append(_item(3, DELIVERABLE_ITEMS[2], False,
                                       "; ".join(f"{c['directory']}: number {c['number']} claimed by {', '.join(c['names'])}"
                                                 for c in clashes[:4])
                                       + f" - renumber the branch's own file(s) on top of {remote}/{dev_branch}, push, re-request",
                                       collisions=clashes))
                else:
                    items.append(_item(3, DELIVERABLE_ITEMS[2], True,
                                       f"{len(introduced)} added migration number(s) are free in the composed tree"))
    except Exception as exc:  # noqa: BLE001
        items.append(_unmeasured(3, DELIVERABLE_ITEMS[2], exc))

    # -- 4. derived files current at the head ------------------------------------------------
    try:
        if not head:
            items.append(_item(4, DELIVERABLE_ITEMS[3], False, "not measurable: the branch head does not resolve"))
        else:
            res = (derived_check or export_derived_check(cwd))(head)
            ok4 = bool(res.get("ok") and res.get("measured", True))
            detail4, arts4 = str(res.get("detail") or ""), list(res.get("results") or [])
            # 4b (folded in): when the delivery changes mcp/noctusai/cli.py, `cli.py --help` of the HEAD must exit 0
            rc_d, changed, _e = git("diff", "--name-only", f"{dev}...{head}") if dev else (1, "", "")
            if rc_d != 0 or CLI_REL in changed.splitlines():
                hres = (cli_help_check or export_cli_help_check(cwd))(head)
                hok = bool(hres.get("ok") and hres.get("measured", True))
                arts4.append({"name": "cli-help", "ok": hok, "measured": hres.get("measured", True), "skipped": False,
                              "detail": hres.get("detail", "")})
                _emit_gate_event("deliverable:cli-help", "pass" if hok else "deny", branch, hres.get("detail", ""))
                ok4 = ok4 and hok
                detail4 += f"; cli.py --help: {hres.get('detail', '')}" if not hok else "; cli.py --help: ok"
            else:
                arts4.append({"name": "cli-help", "ok": True, "measured": True, "skipped": True,
                              "detail": f"skipped: {CLI_REL} is not in the diff vs {remote}/{dev_branch}"})
                detail4 += f"; cli.py --help: skipped ({CLI_REL} not in the diff vs {remote}/{dev_branch})"
            items.append(_item(4, DELIVERABLE_ITEMS[3], ok4, detail4, artifacts=arts4))
    except Exception as exc:  # noqa: BLE001
        items.append(_unmeasured(4, DELIVERABLE_ITEMS[3], exc))

    # -- 5. scoped keepers/tests, judged the way CI judges them -------------------------------
    try:
        if scoped_check is not None and head:
            res = scoped_check(branch, head)
            items.append(_item(5, DELIVERABLE_ITEMS[4], bool(res.get("ok")), str(res.get("detail") or "scoped check ran"),
                               **({"verdict_ref": res["verdict_ref"]} if res.get("verdict_ref") else {})))
        else:
            tree5 = None
            if head:
                rc5, o5, _e5 = git("rev-parse", "--verify", "--quiet", f"{head}^{{tree}}")
                tree5 = o5.strip() if rc5 == 0 and o5.strip() else None
            ok5, why5 = validate_verdict_ref(verdict_ref, head, verdict_store, tree5)
            items.append(_item(5, DELIVERABLE_ITEMS[4], ok5, why5))
    except Exception as exc:  # noqa: BLE001
        items.append(_unmeasured(5, DELIVERABLE_ITEMS[4], exc))

    failing = [i["name"] for i in items if not i["ok"]]
    return {**out, "ok": not failing, "verdict": "deliverable" if not failing else "needs_resync",
            "items": items, "failing": failing, "kb": KB_POINTER}


def deliverable_refusal(result: dict[str, Any]) -> str:
    """One line naming every failing item and its detail (what a refusal message carries)."""
    bad = [i for i in result.get("items", []) if not i["ok"]]
    return "needs_resync - " + " | ".join(f"item {i['n']} {i['name']}: {i['detail']}" for i in bad)


# -- the MCP tool + CLI entry -----------------------------------------------

ACTIONS = ("status", "mine", "claim", "heartbeat", "handoff", "release", "request", "inbox", "ack",
           "role", "roles", "reconcile", "withdraw", "ask", "position", "decision", "deliverable")


def run_action(action: str, session_id: str | None, *, store: StewardStore | None = None,
               claude_pid: int | None = None, child_session: bool = False, **kw: Any) -> dict[str, Any]:
    store = store or StewardStore()
    if action != "status":
        store.role_touch(session_id, claude_pid)
    if action == "status":
        return store.status(session_id)
    if action == "mine":
        return store.mine(session_id, include_done=bool(kw.get("include_done")))
    if action == "claim":
        return store.claim(session_id or "", kw.get("name"), kw.get("reason"), claude_pid,
                           kw.get("ttl_s"), child_session)
    if action == "heartbeat":
        return store.heartbeat(session_id)
    if action == "handoff":
        return store.handoff(session_id, kw.get("to_session_id"), kw.get("to_name"), kw.get("notes"))
    if action == "release":
        return store.release(session_id, kw.get("notes"))
    if action == "request":
        return store.request(session_id, kw.get("slug") or "", name=kw.get("name"), branch=kw.get("branch"),
                             head_sha=kw.get("head_sha"), products=kw.get("products"),
                             migrations=bool(kw.get("migrations")), notes=kw.get("notes"),
                             inline_reason=kw.get("inline_reason"), inline_note=kw.get("inline_note"), branches=kw.get("branches"),
                             verdict_ref=kw.get("verdict_ref"), run_scoped=bool(kw.get("run_scoped")))
    if action == "deliverable":
        return store.check_deliverable(kw.get("slug"), kw.get("branch"), kw.get("head_sha"), kw.get("verdict_ref"),
                                    run_scoped=bool(kw.get("run_scoped")))
    if action == "inbox":
        return store.inbox(include_done=bool(kw.get("include_done")))
    if action == "roles":
        return store.roles()
    if action == "role":
        if (kw.get("op") or "set") == "clear":
            return store.role_clear(session_id, kw.get("role") or "")
        return store.role_set(session_id, kw.get("role") or "", name=kw.get("name"), claude_pid=claude_pid,
                              to_session_id=kw.get("to_session_id"))
    if action == "reconcile":
        return store.reconcile(session_id, confirm=bool(kw.get("confirm")))
    if action == "withdraw":
        return store.withdraw(session_id, kw.get("slug") or "", kw.get("notes"))
    if action == "ask":
        return store.ask(session_id, kw.get("slug") or "", kw.get("question") or "", kw.get("addressed_to"),
                         kw.get("deadline_min"))
    if action == "position":
        return store.position(session_id, kw.get("slug") or "", kw.get("notes") or "", kw.get("ref"))
    if action == "decision":
        return store.decide(session_id, kw.get("slug") or "", kw.get("notes") or "")
    if action == "ack":
        return store.ack(session_id, kw.get("slug") or "", kw.get("outcome") or "", kw.get("dev_sha"), kw.get("notes"))
    return _err(f"unknown action {action!r} ({'|'.join(ACTIONS)})")


def register(server) -> None:
    @server.tool(
        name="noctus.dev.release_steward",
        description=(
            "The release steward: ONE elected LEADER session per machine handles CI queueing AND deploy (enqueue, "
            "landed, bless, promote, deploy, prod migrations); everyone else files deliveries and KEEPS BUILDING. "
            "action=status (who is steward, am I, my requests) | claim name= reason= [ttl_s=] (refused while a live "
            "other holder exists; stale after ttl or dead process; then ANNOUNCE via ListAgents+SendMessage) | "
            "heartbeat | handoff to_session_id=|to_name= | release | request slug= [branch= head_sha= products=[] "
            "migrations= notes= verdict_ref= inline_reason= inline_note=] (OPEN to every session, NON-BLOCKING, returns at once; "
            "re-requesting a slug keeps the latest head_sha; an inline-agent delivery >=100 LoC or >=3 files wants "
            "inline_reason=orchestrator_owned|single_coherent_voice|shared_state|owner_directed + inline_note, else a "
            "warning names the specialists to dispatch) | mine (my requests' outcomes) | inbox [include_done] (pending, grouped by "
            "requester, with the batched drain list) | ack slug= outcome=enqueued|landed|ejected|deployed|withdrawn|needs_resync [dev_sha= "
            "notes= (required for withdrawn|needs_resync)] (steward) | deliverable slug=|branch= [head_sha= verdict_ref= run_scoped=true] (READ-ONLY, open to all: the DELIVERY CONTRACT - head pushed + tree clean, merge-buildable (contains origin/dev OR merge-tree clean), migration numbers free, derived files current at the head, scoped keepers/tests green the way CI judges them - the CI-blocking keeper set + real-tree keeper tests, env-scrubbed, derived from test.yml (run_scoped=true runs it, minutes) OR a verdict_ref carrying `env-scrubbed`,`ci-keepers` and the head sha; verdict deliverable|needs_resync, failing items named; `request` runs it at filing and the guardian re-runs it before enqueue, which is then a pure push) | withdraw slug= [notes=] (the requester or steward takes a request back) | ask slug= question= [addressed_to=<role> deadline_min=30] (steward: kind=needs_info, one bounded question; unanswered past the deadline = escalate_to_owner in inbox) | position slug= notes= [ref=<ni-id>] (answer / stance) | decision slug= notes= (steward's final call) | role role=<role> [name= op=set|clear to_session_id=] (durable ROLE->session map: dev-steward "
            "is derived from the lease, also branch-steward:<branch>, agents, products/sw, ...; any session sets its own, "
            "steward sets others') | roles (the map, stale/dead sessions flagged) | reconcile [confirm=True] (steward: ack "
            "every inbox request already in origin/dev - `git cherry` - as landed; inbox/status list them as already_landed, "
            "not drain) ; request also takes branches=[feat/a, feat/b] (ordered; the drain emits ONE task_branch train + ONE "
            "enqueue, never separate enqueues for a split delivery). Identity = the server's CLAUDE_CODE_SESSION_ID (one MCP server per session). "
            "Files: ~/.noctus/release-steward.json|.ndjson, ship-requests.ndjson. The PreToolUse hook "
            "claude-guard-release-steward.py denies steward-class calls from non-holders and names the holder; the "
            "tools re-check (status refused_not_steward). Override: NOC_STEWARD_OVERRIDE=<reason of 10+ chars>, "
            f"recorded. {KB_POINTER}"
        ),
    )
    def _release_steward(action: str = "status", name: str | None = None, reason: str | None = None,
                         ttl_s: int | None = None, to_session_id: str | None = None,
                         to_name: str | None = None, slug: str | None = None, branch: str | None = None,
                         head_sha: str | None = None, products: list[str] | None = None,
                         migrations: bool = False, notes: str | None = None, outcome: str | None = None,
                         dev_sha: str | None = None, include_done: bool = False,
                         inline_reason: str | None = None, inline_note: str | None = None, branches: list[str] | None = None,
                         role: str | None = None, op: str | None = None, confirm: bool = False,
                         question: str | None = None, addressed_to: str | None = None,
                         deadline_min: float | None = None, ref: str | None = None,
                         verdict_ref: str | None = None, run_scoped: bool = False) -> dict:
        return run_action(
            action, os.environ.get(SESSION_ENV), claude_pid=os.getppid(),
            child_session=os.environ.get("CLAUDE_CODE_CHILD_SESSION") == "1",
            name=name, reason=reason, ttl_s=ttl_s, to_session_id=to_session_id, to_name=to_name, slug=slug,
            branch=branch, head_sha=head_sha, products=products, migrations=migrations, notes=notes,
            outcome=outcome, dev_sha=dev_sha, include_done=include_done,
            inline_reason=inline_reason, inline_note=inline_note, branches=branches,
            role=role, op=op, confirm=confirm, question=question, addressed_to=addressed_to,
            deadline_min=deadline_min, ref=ref, verdict_ref=verdict_ref, run_scoped=run_scoped)


__all__ = ["deliverable", "export_derived_check", "export_ci_parity_check", "ci_blocking_flags", "ci_keeper_test_ids",
           "hermetic_env", "export_env", "export_cli_help_check", "meaningful_tail", "seed_pythonpath", "validate_verdict_ref", "record_verdict", "read_verdict", "default_verdict_store", "resolve_branch_name", "trial_merge_tree", "StewardStore", "Gated", "classify_tool", "classify_bash", "decide", "decide_call",
           "tool_refusal", "run_action", "register", "REQUEST_CMD", "OVERRIDE_ENV"]
