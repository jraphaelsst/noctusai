"""Persistence seam — Protocol + Fake + Real(s) + factory.

Lets a product develop its domain layer against SQLite and later land on
Supabase/Postgres without rewriting repositories. Authored 2026-08-09 for
the IgIg agency-ERP, which develops on SQLite by explicit decision and
migrates to Supabase afterwards; product-agnostic by construction, so any
product may consume it.

Layer placement: ``integrations/`` because it touches the DB — see
``KB § PATTERNS/architect/seed-lib-layout.md § decision tree`` step 1.
Shape: ``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

Usage::

    from noctusai_lib.integrations.persistence import get_record_store

    store = get_record_store(sqlite_path="var/igig.db")     # → SqliteRecordStore
    store = get_record_store(supabase_client=client)        # → SupabaseRecordStore
    store = get_record_store()                              # → InMemoryRecordStore

**Per-entity repositories do NOT live here.** They are single-product
code and belong in ``products/<slug>/backend/app/repositories/``; this
module ships only the generic machinery every product could share.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .fake_adapter import InMemoryRecordStore
from .paging import (
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    PagerOverflowError,
    iter_paged_rows,
)
from .sqlite_adapter import SqliteRecordStore
from .supabase_adapter import SupabaseLike, SupabaseRecordStore
from .types import (
    Filter,
    Op,
    Order,
    PersistenceError,
    QuerySpec,
    Record,
    RecordNotFound,
    RecordStore,
)

__all__ = [
    # Protocol + value objects
    "RecordStore",
    "Record",
    "QuerySpec",
    "Filter",
    "Order",
    "Op",
    "RecordNotFound",
    "PersistenceError",
    # Implementations
    "InMemoryRecordStore",
    "SqliteRecordStore",
    "SupabaseRecordStore",
    "SupabaseLike",
    # Factory
    "get_record_store",
    # Offset-paged reads (see paging.py — hazard is the LOOP, not the query)
    "iter_paged_rows",
    "PagerOverflowError",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_MAX_PAGES",
]


def get_record_store(
    *,
    supabase_client: Any | None = None,
    sqlite_path: str | Path | None = None,
) -> RecordStore:
    """Return the store the environment calls for.

    One decision, in precedence order:

    1. ``supabase_client`` present → :class:`SupabaseRecordStore` (production).
    2. ``sqlite_path`` present → :class:`SqliteRecordStore` (local development).
    3. neither → :class:`InMemoryRecordStore` (tests).

    Supabase wins over SQLite when both are supplied: a configured
    production backend must never be silently shadowed by a leftover
    local file. Adapter-specific configuration belongs on the adapter
    constructors, not here — this factory answers "which kind", nothing
    else (``KB § PATTERNS/backend/seed-fake-real-adapter.md § anti-patterns``).
    """
    if supabase_client is not None:
        return SupabaseRecordStore(supabase_client)
    if sqlite_path is not None:
        return SqliteRecordStore(sqlite_path)
    return InMemoryRecordStore()
