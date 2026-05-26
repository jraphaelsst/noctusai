"""cache_backend_postgres — PostgresCacheBackend, the Phase 3.1 remote backend.

Implements the `CacheBackend` Protocol for Postgres + pgvector.

## Per-cache table naming

Cache names are mapped to qualified table names via:

    f"{schema}.cache_{cache_name.replace('-', '_')}"

Examples:
    "keeper-patterns"  → noctus_cache.cache_keeper_patterns
    "agent-context"    → noctus_cache.cache_agent_context
    "auto-improvement" → noctus_cache.cache_auto_improvement
    "kb-embeddings"    → noctus_cache.cache_kb_embeddings
    "code-embeddings"  → noctus_cache.cache_code_embeddings

## DSN resolution order

1. Explicit ``dsn`` kwarg passed to the constructor.
2. ``NOCTUS_CACHE_POSTGRES_DSN`` env var.
3. Individual env vars built into a DSN:
   - ``NOCTUS_CACHE_POSTGRES_HOST`` (default: ``localhost``)
   - ``NOCTUS_CACHE_POSTGRES_PORT`` (default: ``5432``)
   - ``NOCTUS_CACHE_POSTGRES_DB``   (default: ``noctusai``)
   - ``NOCTUS_CACHE_POSTGRES_USER`` (default: ``postgres``)
   - ``NOCTUS_CACHE_POSTGRES_PASSWORD`` (default: ``""``)

## Vector type registration

For ``cache_name in ("kb-embeddings", "code-embeddings")``, the backend
registers the pgvector numpy type extension on the connection via
``pgvector.psycopg2.register_vector``.  This is a no-op if pgvector is
not installed on the server — but the *client-side* ``pgvector`` Python
package MUST be available.  If it is not available, the import is
deferred to connect-time so that non-embedding-cache consumers can use
this module without the optional dependency.

## _ensure_schema() bootstrap helper

Call once at provisioning time (not per-connect — it is too heavy):

    backend._ensure_schema()

Runs:
    CREATE SCHEMA IF NOT EXISTS noctus_cache;
    CREATE EXTENSION IF NOT EXISTS vector;

The ``vector`` extension requires superuser or ``CREATE`` privilege on the
database; a warning is logged if the statement fails (non-fatal).

## Roadmap context

See ``project-history/roadmaps/cache-backend-portability-2026-05.md``
Phase 3.1 — shipped 2026-05-26 evening (trigger T2 fired).
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# ── Embedding-cache names that need pgvector type registration ────────────────
_VECTOR_CACHES = frozenset({"kb-embeddings", "code-embeddings"})


class PostgresCacheBackend:
    """PostgreSQL backend satisfying the `CacheBackend` Protocol.

    Args:
        dsn: Explicit libpq connection string.  If *None*, resolved from
            ``NOCTUS_CACHE_POSTGRES_DSN`` env var, then from the
            individual ``NOCTUS_CACHE_POSTGRES_*`` env vars.
        schema: Postgres schema that holds all cache tables.
            Default: ``"noctus_cache"``.
    """

    def __init__(self, dsn: str | None = None, *, schema: str = "noctus_cache") -> None:
        self._explicit_dsn = dsn
        self._schema = schema

    # ── Protocol surface ─────────────────────────────────────────────────────

    def kind(self) -> str:
        """Backend identifier — always ``"postgres"``."""
        return "postgres"

    def location(self, cache_name: str) -> str:
        """Return a human-readable URL for *cache_name* (no password).

        Shape: ``postgresql://<host>/<db>/<schema>.<table>``
        """
        host = os.environ.get("NOCTUS_CACHE_POSTGRES_HOST", "localhost")
        port = os.environ.get("NOCTUS_CACHE_POSTGRES_PORT", "5432")
        db = os.environ.get("NOCTUS_CACHE_POSTGRES_DB", "noctusai")
        table = self._table_name(cache_name)
        return f"postgresql://{host}:{port}/{db}/{table}"

    @contextmanager
    def connect(self, cache_name: str) -> Iterator[Any]:
        """Yield a psycopg2 connection for *cache_name*.

        Behavior:
        - ``autocommit`` is OFF — callers commit explicitly.
        - For embedding caches, ``pgvector`` numpy type is registered.
        - Connection is closed on context-manager exit.
        """
        import psycopg2  # type: ignore[import]

        dsn = self._resolve_dsn()
        conn = psycopg2.connect(dsn)
        conn.autocommit = False

        if cache_name in _VECTOR_CACHES:
            try:
                from pgvector.psycopg2 import register_vector  # type: ignore[import]
                register_vector(conn)
            except ImportError:
                logger.warning(
                    "pgvector Python package not installed; "
                    "vector type registration skipped for cache %r. "
                    "Install pgvector to enable KNN operations.",
                    cache_name,
                )

        try:
            yield conn
        finally:
            conn.close()

    # ── Bootstrap helper ─────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create the cache schema + pgvector extension (call once at bootstrap).

        NOT called from ``connect()`` — this is too heavy per-connection.
        Call explicitly during deployment / provisioning.

        Requires superuser or ``CREATE`` privilege on the database for
        the ``vector`` extension; logs a warning if that statement fails.
        """
        import psycopg2  # type: ignore[import]

        dsn = self._resolve_dsn()
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE SCHEMA IF NOT EXISTS {self._schema}"
                )
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "CREATE EXTENSION IF NOT EXISTS vector failed "
                        "(non-fatal — requires superuser or CREATE privilege): %s",
                        exc,
                    )
        finally:
            conn.close()

    # ── Private helpers ──────────────────────────────────────────────────────

    def _table_name(self, cache_name: str) -> str:
        """Resolve a cache name to its qualified Postgres table name."""
        return f"{self._schema}.cache_{cache_name.replace('-', '_')}"

    def _resolve_dsn(self) -> str:
        """Resolve the connection string using the 3-step priority chain."""
        if self._explicit_dsn is not None:
            return self._explicit_dsn

        env_dsn = os.environ.get("NOCTUS_CACHE_POSTGRES_DSN")
        if env_dsn:
            return env_dsn

        host = os.environ.get("NOCTUS_CACHE_POSTGRES_HOST", "localhost")
        port = os.environ.get("NOCTUS_CACHE_POSTGRES_PORT", "5432")
        db = os.environ.get("NOCTUS_CACHE_POSTGRES_DB", "noctusai")
        user = os.environ.get("NOCTUS_CACHE_POSTGRES_USER", "postgres")
        password = os.environ.get("NOCTUS_CACHE_POSTGRES_PASSWORD", "")
        return (
            f"host={host} port={port} dbname={db} "
            f"user={user} password={password}"
        )


__all__ = ["PostgresCacheBackend"]
