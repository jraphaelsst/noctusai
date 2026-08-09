"""Process-wide persistence store for IgIg domain data.

**Domain data only.** Auth, orgs, users and roles stay on Supabase through
the seed's `create_database_module()` / `create_dependencies()` — this store
holds the `igig` schema's business tables and nothing else. That split is the
decision recorded in KB § 02-LANDSCAPE's IgIg row: develop domain data on
SQLite, keep identity on Supabase so core SSO and `public.noctus_users` work
unchanged.

Swapping to Supabase later is a change HERE and nowhere else — repositories,
services and routers are written against the ``RecordStore`` Protocol.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from noctusai_lib.integrations.persistence import RecordStore, get_record_store

from app.config import settings
from app.repositories import Repositorios

logger = logging.getLogger(__name__)

__all__ = ["get_store", "get_repositorios", "aplicar_schema_sqlite", "reset_store"]

_SQLITE_SCHEMA = Path(__file__).resolve().parents[1] / "migrations" / "sqlite" / "001_dominio.sql"


@lru_cache(maxsize=1)
def get_store() -> RecordStore:
    """The process's store, built once.

    Cached because :class:`SqliteRecordStore` owns a connection; building one
    per request would leak file handles and defeat its serialisation lock.

    Today this always resolves to SQLite (``settings.igig_sqlite_path``).
    When IgIg moves to Supabase, pass the seed's user-scoped client here
    instead — `get_record_store()` already prefers it over any SQLite path.
    """
    store = get_record_store(sqlite_path=settings.igig_sqlite_path)
    logger.info(
        "igig persistence store: %s (sqlite_path=%s)",
        type(store).__name__,
        settings.igig_sqlite_path,
    )
    aplicar_schema_sqlite(store)
    return store


def aplicar_schema_sqlite(store: RecordStore) -> None:
    """Apply the SQLite domain schema if the store is SQLite-backed.

    Idempotent — every statement in the mirror is ``IF NOT EXISTS``. This is
    the development substitute for running migrations against Postgres; the
    canonical `006_igig_dominio.sql` still applies to Supabase via the normal
    migration path.
    """
    executescript = getattr(store, "executescript", None)
    if executescript is None:
        return  # Supabase / in-memory — schema lives elsewhere.
    if not _SQLITE_SCHEMA.exists():
        raise FileNotFoundError(f"SQLite domain schema missing at {_SQLITE_SCHEMA}")
    executescript(_SQLITE_SCHEMA.read_text(encoding="utf-8"))


def get_repositorios() -> Repositorios:
    """FastAPI dependency — the repository set bound to the process store."""
    return Repositorios(get_store())


def reset_store() -> None:
    """Drop the cached store. Tests only — lets a test swap in a Fake."""
    get_store.cache_clear()
