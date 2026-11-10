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
import subprocess
import sys
import time
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
    "mcp__noctusai__noctus_dev_release_steward": "noctus.dev.release_steward",
}
_TASK_BRANCH_GATED = {"enqueue", "integrate", "landed"}
_RELEASE_GATED = {"bless", "promote", "backmerge"}
OUTCOMES = ("enqueued", "landed", "ejected", "deployed")
_ADVANCED = {"enqueued", "landed", "deployed"}


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
    in base (merged OR rebased/squashed). state: landed | pending | unresolvable (never silent).
    `dev_sha` = the ref's own sha when it is an ancestor of base, else base's tip."""
    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=30, check=False,
                              cwd=str(cwd) if cwd else None)

    def _rev(ref: str) -> str | None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            out = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
            sha = out.stdout.strip()
            if out.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", sha):
                return sha
        return None

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
            if any(ln.startswith("+") for ln in cherry.stdout.splitlines()):
                return {"state": "pending"}
            anc = _git("merge-base", "--is-ancestor", sha, base_tip)
            return {"state": "landed", "dev_sha": sha if anc.returncode == 0 else base_tip}
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
                 inline_gate: Callable[[str, str | None, str | None], dict[str, Any]] | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()
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
                    "notes": ev.get("notes"), "requester": ev.get("requester") or {},
                    "requested_at": ev["ts"], "status": "queued_for_steward",
                    "revision": (cur or {}).get("revision", 0) + 1, "dev_sha": None, "ack_note": None,
                    "requeued": bool(cur and cur["status"] != "queued_for_steward"),
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
                inline_note: str | None = None, branches: list[str] | None = None) -> dict[str, Any]:
        """NON-BLOCKING: file a delivery for the steward and return at once.

        Inline-cutoff gate (shadow): an over-cutoff delivery by an inline agent wants an
        ``inline_reason``; its absence is a WARNING naming who to dispatch, never a refusal."""
        slug = (slug or "").strip()
        if not slug or not re.fullmatch(r"[A-Za-z0-9._/-]+", slug):
            return _err("request needs slug=<slug> (the feat/<slug> name; letters, digits, . _ / -)")
        branches = [b.strip() for b in (branches or []) if b and b.strip()]
        if branches and any(not re.fullmatch(r"[A-Za-z0-9._/-]+", b) for b in branches):
            return _err("branches=[...] entries must be branch names (letters, digits, . _ / -)")
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
        with self._locked("ship-requests"):
            before = self.requests().get(slug)
            self._append_event({
                "ts": _iso(self.clock()), "event": "request", "slug": slug, "branch": branch,
                "head_sha": head_sha, "products": products or [], "migrations": bool(migrations),
                "notes": notes, "requester": {"session_id": session_id, "name": name or _short(session_id)},
                "branches": branches,
            })
            after = self.requests()[slug]
        holder = self.public_holder()
        out: dict[str, Any] = {
            "ok": True, "status": "queued_for_steward", "request": after,
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
            rows = [r for r in rows if r["status"] != "deployed"]
        return {"ok": True, "status": "mine", "requests": sorted(rows, key=lambda r: r["requested_at"])}

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
        if all(st == "landed" for st in states):
            return {"state": "landed", "dev_sha": results[-1].get("dev_sha")}
        return {"state": "pending"}

    def _partition(self, pending: list[dict[str, Any]]) -> tuple[list, list, list]:
        todo, landed, unres = [], [], []
        for r in pending:
            c = self._classify(r)
            if c["state"] == "landed":
                landed.append({**r, "landed_detected": c.get("dev_sha") or "origin/dev"})
            else:
                todo.append(r)
                if c["state"] == "unresolvable":
                    unres.append({**r, "unresolvable_reason": c.get("reason")})
        return todo, landed, unres

    def inbox(self, include_done: bool = False) -> dict[str, Any]:
        rows = list(self.requests().values())
        queued = sorted((r for r in rows if r["status"] == "queued_for_steward"), key=lambda r: r["requested_at"])
        pending, already_landed, unresolvable = self._partition(queued)
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
        out: dict[str, Any] = {
            "ok": True, "status": "inbox", "pending": len(pending), "by_requester": grouped,
            "requests": shown, "already_landed": already_landed, "unresolvable": unresolvable,
            "drain": drain,
            "next": ("drain ALL pending in one pass (enqueue each so riders batch in the merge queue; a multi-branch "
                     "delivery is ONE train then ONE enqueue), ack each "
                     "as enqueued, ack landed/ejected/deployed as they resolve, and SendMessage each requester "
                     "LANDED <dev sha> / EJECTED <reason> / DEPLOYED") if pending else "inbox empty",
        }
        if already_landed:
            out["next"] += (f" | {len(already_landed)} request(s) are ALREADY in origin/dev (git cherry): ack them "
                            "landed in one call with release_steward action=reconcile confirm=True")
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
        queued = [r for r in self.requests().values() if r["status"] == "queued_for_steward"]
        _todo, landed, _unres = self._partition(sorted(queued, key=lambda r: r["requested_at"]))
        slugs = [r["slug"] for r in landed]
        if not confirm:
            return {"ok": True, "status": "planned", "would_ack": slugs,
                    "next": "re-run with confirm=True to ack them landed" if slugs else "nothing already landed"}
        for r in landed:
            self.ack(session_id, r["slug"], "landed", dev_sha=r["landed_detected"], note="reconciled: already in origin/dev")
        if slugs:
            self.audit("reconcile", session_id=session_id, slugs=slugs)
        return {"ok": True, "status": "reconciled", "acked": slugs,
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

    def role_touch(self, session_id: str | None) -> None:
        """Best-effort liveness refresh of the roles this session holds (every action calls it)."""
        if not session_id:
            return
        with contextlib.suppress(Exception), self._locked("release-steward-roles"):
            roles = self._read_roles()
            hit = False
            for row in roles.values():
                if row.get("session_id") == session_id:
                    row["heartbeat_ts"], hit = self.clock(), True
            if hit:
                self._write_roles(roles)

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
                 "ejected": f"EJECTED {note or ''}".strip(), "deployed": "DEPLOYED"}
        return {"ok": True, "status": f"acked_{outcome}", "request": after,
                "next": f"SendMessage {after['requester'].get('name')}: {words[outcome]} (slug {slug})"}

    def status(self, session_id: str | None) -> dict[str, Any]:
        lease, state = self.holder()
        reqs = list(self.requests().values())
        queued = [r for r in reqs if r["status"] == "queued_for_steward"]
        _todo, landed, unres = self._partition(queued)
        roles = self.roles()
        return {
            "ok": True, "status": "status", "state": state, "steward": self.public_holder(),
            "i_am_steward": bool(lease and state == "live" and session_id and lease.get("session_id") == session_id),
            "session_id": session_id, "ttl_default_s": self.default_ttl_s,
            "roles": roles["roles"], "stale_roles": roles["stale_roles"],
            "outbox": {"pending": len(queued) - len(landed), "already_landed": len(landed),
                       "unresolvable": len(unres),
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
        return Gated(f"task_branch {action}", args.get("slug")) if action in _TASK_BRANCH_GATED and confirm else None
    if key == "noctus.dev.release":
        stage = args.get("stage") or "status"
        return Gated(f"release {stage}") if stage in _RELEASE_GATED and confirm else None
    if key == "noctus.dev.record_applied_migrations":
        return Gated("record_applied_migrations")  # always a write (it integrates to dev)
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
}
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
    for idx, w in enumerate(words):
        if not w.startswith("--"):
            continue
        flag, eq, val = w.partition("=")
        flags.add(flag)
        if flag in _CLI_GATES:
            nxt = words[idx + 1] if idx + 1 < len(words) else None
            vals[flag] = val if eq else (nxt if nxt and not nxt.startswith("--") else None)
    for flag, (allowed, confirm_flag, label) in _CLI_GATES.items():
        if flag in vals and confirm_flag in flags and (allowed is None or vals[flag] in allowed):
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
                  f"Reads and dry-runs stay open. {escape} {KB_POINTER}")
    else:
        why = "the previous steward's lease is stale" if state == "stale" else "no release steward is elected"
        reason = (f"{gated.kind} is steward-only and {why}. Run ListAgents and `release_steward action=status`; if you "
                  "are a LEADER session (interactive, top-level, not a dispatched subagent) with shipping work and no "
                  "other leader holds the lane, run `release_steward action=claim` and announce it to every peer with "
                  f"SendMessage. Otherwise {ask}. {escape} {KB_POINTER}")
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


# -- the MCP tool + CLI entry -----------------------------------------------

ACTIONS = ("status", "mine", "claim", "heartbeat", "handoff", "release", "request", "inbox", "ack",
           "role", "roles", "reconcile")


def run_action(action: str, session_id: str | None, *, store: StewardStore | None = None,
               claude_pid: int | None = None, child_session: bool = False, **kw: Any) -> dict[str, Any]:
    store = store or StewardStore()
    if action != "status":
        store.role_touch(session_id)
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
                             inline_reason=kw.get("inline_reason"), inline_note=kw.get("inline_note"), branches=kw.get("branches"))
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
            "migrations= notes= inline_reason= inline_note=] (OPEN to every session, NON-BLOCKING, returns at once; "
            "re-requesting a slug keeps the latest head_sha; an inline-agent delivery >=100 LoC or >=3 files wants "
            "inline_reason=orchestrator_owned|single_coherent_voice|shared_state|owner_directed + inline_note, else a "
            "warning names the specialists to dispatch) | mine (my requests' outcomes) | inbox [include_done] (pending, grouped by "
            "requester, with the batched drain list) | ack slug= outcome=enqueued|landed|ejected|deployed [dev_sha= "
            "notes=] (steward) | role role=<role> [name= op=set|clear to_session_id=] (durable ROLE->session map: dev-steward "
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
                         role: str | None = None, op: str | None = None, confirm: bool = False) -> dict:
        return run_action(
            action, os.environ.get(SESSION_ENV), claude_pid=os.getppid(),
            child_session=os.environ.get("CLAUDE_CODE_CHILD_SESSION") == "1",
            name=name, reason=reason, ttl_s=ttl_s, to_session_id=to_session_id, to_name=to_name, slug=slug,
            branch=branch, head_sha=head_sha, products=products, migrations=migrations, notes=notes,
            outcome=outcome, dev_sha=dev_sha, include_done=include_done,
            inline_reason=inline_reason, inline_note=inline_note, branches=branches,
            role=role, op=op, confirm=confirm)


__all__ = ["StewardStore", "Gated", "classify_tool", "classify_bash", "decide", "decide_call",
           "tool_refusal", "run_action", "register", "REQUEST_CMD", "OVERRIDE_ENV"]
