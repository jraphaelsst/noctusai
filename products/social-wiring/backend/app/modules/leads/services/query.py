"""The canonical Leads filter set (§5.1 of the PROJECT contract) applied
to a Supabase-style query builder, plus the shared "fetch every row a
filter set resolves to" primitive every list/analytics endpoint composes
from — one filter implementation, reused everywhere (CRUD list,
summary/timeseries/by-dimension/heatmap, facets).

Design note — why filtering isn't 100% DB-pushed
──────────────────────────────────────────────────
Most simple-comparison filters (``de``/``ate``/``origem_id``/
``corretor_id``/``tipo``/``tier``/``empreendimento``/``regiao``/
``needs_review``) ARE pushed to the query builder via
``eq``/``in_``/``gte``/``lte`` — these evaluate correctly against BOTH
the real Supabase/PostgREST client and
``noctusai_lib.testing.MockSupabaseClient`` (confirmed against
``_FilterMixin``).

TWO filters are deliberately NOT DB-pushed:

* ``q`` (free text over ``cliente_nome``/``contato``/``codigo_raw``/
  ``observacoes``) — ``MockRequestBuilder.or_()`` records the call but
  evaluates as match-all (see its docstring: "complex PostgREST
  expressions ... evaluate as match-all"), which would make ``q``
  untestable against the canonical test double while silently
  no-op'ing in the suite and working in prod.
* ``ano``/``mes`` — these are ``GENERATED ALWAYS AS (...) STORED``
  columns (§4); real Postgres computes + can filter on them, but
  ``MockSupabaseClient`` has no server-side computation, so a stored
  mock row never actually HAS an ``ano``/``mes`` key to filter against
  (only ``backfill_generated_columns`` derives them, transiently, at
  READ time) — pushing ``.in_("ano", ...)`` to the mock would silently
  match zero rows every time, the same prod/test divergence as ``q``.

Both are applied in Python, post-fetch (after
``backfill_generated_columns`` so ``ano``/``mes`` are guaranteed
present), same as the aggregation math (sorting/pagination/analytics)
already has to be — the fact table is bounded (~12k rows for the source
org) so this stays well within a single request's budget, and it's the
SAME code path prod and tests exercise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID


@dataclass
class LeadFilters:
    """The canonical filter set — every list + analytics endpoint accepts
    exactly this shape (§5.1). Repeatable params are lists; empty/None =
    no constraint on that dimension."""

    de: Optional[date] = None
    ate: Optional[date] = None
    ano: list[int] = field(default_factory=list)
    mes: list[int] = field(default_factory=list)
    origem_id: list[UUID] = field(default_factory=list)
    corretor_id: list[UUID] = field(default_factory=list)
    tipo: list[str] = field(default_factory=list)
    tier: list[str] = field(default_factory=list)
    empreendimento: list[str] = field(default_factory=list)
    regiao: list[str] = field(default_factory=list)
    needs_review: Optional[bool] = None
    q: Optional[str] = None


def apply_db_filters(query: Any, filters: LeadFilters) -> Any:
    """Apply every filter EXCEPT ``q`` to a ``.table("leads")``-style
    query builder. Returns the same builder (chainable)."""
    if filters.de is not None:
        query = query.gte("data_entrada", filters.de.isoformat())
    if filters.ate is not None:
        query = query.lte("data_entrada", filters.ate.isoformat())
    if filters.origem_id:
        query = query.in_("origem_id", [str(v) for v in filters.origem_id])
    if filters.corretor_id:
        query = query.in_("corretor_id", [str(v) for v in filters.corretor_id])
    if filters.tipo:
        query = query.in_("tipo_lead", list(filters.tipo))
    if filters.tier:
        query = query.in_("anuncio_tier", list(filters.tier))
    if filters.empreendimento:
        query = query.in_("empreendimento", list(filters.empreendimento))
    if filters.regiao:
        query = query.in_("regiao", list(filters.regiao))
    if filters.needs_review is not None:
        query = query.eq("needs_review", filters.needs_review)
    return query


def backfill_generated_columns(row: dict) -> dict:
    """``ano``/``mes`` are ``GENERATED ALWAYS AS (...) STORED`` on real
    Postgres (§4) — they can never appear in an INSERT/UPDATE payload
    (Postgres rejects an explicit value for a generated column), so
    real Supabase always returns them computed. ``MockSupabaseClient``
    has no such server-side computation and simply echoes back whatever
    was written — this derives them from ``data_entrada`` when absent,
    transiently, at read time, so both environments hand callers a
    complete row. No-op (returns ``row`` unchanged) when already present
    (the real-Postgres case)."""
    if row.get("ano") is not None or not row.get("data_entrada"):
        return row
    value = row["data_entrada"]
    try:
        if isinstance(value, str):
            year, month = int(value[0:4]), int(value[5:7])
        else:
            year, month = value.year, value.month
    except (ValueError, IndexError, AttributeError):
        return row
    return {**row, "ano": year, "mes": month}


_Q_COLUMNS = ("cliente_nome", "contato", "codigo_raw", "observacoes")


def matches_free_text(row: dict, q: Optional[str]) -> bool:
    """``q`` matches when ANY of the 4 free-text columns contains it
    (case-insensitive substring), mirroring the SQL ``ILIKE %q%`` OR the
    contract describes. Empty/None ``q`` always matches (no constraint)."""
    if not q:
        return True
    needle = q.strip().lower()
    if not needle:
        return True
    for col in _Q_COLUMNS:
        val = row.get(col)
        if isinstance(val, str) and needle in val.lower():
            return True
    return False


def matches_ano_mes(row: dict, filters: LeadFilters) -> bool:
    """Post-fetch ``ano``/``mes`` predicate — see the module docstring
    for why these two aren't DB-pushed. Call AFTER
    ``backfill_generated_columns`` so ``row["ano"]``/``row["mes"]`` are
    guaranteed present."""
    if filters.ano and row.get("ano") not in filters.ano:
        return False
    if filters.mes and row.get("mes") not in filters.mes:
        return False
    return True


def fetch_filtered(client: Any, org_id: UUID, filters: LeadFilters) -> list[dict]:
    """Fetch every ``leads`` row (as raw dicts, joins not yet resolved)
    for ``org_id`` matching ``filters`` — the shared primitive every
    list/analytics service builds on. ``client`` is already
    ``social_wiring``-scoped — see
    ``app/modules/leads/deps.py::get_leads_client``'s docstring for why
    this deliberately does NOT call ``.schema(...)`` itself."""
    query = client.table("leads").select("*").eq("org_id", str(org_id))
    query = apply_db_filters(query, filters)
    resp = query.execute()
    rows = [backfill_generated_columns(r) for r in list(resp.data or [])]
    rows = [r for r in rows if matches_ano_mes(r, filters)]
    if filters.q:
        rows = [r for r in rows if matches_free_text(r, filters.q)]
    return rows


__all__ = [
    "LeadFilters",
    "apply_db_filters",
    "matches_free_text",
    "matches_ano_mes",
    "fetch_filtered",
    "backfill_generated_columns",
]
