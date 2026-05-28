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

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from settings import REPO_ROOT
from tools.noctus.dev.cache_backend_postgres import PostgresCacheBackend  # noqa: E402


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
}

_CACHE_DIR_REL = ".claude/cache"


def known_caches() -> list[str]:
    """Return the registered cache names (stable order)."""
    return list(_CACHE_FILES.keys())


def cache_path(cache_name: str, repo_root: Path | None = None) -> Path:
    """Resolve a cache name to its local SQLite file path.

    Even when a remote backend is configured, the resolved local
    path remains the fallback location — backends are free to use
    it (sqlite does) or ignore it (postgres/supabase will).

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
    return root / _CACHE_DIR_REL / _CACHE_FILES[cache_name]


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
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass  # tmpfs / readonly fallback — non-fatal
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
