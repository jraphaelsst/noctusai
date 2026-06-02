"""cache_backend — pluggable storage layer for the 5 keeper-mirror caches.

Why this module exists
    The keeper-mirror caches (`keeper-patterns`, `agent-context`,
    `auto-improvement`, `kb-embeddings`, `code-embeddings`) all use
    local SQLite under `.claude/cache/`. The choice is correct for
    our current scale — single-architect, gitignored per-user,
    regenerable from source in minutes.

    The migration path to remote/shared cache (Supabase pgvector or
    self-hosted Postgres) is on the roadmap — see
    `project-history/roadmaps/cache-backend-portability-2026-05.md`
    for the trigger conditions and slice list. To make the eventual
    migration a localized swap rather than a 5-module rewrite, the
    connection + path-resolution layer is abstracted behind this
    Protocol now, while we have the option-value-cheap window.

Status — Phase 1
    The abstraction ships; the default `SqliteCacheBackend` matches
    today's behavior 1:1. Existing cache modules keep their direct
    sqlite3 calls (no big-bang refactor). NEW code that wants
    portability can consume `get_backend()`.

What this module does NOT do
    - It does NOT translate SQL dialects. A future PostgresBackend
      will need DB-API-2.0 parameter-style adaptation per-cache.
    - It does NOT migrate data between backends. Each cache is
      regenerable from source — migration = swap, then refresh.
    - It does NOT centralize per-cache schemas. Each cache continues
      to own its DDL — the backend just opens the connection.
    - It does NOT change consumer behavior. Touching this module
      should be ZERO-COST today; its job is to exist when needed.

The contract (see CacheBackend Protocol below)
    `backend.connect(cache_name)` is a context manager yielding a
    DB-API-2.0-compatible connection. The connection MUST support
    `.execute(sql, params)`, `.commit()`, and `.close()`.

    `backend.location(cache_name)` returns a human-readable string
    (file path for sqlite, URL for remote backends) — useful for
    telemetry + error messages.

    `backend.kind()` returns the implementation identifier —
    `"sqlite"` / `"postgres"` / `"supabase"` — for the freshness
    keepers to surface in their issue messages.

KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from settings import REPO_ROOT
from tools.noctus.dev.cache_backend_postgres import PostgresCacheBackend  # noqa: E402

_log = logging.getLogger("noctus.dev.cache_backend")


# ── Cache-locking discipline (single source of truth) ────────────────────────
# Default busy-wait before a contending writer raises "database is locked".
CACHE_BUSY_TIMEOUT_MS = 5000


def apply_locking_pragmas(
    conn: sqlite3.Connection, *, timeout_ms: int = CACHE_BUSY_TIMEOUT_MS
) -> None:
    """Apply the cache-locking discipline to a freshly-opened SQLite connection.

    Two pragmas, together:
      - ``journal_mode=WAL`` — readers never block the single writer.
      - ``busy_timeout`` — a CONTENDING writer waits up to ``timeout_ms`` for the
        lock instead of immediately raising
        ``sqlite3.OperationalError: database is locked``. WAL does NOT serialize
        writer-vs-writer; this closes that gap. The Tier-1 caches are shared
        across worktrees *and* the running MCP server, so concurrent writers are
        real — observed as a pre-push embedding-refresh fan-out colliding with a
        live MCP reader (2026-05-30).

    Idempotent; the WAL leg's tmpfs/readonly failure is non-fatal.
    See ``KB § PATTERNS/common/cache-locking-discipline.md``.
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # tmpfs / readonly fallback — non-fatal
    conn.execute(f"PRAGMA busy_timeout={int(timeout_ms)}")


# ── Cache catalog (single source of truth for cache names + files) ───────────
_CACHE_FILES: dict[str, str] = {
    "keeper-patterns":  "keeper-patterns.sqlite",
    "agent-context":    "agent-context.sqlite",
    "auto-improvement": "auto-improvement.sqlite",
    "kb-embeddings":    "kb-embeddings.sqlite",
    "code-embeddings":  "code-embeddings.sqlite",
    "memory-embeddings": "memory-embeddings.sqlite",
    "corpus-embeddings": "corpus-embeddings.sqlite",
    "noc-graph":        "noc-graph.sqlite",  # 8th — structured graph mirror
    "absorptions":      "absorptions.sqlite",  # 9th — absorption tracking mirror
}

# ── Tier-1 path resolution (worktree-shared persistent cache) ────────────────
# Caches live at `<git-common-dir>/noctusai/cache/<file>.sqlite` — one
# physical location per repo, automatically shared by every worktree (because
# `git rev-parse --git-common-dir` resolves to the same path from every
# worktree). Replaces the older `<worktree>/.claude/cache/` location, which
# created an empty cache per fresh worktree and forced ~30 min full re-embed
# on first commit. Legacy data is migrated once on first call (idempotent,
# sentinel-gated, multi-worktree-aware).
#
# KB § PATTERNS/common/cache-portable-architecture.md.

_LEGACY_CACHE_DIR_REL = ".claude/cache"
_NEW_CACHE_SUBDIR = "noctusai/cache"          # under git common dir
_LEGACY_MIGRATION_SENTINEL = ".migrated-from-claude-cache"
_AUTO_PULL_SENTINEL = ".tier2-auto-pulled"
_AUTO_PULL_OPT_OUT_ENV = "NOCTUS_DISABLE_AUTO_CACHE_PULL"
_MIGRATED_ROOTS: set[Path] = set()
_AUTO_PULLED_ROOTS: set[Path] = set()


def _git_common_dir(repo_root: Path) -> Path:
    """Return the directory git uses for shared state across worktrees.

    For the primary tree: `<repo>/.git`. For a linked worktree: still
    `<primary>/.git` (worktrees have a stub `.git` file pointing back).
    `git rev-parse --git-common-dir` is the canonical resolver.

    Falls back to `<repo_root>/.git` if git is unavailable (tests / etc).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        path_str = out.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return repo_root / ".git"
    common = Path(path_str)
    if not common.is_absolute():
        common = (repo_root / common).resolve()
    return common


def cache_dir(repo_root: Path | None = None) -> Path:
    """Return the persistent shared cache directory for this repo.

    Lives at `<git-common-dir>/noctusai/cache/`. ALL worktrees of this repo
    resolve to the same path. Created lazily.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    d = _git_common_dir(root) / _NEW_CACHE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def known_caches() -> list[str]:
    """Return the registered cache names (stable order)."""
    return list(_CACHE_FILES.keys())


def _migrate_legacy_cache(repo_root: Path) -> None:
    """One-time migration: copy legacy `.claude/cache/*.sqlite` from any worktree
    → `<git-common-dir>/noctusai/cache/`. Sentinel-gated (file at the new
    location); also memoized per-process for hot-path zero-cost.

    Uses `copy2` (not `move`) so OLD code on un-pulled worktrees keeps working
    against `.claude/cache/`. A future cleanup commit removes the legacy dirs
    once everyone is on the new code.
    """
    if repo_root in _MIGRATED_ROOTS:
        return
    new_root = cache_dir(repo_root)
    sentinel = new_root / _LEGACY_MIGRATION_SENTINEL
    if sentinel.exists():
        _MIGRATED_ROOTS.add(repo_root)
        return

    # Find every worktree's `.claude/cache/` to pick the newest file per cache.
    worktrees: list[Path] = []
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        for line in out.stdout.splitlines():
            if line.startswith("worktree "):
                worktrees.append(Path(line[len("worktree "):]))
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        worktrees = [repo_root]

    copied_any = False
    for cache_file in _CACHE_FILES.values():
        new_path = new_root / cache_file
        if new_path.exists():
            continue
        best_src: Path | None = None
        best_mtime = -1.0
        for wt in worktrees:
            legacy = wt / _LEGACY_CACHE_DIR_REL / cache_file
            if legacy.is_file():
                m = legacy.stat().st_mtime
                if m > best_mtime:
                    best_mtime = m
                    best_src = legacy
        if best_src is None:
            continue
        # Copy the SQLite file + its WAL / SHM sidecars (if present).
        for suffix in ("", "-wal", "-shm"):
            src = best_src.with_name(best_src.name + suffix)
            dst = new_root / (cache_file + suffix)
            if src.is_file() and not dst.exists():
                try:
                    shutil.copy2(str(src), str(dst))
                    copied_any = True
                except (OSError, FileNotFoundError) as exc:
                    _log.warning("cache migrate: %s → %s failed: %s", src, dst, exc)

    try:
        sentinel.touch()
    except OSError:
        pass
    if copied_any:
        _log.info("cache migrate: copied legacy .claude/cache → %s", new_root)
    _MIGRATED_ROOTS.add(repo_root)


def _auto_pull_enabled() -> bool:
    """Tier-2 auto-pull (remote prod pgvector → local sqlite) opt-out check.

    Default ON — on a fresh clone, missing local sqlite triggers a pull from
    prod pgvector so a new machine reaches steady-state without paying
    ~30 min OpenAI re-embed. `NOCTUS_DISABLE_AUTO_CACHE_PULL=1` opts out
    (CI / offline / first-machine-without-tunnel / debugging).
    """
    return os.environ.get(_AUTO_PULL_OPT_OUT_ENV, "").strip().lower() not in (
        "1", "true", "yes", "on",
    )


def _try_auto_pull(cache_name: str, repo_root: Path) -> bool:
    """If local cache is empty AND remote is reachable, pull remote → local.

    Best-effort: silent failure leaves the cache empty (the standard refresh
    flow then rebuilds locally). Sentinel + per-process memo so a missing
    remote (no tunnel / no DSN) only costs ONE resolution attempt per process.

    Returns True if a pull succeeded; False otherwise.
    """
    if not _auto_pull_enabled():
        return False
    if repo_root in _AUTO_PULLED_ROOTS:
        return False
    new_root = cache_dir(repo_root)
    sentinel = new_root / _AUTO_PULL_SENTINEL
    if sentinel.exists():
        _AUTO_PULLED_ROOTS.add(repo_root)
        return False
    # Late import to avoid circular dep + keep cache_backend lean when
    # the pull path is never exercised.
    try:
        from tools.noctus.dev.cache_deploy_mirror import pull_one_cache
    except ImportError:
        _AUTO_PULLED_ROOTS.add(repo_root)
        return False
    try:
        result = pull_one_cache(cache_name, repo_root=repo_root)
    except Exception as exc:  # remote unreachable, no DSN, schema mismatch — all fine
        _log.info("cache auto-pull: %s skipped (%s)", cache_name, exc)
        _AUTO_PULLED_ROOTS.add(repo_root)
        return False
    if result.get("ok"):
        try:
            sentinel.touch()
        except OSError:
            pass
        _AUTO_PULLED_ROOTS.add(repo_root)
        _log.info("cache auto-pull: %s pulled %d rows from remote",
                  cache_name, result.get("rows_pulled", 0))
        return True
    _log.info("cache auto-pull: %s failed (%s)", cache_name, result.get("error"))
    _AUTO_PULLED_ROOTS.add(repo_root)
    return False


@contextmanager
def acquire_refresh_lock(
    cache_name: str,
    *,
    repo_root: Path | None = None,
    timeout: float = 0.0,
) -> Iterator[bool]:
    """Single-writer lock per cache for refresh operations.

    Why this exists
        After Tier-1 relocation, ALL worktrees share `<git-common-dir>/noctusai/cache/`.
        N parallel pre-commits → N writers serialize on the same SQLite file,
        + N concurrent OpenAI embedding queries hit rate limits in parallel. The
        2026-05-28 dogpile observed three concurrent pre-commits stalling for
        31 min on shared `kb-embeddings.sqlite`. The fix: one writer at a time
        per cache; others SKIP cleanly and trust the in-flight refresh.

    Behavior
        `timeout=0` (default): non-blocking. Yields `True` if the caller is the
        sole writer; yields `False` immediately if another process holds the
        lock. Caller decides — typically log + skip (the in-flight refresh will
        bring the cache current; next boundary will revisit).

        `timeout>0`: blocking wait up to `timeout` seconds.

    Safety
        - `fcntl.flock` is auto-released on process death (kernel-tracked) — a
          crashed refresher does not strand the lock.
        - Lock file is a sibling sentinel; SQLite + WAL state is untouched.
        - Per-process: the lock affects refresh ENTRY only; concurrent SEARCH
          / READ still flows freely (WAL handles those).

    KB § PATTERNS/common/cache-portable-architecture.md §Concurrent-refresh.
    """
    import fcntl
    import time
    root = repo_root if repo_root is not None else REPO_ROOT
    cdir = cache_dir(root)
    lock_path = cdir / f"{cache_name}.refresh.lock"
    try:
        lock_path.touch()
    except OSError:
        # Cannot create the lock file — yield True and let the refresh attempt
        # proceed (the slower-path is better than the no-refresh-ever-path).
        yield True
        return
    fh = open(lock_path, "r")
    acquired = False
    try:
        if timeout <= 0:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                acquired = False
        else:
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    time.sleep(0.1)
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            fh.close()
        except OSError:
            pass


def cache_path(cache_name: str, repo_root: Path | None = None) -> Path:
    """Resolve a cache name to its persistent SQLite file path.

    Path layout (see `KB § PATTERNS/common/cache-portable-architecture.md`):
      `<git-common-dir>/noctusai/cache/<cache_name>.sqlite`

    Side effects (idempotent, per-process memoized — zero-cost after first
    call per repo_root):
      1. Ensures the cache directory exists.
      2. Migrates legacy `.claude/cache/` data once (copy, not move).
      3. On a fresh clone with no local data, attempts a Tier-2 auto-pull
         from the remote prod pgvector mirror (opt-out via
         `NOCTUS_DISABLE_AUTO_CACHE_PULL=1`).

    Args:
      cache_name: must be in `known_caches()`.
      repo_root: optional override (default: settings.REPO_ROOT).

    Raises:
      KeyError: if `cache_name` is unknown.
    """
    if cache_name not in _CACHE_FILES:
        raise KeyError(
            f"Unknown cache name {cache_name!r}; "
            f"valid: {sorted(_CACHE_FILES)}"
        )
    root = repo_root if repo_root is not None else REPO_ROOT
    _migrate_legacy_cache(root)
    path = cache_dir(root) / _CACHE_FILES[cache_name]
    if not path.exists():
        _try_auto_pull(cache_name, root)
    return path


# ── The Protocol ─────────────────────────────────────────────────────────────

@runtime_checkable
class CacheBackend(Protocol):
    """Pluggable cache-storage interface for the 5 keeper-mirror caches.

    Implementations:
      - `SqliteCacheBackend` (today, default — local file).
      - `PostgresCacheBackend` (planned — see roadmap).
      - `SupabaseCacheBackend` (planned — see roadmap).

    A backend is a connection factory + a name + a location string.
    Schema ownership stays with each cache module; the backend just
    opens a usable DB-API-2.0 connection.
    """

    def kind(self) -> str:
        """Backend identifier — `"sqlite"` / `"postgres"` / `"supabase"`."""
        ...

    def location(self, cache_name: str) -> str:
        """Human-readable location (file path / URL) for a named cache."""
        ...

    @contextmanager
    def connect(self, cache_name: str) -> Iterator[Any]:
        """Yield a DB-API-2.0 connection for a named cache.

        The yielded connection MUST support `.execute(sql, params)`,
        `.commit()`, and `.close()`. The context manager owns the
        connection's lifetime — implementations close on exit.
        """
        ...


# ── Default implementation: local SQLite ─────────────────────────────────────

class SqliteCacheBackend:
    """Default backend — local SQLite files under `.claude/cache/`.

    Behavior:
      - Resolves paths via `cache_path()` (centralized catalog).
      - Applies WAL mode on connect (cache-locking discipline).
      - Sets `row_factory = sqlite3.Row` for dict-like access.
      - Closes the connection on context-manager exit.

    The 5 existing cache modules each maintain their own `_connect()`
    helper today. This backend is byte-compatible — they CAN switch
    to it incrementally without behavior change.
    """

    def __init__(self, repo_root: Path | None = None):
        self._repo_root = repo_root

    def kind(self) -> str:
        return "sqlite"

    def location(self, cache_name: str) -> str:
        return str(cache_path(cache_name, self._repo_root))

    @contextmanager
    def connect(self, cache_name: str) -> Iterator[sqlite3.Connection]:
        path = cache_path(cache_name, self._repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        apply_locking_pragmas(conn)
        try:
            yield conn
        finally:
            conn.close()


# ── Factory ──────────────────────────────────────────────────────────────────

_ENV_VAR = "NOCTUS_CACHE_BACKEND"
_VALID_BACKENDS = ("sqlite", "postgres")  # extend when Phase 4+ ships


def get_backend(repo_root: Path | None = None) -> CacheBackend:
    """Return the configured backend.

    Resolution:
      - Reads `NOCTUS_CACHE_BACKEND` env var (case-insensitive).
      - Defaults to `"sqlite"` (today's only valid value).
      - Unknown value ⇒ `ValueError` — fail loud per no-silent-errors.

    Future (per roadmap):
      - `"postgres"` ⇒ `PostgresCacheBackend(dsn=POSTGRES_DSN)`.
      - `"supabase"` ⇒ `SupabaseCacheBackend(url=SUPABASE_URL, key=SUPABASE_KEY)`.
      - Per-cache override env var (`NOCTUS_CACHE_BACKEND_<NAME>`) for
        gradual migration (vector caches first, methodology caches stay
        local — see roadmap Phase 3).
    """
    requested = os.environ.get(_ENV_VAR, "sqlite").strip().lower()
    if requested == "sqlite":
        return SqliteCacheBackend(repo_root=repo_root)
    elif requested == "postgres":
        return PostgresCacheBackend()
    raise ValueError(
        f"{_ENV_VAR}={requested!r} is not a valid backend yet; "
        f"valid today: {sorted(_VALID_BACKENDS)}. "
        f"Migration roadmap: project-history/roadmaps/"
        f"cache-backend-portability-2026-05.md."
    )


__all__ = [
    "CacheBackend",
    "PostgresCacheBackend",
    "SqliteCacheBackend",
    "cache_path",
    "get_backend",
    "known_caches",
]
