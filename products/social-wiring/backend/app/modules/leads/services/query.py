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
present), same as the aggregation math used to be — the fact table is
bounded (~12k rows for the source org) so a full fetch stays within a
single request's budget, but a full fetch PER endpoint, times 5+
concurrent analytics calls on one page load, does not (see
migration 027's header + ``analytics_service.py``'s module docstring
for the incident this caused). ``summary``/``timeseries``/
``by_dimension``/``heatmap``/``facets`` no longer call ``fetch_filtered``
at all — they call the ``social_wiring.leads_analytics_*`` /
``leads_facets`` SQL functions via ``to_rpc_params`` + ``client.rpc()``,
which push ``q``/``ano``/``mes`` (and every other filter) into Postgres
directly; the mock/prod divergence noted above is exactly why those
functions are the ANALYTICS-only escape hatch and this module's
``apply_db_filters``/``fetch_filtered`` stay as they were for the two
paths that still need real Python-side rows: the list endpoint's
default-sort fast path still needs ``q``/``ano``/``mes`` applied
post-fetch when it falls back to full rows (label-sort / those three
filters set), and the importer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence import (
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    PagerOverflowError,
    iter_paged_rows,
)
from noctusai_lib.primitives.phone import phone_search_digits


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

#: Below this, a digit run is too short to be a phone fragment and matching on
#: it would surface unrelated rows (a house number in `observacoes`, a year).
_MIN_PHONE_FRAGMENT_DIGITS = 4


def matches_free_text(row: dict, q: Optional[str]) -> bool:
    """``q`` matches when ANY of the 4 free-text columns contains it
    (case-insensitive substring), mirroring the SQL ``ILIKE %q%`` OR the
    contract describes. Empty/None ``q`` always matches (no constraint).

    PLUS a phone-aware pass, which is a strict SUPERSET of the substring
    behaviour — it only ever adds matches, never removes one.

    It exists because canonicalizing the phone format (migration 037) changed
    what the UI SHOWS without changing what a substring search matches: the
    Funil card and the detail modal render ``+5511981912534`` while the row
    stores ``11 98191.2534``. Copying the number you can see and pasting it
    into the search box returned nothing — across ~11.6k leads. Comparing
    canonical digit runs makes every spelling of one number find that number,
    in either direction.
    """
    if not q:
        return True
    needle = q.strip().lower()
    if not needle:
        return True
    for col in _Q_COLUMNS:
        val = row.get(col)
        if isinstance(val, str) and needle in val.lower():
            return True
    return _matches_phone(row.get("contato"), needle)


def _matches_phone(contato: Optional[str], needle: str) -> bool:
    """Compare the CANONICAL digit run of the stored contact against the
    needle's, so format differences stop hiding a match."""
    if not isinstance(contato, str) or "@" in contato:
        return False
    needle_digits = phone_search_digits(needle)
    if not needle_digits or len(needle_digits) < _MIN_PHONE_FRAGMENT_DIGITS:
        return False
    stored = phone_search_digits(contato)
    return bool(stored) and needle_digits in stored


def to_rpc_params(org_id: UUID, filters: LeadFilters) -> dict:
    """Marshal ``(org_id, filters)`` into the parameter dict every
    ``social_wiring.leads_analytics_*`` / ``leads_facets`` RPC function
    expects (migration ``027_leads_analytics_rpc.sql``) — the single
    source of truth for the Python<->SQL parameter contract, shared by
    every RPC-calling service function (no per-caller drift).

    An empty repeatable filter becomes SQL ``NULL`` (not an empty array):
    the SQL side applies each filter as
    ``(p_x IS NULL OR col = ANY(p_x))``, and Postgres's ``= ANY('{}')``
    matches NOTHING — passing ``[]`` would silently turn "no constraint
    on this dimension" into "match zero rows", the opposite of §5.1
    ("Empty/absent = no constraint")."""
    return {
        "p_org_id": str(org_id),
        "p_de": filters.de.isoformat() if filters.de else None,
        "p_ate": filters.ate.isoformat() if filters.ate else None,
        "p_ano": list(filters.ano) or None,
        "p_mes": list(filters.mes) or None,
        "p_origem_id": [str(v) for v in filters.origem_id] or None,
        "p_corretor_id": [str(v) for v in filters.corretor_id] or None,
        "p_tipo": list(filters.tipo) or None,
        "p_tier": list(filters.tier) or None,
        "p_empreendimento": list(filters.empreendimento) or None,
        "p_regiao": list(filters.regiao) or None,
        "p_needs_review": filters.needs_review,
        "p_q": filters.q,
    }


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


#: PostgREST caps any single response at ``db-max-rows`` (1000 by default on
#: Supabase). A bare ``.select().execute()`` therefore returns AT MOST 1000
#: rows with NO error and NO truncation signal — the caller cannot tell a
#: complete 1000-row result from a truncated 12,000-row one. Every count,
#: share_pct and chart series in this module derives from `fetch_filtered`,
#: so that silent cap made all of them wrong (observed 2026-07-22: summary
#: reported total=1000 against 12,177 real rows). We page explicitly instead.
_PAGE_SIZE = DEFAULT_PAGE_SIZE

#: Hard ceiling on the paging loop — a runaway (e.g. a client whose `.range()`
#: is a no-op) must fail LOUDLY rather than spin or silently truncate.
_MAX_PAGES = DEFAULT_MAX_PAGES


class LeadsResultTooLargeError(PagerOverflowError):
    """Raised when a filter set resolves to more rows than the pager will
    walk. Deliberately an exception, not a silent truncation: a wrong-but-
    plausible number in a KPI tile is worse than a visible failure.

    Subclasses the seed's :class:`PagerOverflowError` so this module keeps
    its own public name while the shared pager (which owns the loop, the
    no-progress guard and the ceiling) does the raising — see
    ``noctusai_lib.integrations.persistence.paging``."""


def _with_id_column(columns: str) -> str:
    """``columns`` with ``id`` guaranteed present.

    ``select("*")`` already includes it; a projection list may not, and
    the pager refuses to run without its dedup key (deliberately — a
    guard that silently no-ops brings the infinite loop back)."""
    if columns.strip() == "*":
        return columns
    parts = [part.strip() for part in columns.split(",") if part.strip()]
    if "id" in parts:
        return columns
    return ", ".join(["id", *parts])


def fetch_filtered(client: Any, org_id: UUID, filters: LeadFilters) -> list[dict]:
    """Fetch every ``leads`` row (as raw dicts, joins not yet resolved)
    for ``org_id`` matching ``filters`` — the shared primitive every
    list/analytics service builds on. ``client`` is already
    ``social_wiring``-scoped — see
    ``app/modules/leads/deps.py::get_leads_client``'s docstring for why
    this deliberately does NOT call ``.schema(...)`` itself.

    Pages through PostgREST's per-response row cap (see ``_PAGE_SIZE``)
    and returns the COMPLETE result set. ``.order("id")`` is required for
    the paging to be stable — without a deterministic sort PostgREST may
    return overlapping/missing rows across ranges."""

    def fetch_page(start: int, end: int):
        query = client.table("leads").select("*").eq("org_id", str(org_id))
        query = apply_db_filters(query, filters)
        return query.order("id").range(start, end).execute().data

    rows = list(
        iter_paged_rows(
            fetch_page,
            page_size=_PAGE_SIZE,
            max_pages=_MAX_PAGES,
            label=f"leads result for org_id={org_id}",
            overflow_error=LeadsResultTooLargeError,
        )
    )

    rows = [backfill_generated_columns(r) for r in rows]
    rows = [r for r in rows if matches_ano_mes(r, filters)]
    if filters.q:
        rows = [r for r in rows if matches_free_text(r, filters.q)]
    return rows


def iter_leads_rows(
    client: Any,
    org_id: UUID,
    columns: str = "*",
    **eq_filters: Any,
) -> list[dict]:
    """Shared PostgREST pager for the ``leads`` table reads that aren't
    already covered by ``fetch_filtered``'s ``LeadFilters``-shaped call
    sites — dimension-management scans (unmapped-origem/corretor,
    relink-by-alias, delete-with-reassign) and the importer's
    existing-row lookups. Every one of those used to be a bare
    ``.select().execute()``, capped at PostgREST's ``_PAGE_SIZE`` rows
    with no truncation signal (the same class of bug ``fetch_filtered``
    already fixes — see this module's header comment for the incident).

    Same paging contract as ``fetch_filtered``: pages via
    ``.order("id").range(...)``, raises ``LeadsResultTooLargeError``
    instead of silently truncating past ``_MAX_PAGES``. Callers pass
    plain ``column=value`` equality filters as kwargs (``.eq(k, v)`` per
    entry) instead of a full ``LeadFilters`` — every current caller only
    needs ``org_id`` scoping plus at most one extra ``eq`` (e.g.
    ``source_sheet=name``).

    ``id`` is forced into the projection even when the caller did not ask
    for it: the pager's no-progress guard dedupes on it, and the columns
    callers DO ask for here (``origem_raw``, ``corretor_raw``,
    ``source_sheet``) are deliberately non-unique — deduping on one of
    those would collapse rows those callers are counting.
    """
    selected = _with_id_column(columns)

    def fetch_page(start: int, end: int):
        query = client.table("leads").select(selected).eq("org_id", str(org_id))
        for key, value in eq_filters.items():
            query = query.eq(key, value)
        return query.order("id").range(start, end).execute().data

    return list(
        iter_paged_rows(
            fetch_page,
            page_size=_PAGE_SIZE,
            max_pages=_MAX_PAGES,
            label=f"leads scan for org_id={org_id}",
            overflow_error=LeadsResultTooLargeError,
        )
    )


def chunked(items: list, size: int):
    """Yield ``items`` in ``size``-sized slices — shared by every batched
    write in this module (``.in_("id", chunk)`` writes instead of one
    round-trip per row)."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


__all__ = [
    "LeadFilters",
    "apply_db_filters",
    "matches_free_text",
    "matches_ano_mes",
    "fetch_filtered",
    "backfill_generated_columns",
    "LeadsResultTooLargeError",
    "to_rpc_params",
    "iter_leads_rows",
    "chunked",
]
