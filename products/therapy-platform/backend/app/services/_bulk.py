"""
Bulk-lookup helper — pre-fetch ``{id: value}`` maps to avoid N+1 in
admin listings.

Surfaced 2026-05-10 from the N=3 within-product recurrence:
``_resolve_clinic_names`` + ``_resolve_session_counts`` +
``_resolve_message_previews`` all shipped the same
``(db, list[id]) -> {id: scalar}`` shape. Architect's Phase-0 audit also
caught a 4th inline instance in ``routers/admin_financials.py`` (clinic
name lookup).

Single-row-per-id lookups consume this helper. Aggregation patterns
(e.g. session counts via ``.eq("status", "completed")`` + COUNT) are a
different abstraction and stay as-is; see Phase 0 audit notes.

Stays in-product. Seed-promotion deferred to N=2 cross-product trigger.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence


def bulk_lookup(
    db: Any,
    table: str,
    ids: Sequence[str],
    key_col: str = "id",
    value_cols: list[str] | str = "name",
) -> Dict[str, Any]:
    """Bulk pre-fetch a ``{id: value_or_dict}`` map from ``table``.

    - ``value_cols: str`` → returns ``{id: scalar}`` keyed by ``key_col``.
    - ``value_cols: list[str]`` → returns ``{id: {col: val, ...}}``.
    - Empty ``ids`` short-circuits to ``{}`` (no DB call).
    - Falsy ids are filtered; duplicates collapsed via ``set``.

    Preserves the canonical ``.in_(key_col, ids).execute()`` bulk-pre-fetch
    shape — one query, no N+1. Use at admin listing / DTO-mapping sites
    that need to resolve names / display fields from product-owned tables.
    """
    if not ids:
        return {}
    unique_ids = list({i for i in ids if i})
    if not unique_ids:
        return {}

    if isinstance(value_cols, str):
        select_cols = f"{key_col}, {value_cols}"
    else:
        select_cols = ", ".join([key_col, *value_cols])

    result = (
        db.table(table)
        .select(select_cols)
        .in_(key_col, unique_ids)
        .execute()
    )
    rows = result.data or []

    if isinstance(value_cols, str):
        return {
            row[key_col]: row.get(value_cols)
            for row in rows
            if row.get(key_col)
        }
    return {
        row[key_col]: {c: row.get(c) for c in value_cols}
        for row in rows
        if row.get(key_col)
    }
