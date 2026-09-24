"""Ledger store — the append-only ``project-history/*.ndjson`` ledgers live on
an orphan ``ledgers`` branch on origin, written by git PLUMBING only.

Why (owner decision 2026-09-24, project gate-mechanisms): 963 of 2378 ``dev``
commits since 2026-08-01 (41%) were ledger chores — ``chore(salvage)`` /
``chore(branch-pointer)`` / ``chore(ledger)`` / ``chore(cost-log)``. They
cancelled CI runs (``test.yml`` is ``cancel-in-progress``), raced each other
("cannot lock ref"), blocked the primary checkout's sync and buried the real
history. A ledger row is tracking METADATA, not code: it needs durability and a
shared view, not a place on the integration branch.

Shape (CLAUDE.md §1 "Seed IO modules ship Fake+Real+factory")::

    Ledger (Protocol)      one named ledger: read_text / append / update
    GitLedger   (Real)     origin/ledgers via hash-object → mktree →
                           commit-tree → FF push, retried on the race
    FileLedger  (Fake)     the legacy local file at the writer's own path
    open_ledger (factory)  NOCTUS_LEDGER_STORE=git (default) | fake

The Real side NEVER checks anything out and never touches a working tree or an
index: it writes objects into the (shared) object store and moves exactly one
ref on the remote, fast-forward only. So it is safe to call from the primary
checkout, from any worktree, and concurrently from several processes.

Durability — a write-ahead spool. ``append`` first lands the rows in
``<git-common-dir>/noctusai/ledgers-pending/<name>`` (under an ``flock``), THEN
publishes. A publish that cannot complete (offline, auth, a race lost
``MAX_ATTEMPTS`` times) leaves the rows in the spool and says so
(``status='pending'``) — never a silent drop — and the next append/flush
carries them. ``read_text`` returns branch content + spooled rows, so a writer
always reads its own writes. Spooled rows already present on the branch are
dropped at publish time, so a crash between push and spool-truncate cannot
duplicate a row.

Dual-read (the S2 migration leg): until the dev copies are deleted (roadmap
``project-history/roadmaps/ledgers-off-dev-2026-09.md`` S4), readers merge
``origin/ledgers`` with the legacy dev copy via :func:`merge_ndjson_text` so
rows written by a peer session still on the old code are never invisible.

The tests use a temp bare repo only — no network. The mcp suite's conftest pins
``NOCTUS_LEDGER_STORE=fake`` so no test can ever push to the real origin.

KB § PATTERNS/architect/branch-tree-tracking.md · KB § PATTERNS/common/ledger-store.md
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

LEDGERS_BRANCH = "ledgers"
REMOTE = "origin"
MAX_ATTEMPTS = 5
GIT_TIMEOUT_S = 60
ENV_MODE = "NOCTUS_LEDGER_STORE"
MODE_GIT = "git"
MODE_FAKE = "fake"

# The ledgers that live on origin/ledgers. `ledger.ndjson` (the human project
# history) deliberately STAYS on dev — it is part of the reviewed record.
MOVED_LEDGERS: tuple[str, ...] = (
    "auto-improvement.ndjson",
    "vector-costs.ndjson",
    "vector-signals.ndjson",
    "vector-calibration.ndjson",
    "dispatch-budget.ndjson",
    "absorptions.ndjson",
    "worktree-salvage.ndjson",
    "branch-tree.ndjson",
    "ship-consent.ndjson",
)

Transform = Callable[[str], str]


class LedgerStoreError(RuntimeError):
    """The ledgers branch could not be read (missing ref, git failure)."""


# ── text helpers ──────────────────────────────────────────────────────────────
def _norm_lines(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        s = ln.rstrip("\n")
        if "\n" in s:
            raise ValueError("a ledger row must be a single line (got an embedded newline)")
        if s.strip():
            out.append(s)
    return out


def _join(base: str, lines: list[str]) -> str:
    if not lines:
        return base
    if base and not base.endswith("\n"):
        base += "\n"
    return base + "\n".join(lines) + "\n"


def merge_ndjson_text(*sources: str, key: Callable[[dict], Any] | None = None) -> str:
    """Union of several ndjson texts — the dual-read merge.

    Order-preserving, first occurrence wins for exact-duplicate lines. With a
    ``key`` (e.g. auto-improvement's ``(ts, target, description)`` identity), a
    LATER source's row REPLACES an earlier source's row with the same key in
    place — pass the authoritative source last. Malformed lines are kept
    verbatim (they are the keepers' business, never silently dropped here)."""
    order: list[str] = []          # slot ids in output order
    slots: dict[str, str] = {}     # slot id → line
    seen_lines: set[str] = set()
    for text in sources:
        for raw in (text or "").splitlines():
            line = raw.strip()
            if not line or line in seen_lines:
                continue
            seen_lines.add(line)
            slot = f"line:{line}"
            if key is not None:
                try:
                    obj = json.loads(line)
                    k = key(obj) if isinstance(obj, dict) else None
                except (json.JSONDecodeError, TypeError, KeyError):
                    k = None
                if k is not None:
                    slot = "key:" + json.dumps(k, ensure_ascii=False, sort_keys=True, default=str)
            if slot not in slots:
                order.append(slot)
            slots[slot] = line
    return "".join(slots[s] + "\n" for s in order)


# ── Protocol ──────────────────────────────────────────────────────────────────
@runtime_checkable
class Ledger(Protocol):
    """One named append-only ledger."""

    name: str

    def read_text(self, *, fetch: bool = False) -> str: ...

    def append(self, lines: Iterable[str], *, message: str, publish: bool = True) -> dict: ...

    def update(self, transform: Transform, *, message: str) -> dict: ...


# ── Fake: the legacy local file ───────────────────────────────────────────────
@dataclass
class FileLedger:
    """File-backed Fake: reads/appends the writer's own local path.

    Exactly the pre-2026-09-24 on-disk behaviour minus any git step, so writer
    tests that point a module's ``LEDGER_PATH`` at ``tmp_path`` keep exercising
    the same bytes. Never touches git or the network."""

    name: str
    path: Path

    def read_text(self, *, fetch: bool = False) -> str:
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""

    def append(self, lines: Iterable[str], *, message: str, publish: bool = True) -> dict:
        rows = _norm_lines(lines)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if rows:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(rows) + "\n")
        return {"ok": True, "status": "written", "store": MODE_FAKE, "rows": len(rows),
                "path": str(self.path)}

    def update(self, transform: Transform, *, message: str) -> dict:
        before = self.read_text()
        after = transform(before)
        if after == before:
            return {"ok": True, "status": "unchanged", "store": MODE_FAKE}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(after, encoding="utf-8")
        tmp.replace(self.path)
        return {"ok": True, "status": "written", "store": MODE_FAKE, "path": str(self.path)}


# ── Real: origin/ledgers via plumbing ─────────────────────────────────────────
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _default_runner(cmd: list[str], *, cwd: str, input: str | None = None,
                    timeout: int = GIT_TIMEOUT_S, env: dict | None = None
                    ) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, cwd=cwd, input=input, capture_output=True, text=True,
                          timeout=timeout, env=env)


@dataclass
class GitLedgerStore:
    """Multi-file store over ``<remote>/<branch>`` in the repo at ``repo_root``."""

    repo_root: Path
    remote: str = REMOTE
    branch: str = LEDGERS_BRANCH
    max_attempts: int = MAX_ATTEMPTS
    runner: Runner = field(default=_default_runner, repr=False)
    backoff_s: float = 0.4

    # ── git plumbing ──────────────────────────────────────────────────────────
    def _git(self, *args: str, input: str | None = None, timeout: int = GIT_TIMEOUT_S
             ) -> "subprocess.CompletedProcess[str]":
        try:
            return self.runner(["git", *args], cwd=str(self.repo_root), input=input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(exc.cmd, 124, "", f"timed out after {timeout}s")

    @property
    def tracking_ref(self) -> str:
        return f"refs/remotes/{self.remote}/{self.branch}"

    def _common_dir(self) -> Path:
        r = self._git("rev-parse", "--git-common-dir")
        if r.returncode != 0:
            raise LedgerStoreError(f"not a git repository: {self.repo_root} ({r.stderr.strip()})")
        p = Path(r.stdout.strip())
        return p if p.is_absolute() else (self.repo_root / p).resolve()

    def pending_dir(self) -> Path:
        d = self._common_dir() / "noctusai" / "ledgers-pending"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @contextlib.contextmanager
    def _locked(self) -> Iterator[Path]:
        d = self.pending_dir()
        with (d / ".lock").open("a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield d
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def fetch(self) -> tuple[bool, str]:
        r = self._git("fetch", "--quiet", self.remote,
                      f"+refs/heads/{self.branch}:{self.tracking_ref}")
        return r.returncode == 0, (r.stderr or "").strip()

    def tip(self) -> str | None:
        r = self._git("rev-parse", "--verify", "--quiet", f"{self.tracking_ref}^{{commit}}")
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

    def _blob(self, commit: str, name: str) -> str:
        r = self._git("cat-file", "-e", f"{commit}:{name}")
        if r.returncode != 0:
            return ""
        r = self._git("cat-file", "blob", f"{commit}:{name}")
        if r.returncode != 0:
            raise LedgerStoreError(f"cat-file {commit[:10]}:{name} failed: {r.stderr.strip()}")
        return r.stdout

    @staticmethod
    def _check_name(name: str) -> None:
        if not name or "/" in name or name.startswith(".") or not name.endswith(".ndjson"):
            raise ValueError(f"ledger name must be a bare '*.ndjson' filename; got {name!r}")

    # ── reads ─────────────────────────────────────────────────────────────────
    def pending_text(self, name: str) -> str:
        p = self.pending_dir() / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def read_text(self, name: str, *, fetch: bool = False) -> str:
        """Branch content + this clone's not-yet-published rows.

        ``fetch=False`` reads the local tracking ref (every ``git fetch origin``
        refreshes it — the default refspec covers ``ledgers``); one fetch is
        attempted when the ref is missing. Raises :class:`LedgerStoreError`
        when the branch cannot be resolved — callers surface it."""
        self._check_name(name)
        if fetch:
            ok, err = self.fetch()
            if not ok:
                logger.warning("ledger_store: fetch %s/%s failed (%s); reading the local ref",
                               self.remote, self.branch, err)
        tip = self.tip()
        if tip is None:
            self.fetch()
            tip = self.tip()
        if tip is None:
            raise LedgerStoreError(
                f"{self.tracking_ref} not found — the ledgers branch is not bootstrapped "
                "(noctus.dev.ledger_store action='bootstrap')")
        base = self._blob(tip, name)
        pend = [ln for ln in _norm_lines(self.pending_text(name).splitlines())]
        base_set = {ln.strip() for ln in base.splitlines()}
        return _join(base, [ln for ln in pend if ln.strip() not in base_set])

    # ── writes ────────────────────────────────────────────────────────────────
    def append(self, name: str, lines: Iterable[str], *, message: str, publish: bool = True) -> dict:
        self._check_name(name)
        rows = _norm_lines(lines)
        with self._locked() as d:
            if rows:
                with (d / name).open("a", encoding="utf-8") as fh:
                    fh.write("\n".join(rows) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
            if not publish:
                return {"ok": True, "status": "spooled", "store": MODE_GIT, "rows": len(rows),
                        "note": "rows are in the local spool; the next append/flush publishes them"}
            return self._publish_locked(d, message=message)

    def update(self, name: str, transform: Transform, *, message: str) -> dict:
        self._check_name(name)
        with self._locked() as d:
            return self._publish_locked(d, message=message, transforms={name: transform})

    def flush(self, *, message: str = "flush spooled rows") -> dict:
        with self._locked() as d:
            return self._publish_locked(d, message=message)

    def _publish_locked(self, d: Path, *, message: str,
                        transforms: dict[str, Transform] | None = None) -> dict:
        transforms = transforms or {}
        pending = {p.name: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.ndjson"))}
        pending = {k: v for k, v in pending.items() if v.strip()}
        if not pending and not transforms:
            return {"ok": True, "status": "nothing_pending", "store": MODE_GIT, "pushed": False}
        last_err = ""
        for attempt in range(1, self.max_attempts + 1):
            ok, err = self.fetch()
            if not ok:
                last_err = f"fetch failed: {err}"
                self._sleep(attempt)
                continue
            tip = self.tip()
            if tip is None:
                return self._pending_result(
                    f"{self.tracking_ref} missing after fetch — bootstrap the ledgers branch first",
                    pending)
            try:
                commit, changed = self._build_commit(tip, pending, transforms, message)
            except (LedgerStoreError, ValueError) as exc:
                return self._pending_result(str(exc), pending)
            if commit is None:
                self._clear(d, pending)
                return {"ok": True, "status": "unchanged", "store": MODE_GIT, "pushed": False,
                        "commit": tip}
            r = self._git("push", "--quiet", self.remote, f"{commit}:refs/heads/{self.branch}")
            if r.returncode == 0:
                self._git("update-ref", self.tracking_ref, commit, tip)
                self._clear(d, pending)
                return {"ok": True, "status": "pushed", "store": MODE_GIT, "pushed": True,
                        "commit": commit, "changed": changed, "attempts": attempt}
            last_err = (r.stderr or "").strip() or f"git push exited {r.returncode}"
            self._sleep(attempt)
        return self._pending_result(
            f"publish to {self.remote}/{self.branch} failed after {self.max_attempts} attempts: {last_err}",
            pending)

    def _build_commit(self, tip: str, pending: dict[str, str], transforms: dict[str, Transform],
                      message: str) -> tuple[str | None, list[str]]:
        r = self._git("ls-tree", "-z", tip)
        if r.returncode != 0:
            raise LedgerStoreError(f"ls-tree {tip[:10]} failed: {r.stderr.strip()}")
        entries: dict[str, str] = {}
        for rec in r.stdout.split("\0"):
            if not rec:
                continue
            meta, _, fname = rec.partition("\t")
            entries[fname] = meta
        changed: list[str] = []
        for name in sorted(set(pending) | set(transforms)):
            self._check_name(name)
            base = self._blob(tip, name)
            base_set = {ln.strip() for ln in base.splitlines()}
            rows = [ln for ln in _norm_lines(pending.get(name, "").splitlines())
                    if ln.strip() not in base_set]
            new = _join(base, rows)
            if name in transforms:
                new = transforms[name](new)
            if new == base:
                continue
            h = self._git("hash-object", "-w", "--stdin", input=new)
            if h.returncode != 0:
                raise LedgerStoreError(f"hash-object failed: {h.stderr.strip()}")
            entries[name] = f"100644 blob {h.stdout.strip()}"
            changed.append(name)
        if not changed:
            return None, []
        mk = self._git("mktree", "-z", input="".join(f"{m}\t{n}\0" for n, m in sorted(entries.items())))
        if mk.returncode != 0:
            raise LedgerStoreError(f"mktree failed: {mk.stderr.strip()}")
        subject = f"ledger({', '.join(changed)}): {message}".strip()
        ct = self._git("commit-tree", mk.stdout.strip(), "-p", tip, "-m", subject)
        if ct.returncode != 0:
            raise LedgerStoreError(f"commit-tree failed: {ct.stderr.strip()}")
        return ct.stdout.strip(), changed

    def _clear(self, d: Path, pending: dict[str, str]) -> None:
        # Under the lock, so no cooperating writer appended since we read.
        for name in pending:
            with contextlib.suppress(FileNotFoundError):
                (d / name).unlink()

    def _pending_result(self, error: str, pending: dict[str, str]) -> dict:
        logger.warning("ledger_store: %s — %d ledger(s) stay spooled for the next publish",
                       error, len(pending))
        return {"ok": False, "status": "pending", "store": MODE_GIT, "pushed": False,
                "error": error, "spooled": sorted(pending)}

    def _sleep(self, attempt: int) -> None:
        if attempt < self.max_attempts and self.backoff_s > 0:
            time.sleep(self.backoff_s * attempt + random.uniform(0, self.backoff_s))

    # ── bootstrap (S0) ────────────────────────────────────────────────────────
    def bootstrap(self, seed: dict[str, str], *, message: str) -> dict:
        """Create the orphan branch on the remote from ``{name: text}``.

        REFUSES when the branch already exists (never rewrites it)."""
        ok, _ = self.fetch()
        if self.tip() is not None:
            return {"ok": False, "status": "exists", "error": f"{self.remote}/{self.branch} already exists"}
        lines = []
        for name, text in sorted(seed.items()):
            if name != "README.md":
                self._check_name(name)
            h = self._git("hash-object", "-w", "--stdin", input=text)
            if h.returncode != 0:
                return {"ok": False, "error": f"hash-object failed: {h.stderr.strip()}"}
            lines.append(f"100644 blob {h.stdout.strip()}\t{name}\0")
        mk = self._git("mktree", "-z", input="".join(lines))
        if mk.returncode != 0:
            return {"ok": False, "error": f"mktree failed: {mk.stderr.strip()}"}
        ct = self._git("commit-tree", mk.stdout.strip(), "-m", message)
        if ct.returncode != 0:
            return {"ok": False, "error": f"commit-tree failed: {ct.stderr.strip()}"}
        commit = ct.stdout.strip()
        r = self._git("push", "--quiet", self.remote, f"{commit}:refs/heads/{self.branch}")
        if r.returncode != 0:
            return {"ok": False, "error": f"push failed: {r.stderr.strip()}"}
        self._git("update-ref", self.tracking_ref, commit)
        return {"ok": True, "status": "created", "commit": commit, "files": sorted(seed)}


@dataclass
class GitLedger:
    """Real: one named ledger on a :class:`GitLedgerStore`."""

    name: str
    store: GitLedgerStore

    def read_text(self, *, fetch: bool = False) -> str:
        return self.store.read_text(self.name, fetch=fetch)

    def append(self, lines: Iterable[str], *, message: str, publish: bool = True) -> dict:
        return self.store.append(self.name, lines, message=message, publish=publish)

    def update(self, transform: Transform, *, message: str) -> dict:
        return self.store.update(self.name, transform, message=message)


# ── factory ───────────────────────────────────────────────────────────────────
def store_mode() -> str:
    mode = (os.environ.get(ENV_MODE) or MODE_GIT).strip().lower()
    if mode not in (MODE_GIT, MODE_FAKE):
        raise ValueError(f"{ENV_MODE} must be '{MODE_GIT}' or '{MODE_FAKE}'; got {mode!r}")
    return mode


def default_store(repo_root: Path | None = None) -> GitLedgerStore:
    """The Real store on the PRIMARY checkout's repo (``settings.LEDGER_ROOT``,
    read at call time so a patched root is honoured)."""
    if repo_root is None:
        import settings  # lazy: tests patch settings.LEDGER_ROOT
        repo_root = settings.LEDGER_ROOT
    return GitLedgerStore(repo_root=Path(repo_root))


def open_ledger(name: str, local_path: Path, *, repo_root: Path | None = None) -> Ledger:
    """Factory. ``local_path`` is the writer's legacy file — the Fake's backing
    file, and ignored by the Real store (whose key is ``name``)."""
    if store_mode() == MODE_FAKE:
        return FileLedger(name=name, path=Path(local_path))
    return GitLedger(name=name, store=default_store(repo_root))


def read_dual(ledger: Ledger, dev_text: str, *, fetch: bool = False,
              key: Callable[[dict], Any] | None = None) -> tuple[str, str | None]:
    """S2 dual-read: ``dev_text`` (the legacy dev copy) ∪ the store's text.

    Returns ``(merged_text, error)``. A store read failure is RETURNED (and
    logged) — the caller surfaces it — while the dev copy still answers, so a
    missing ``origin/ledgers`` degrades loudly instead of hiding rows."""
    try:
        store_text = ledger.read_text(fetch=fetch)
    except LedgerStoreError as exc:
        logger.warning("ledger_store: dual-read of %s fell back to the dev copy only: %s",
                       ledger.name, exc)
        return merge_ndjson_text(dev_text, key=key), str(exc)
    return merge_ndjson_text(dev_text, store_text, key=key), None


def read_ledger_text(name: str, dev_path: Path, *, fetch: bool = False,
                     key: Callable[[dict], Any] | None = None) -> tuple[str, str | None]:
    """Dual-read one ledger: the dev copy at ``dev_path`` ∪ the store.

    The one-call form every simple reader uses (vector-costs, dispatch-budget,
    vector-calibration, absorptions, …) — ``(merged_text, store_error)``."""
    dev_path = Path(dev_path)
    dev = dev_path.read_text(encoding="utf-8") if dev_path.exists() else ""
    return read_dual(open_ledger(name, dev_path), dev, fetch=fetch, key=key)


def append_rows(name: str, dev_path: Path, rows: Iterable[dict | str], *, message: str,
                publish: bool = True) -> dict:
    """Append rows (dicts are JSON-encoded, compact, key order kept) to one
    ledger through the factory. Returns the store result; a result with
    ``status='pending'`` means the rows are durably spooled, not lost."""
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows]
    return open_ledger(name, Path(dev_path)).append(lines, message=message, publish=publish)


__all__ = [
    "read_ledger_text", "append_rows",
    "Ledger", "FileLedger", "GitLedger", "GitLedgerStore", "LedgerStoreError",
    "open_ledger", "default_store", "read_dual", "merge_ndjson_text", "store_mode",
    "MOVED_LEDGERS", "LEDGERS_BRANCH", "ENV_MODE", "MODE_GIT", "MODE_FAKE",
]
