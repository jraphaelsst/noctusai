"""CRUD + list + facets over the ``leads`` fact table.

Every write coerces UUID/date python values to their JSON-safe string
form before hitting the query builder (both the real Supabase client and
the SQLite/Mock test doubles store JSON-serializable primitives, not
python ``UUID``/``date`` objects).

List pagination — DB-pushed count + page, with a documented fallback
────────────────────────────────────────────────────────────────────
``list_leads`` used to call ``fetch_filtered`` unconditionally — fetch
EVERY matching row, sort in Python, then slice the requested page — so
``total`` (and every page after the first) cost a full-table fetch. It
now pushes both the count (``select("id", count="exact")``, the same
idiom as ``documentos.py``/``propostas.py``/every other paginated list
in this fleet) and the page itself (``.order().range()``) to Postgres
for the COMMON case: sort by a real column (``data_entrada``,
``cliente_nome``, ``created_at``) with none of ``q``/``ano``/``mes`` set.

Three things are NOT DB-pushed here, each for the same reason
``query.py``'s module docstring gives:

* ``q`` — not evaluated server-side by ``apply_db_filters`` (see there).
* ``ano``/``mes`` — ``GENERATED ALWAYS`` columns; a mock-inserted row has
  no such key until ``backfill_generated_columns`` runs, so pushing
  ``.in_("ano", ...)`` would silently match zero rows in the test suite.
* ``sort in ("origem", "corretor")`` — these order by the JOINED
  label (``lead_sources.label`` / ``lead_corretores.nome``), which the
  bare ``leads`` table has no column for; sorting requires the full
  row set resolved against ``refs`` in Python, same as before.

Any of the three still routes through the ORIGINAL ``fetch_filtered`` +
Python sort/slice path — unchanged, still the safety net for those
cases. This is a deliberate, narrower win than "always one round-trip":
it eliminates the full-fetch for the sort/filter combination the Leads
page actually opens with by default (``data_entrada`` desc, no
`q`/`ano`/`mes`), not every combination.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.phone import normalize_phone

from app.modules.leads.services.query import (
    LeadFilters,
    apply_db_filters,
    backfill_generated_columns,
    fetch_filtered,
    to_rpc_params,
)

_SCHEMA = "social_wiring"
#: `NOT NULL` columns on `leads` (migration 025) — see `update_lead`'s
#: docstring for why an explicit `null` patch value for one of these is
#: ignored rather than applied.
_LEADS_NOT_NULLABLE_FIELDS = {"data_entrada", "tipo_lead", "needs_review"}

_SORTABLE = {"data_entrada", "cliente_nome", "origem", "corretor", "created_at"}
#: sort names that map 1:1 onto a real `leads` column PostgREST can
#: `.order()` directly — the other two (`origem`/`corretor`) need a
#: joined label, see the module docstring.
_DB_SORTABLE = {"data_entrada", "cliente_nome", "created_at"}


def _table(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see
    # `app/modules/leads/deps.py::get_leads_client`'s docstring for why
    # this deliberately does NOT re-call `.schema(_SCHEMA)` here.
    return client.table(name)


def _jsonify(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _jsonify_payload(payload: dict) -> dict:
    return {k: _jsonify(v) for k, v in payload.items()}


def _derive_contato_fields(payload: dict) -> dict:
    """Fill ``contato_norm``/``contato_tipo`` from ``contato``.

    Migration 037 installs ``canonicalize_lead_contato_trigger`` to guarantee
    this at the DB, because leads arrive through three write paths and the next
    one added would forget a service-layer call. So why do it HERE too?

    Two reasons, and neither is belt-and-braces:

    1. ``MockSupabaseClient`` has no triggers. Without this, every test would
       assert against a shape production never produces — the fixture-vs-real
       schema drift class.
    2. This function is the one place ``contato_norm`` was NEVER derived
       before: only the workbook importer set it, so a lead created through
       ``POST /api/leads`` shipped with ``contato_norm``/``contato_tipo`` NULL
       (15 and 2 live rows on 2026-07-30) and was invisible to every lookup
       that keys on the normalized column.

    Mirrors the trigger case for case; they must not disagree, or the API
    would echo one value while the DB stored another.
    """
    if "contato" not in payload:
        return payload

    raw = payload.get("contato")
    value = str(raw).strip() if raw is not None else ""

    if not value:
        return {**payload, "contato_norm": None, "contato_tipo": "desconhecido"}
    if "@" in value:
        return {**payload, "contato_norm": value.lower(), "contato_tipo": "email"}

    canonical = normalize_phone(value)
    if canonical:
        return {**payload, "contato_norm": canonical, "contato_tipo": "telefone"}
    # Looks like a phone but cannot be canonicalized without guessing: no
    # `contato_norm` (nothing may key on a guess), but the type still says what
    # it is, so a human filtering for phones can find and fix it.
    tipo = "telefone" if len(re.sub(r"\D", "", value)) >= 8 else "desconhecido"
    return {**payload, "contato_norm": None, "contato_tipo": tipo}


def create_lead(client: Any, org_id: UUID, payload: dict) -> dict:
    # `id`/`created_at` are explicit here (not left to a DB DEFAULT) so
    # the returned row is deterministic across the real Supabase client
    # AND `MockSupabaseClient` (whose auto-id is `mock-<table>-<n>`, not
    # a UUID — would break `LeadOut.id: UUID` validation). `ano`/`mes`
    # are deliberately NEVER in this payload: they're
    # `GENERATED ALWAYS AS (...) STORED` on real Postgres (§4) and an
    # explicit value there is a hard error — `backfill_generated_columns`
    # derives them at read time instead (mock parity only).
    row = {
        "id": str(uuid.uuid4()),
        "org_id": str(org_id),
        "needs_review": False,
        "tipo_lead": "desconhecido",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
    }
    row.update(_derive_contato_fields(_jsonify_payload(payload)))
    resp = _table(client, "leads").insert(row).execute()
    rows = list(resp.data or [])
    result = rows[0] if rows else row
    return backfill_generated_columns(result)


def get_lead(client: Any, org_id: UUID, lead_id: UUID) -> Optional[dict]:
    resp = (
        _table(client, "leads")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(lead_id))
        .execute()
    )
    rows = list(resp.data or [])
    return backfill_generated_columns(rows[0]) if rows else None


def update_lead(client: Any, org_id: UUID, lead_id: UUID, payload: dict) -> Optional[dict]:
    """The router calls this with ``body.model_dump(exclude_unset=True)``
    — a key's PRESENCE means the caller explicitly sent it. Unlike the
    previous ``is not None`` filter, an explicit ``null`` now genuinely
    CLEARS that field (e.g. un-assigning a corretor: ``{"corretor_id":
    null}``) instead of being silently dropped — the old behavior showed
    "Lead atualizado." with nothing actually changed, a false-success
    toast over a no-op write.

    ``data_entrada``/``tipo_lead``/``needs_review`` are ``NOT NULL`` on
    ``leads`` (migration 025) — an explicit null for one of those has no
    valid applied state and is ignored (dropped), same reasoning as
    ``dimensions_service.update_source``'s ``label``/``categoria``/etc.

    Setting ``origem_id`` to a non-null value auto-clears
    ``needs_review`` — its only cause is an unrecognized/blank origem
    (``importer.resolvers.resolve_origem``), so pointing a lead at a
    real source resolves the flag. This overrides any ``needs_review``
    ALSO present in the same payload (deliberately unconditional) so a
    bulk alias-mapping (``dimensions_service._relink_leads_by_origem``)
    clears the flag the exact same way a manual PATCH does.

    Every real write also stamps ``updated_at`` (previously never set —
    it stayed NULL forever) and ``edited_at``, a marker
    ``importer.import_service.commit`` checks before ever overwriting an
    existing row from a re-imported spreadsheet — see that module's
    docstring for the data-loss class this closes."""
    existing = get_lead(client, org_id, lead_id)
    if existing is None:
        return None
    clean = {
        k: v for k, v in payload.items()
        if not (v is None and k in _LEADS_NOT_NULLABLE_FIELDS)
    }
    if clean.get("origem_id") is not None and "origem_id" in clean:
        clean["needs_review"] = False
    if not clean:
        return existing
    clean = _derive_contato_fields(_jsonify_payload(clean))
    now = datetime.now(timezone.utc).isoformat()
    clean["updated_at"] = now
    clean["edited_at"] = now
    resp = _table(client, "leads").update(clean).eq("id", str(lead_id)).execute()
    rows = list(resp.data or [])
    result = rows[0] if rows else {**existing, **clean}
    return backfill_generated_columns(result)


def delete_lead(client: Any, org_id: UUID, lead_id: UUID) -> bool:
    existing = get_lead(client, org_id, lead_id)
    if existing is None:
        return False
    _table(client, "leads").delete().eq("id", str(lead_id)).execute()
    return True


def _sort_key(row: dict, sort: str, refs: dict):
    if sort == "origem":
        source = refs["sources_by_id"].get(row.get("origem_id"))
        return (source or {}).get("label") or ""
    if sort == "corretor":
        corretor = refs["corretores_by_id"].get(row.get("corretor_id"))
        return (corretor or {}).get("nome") or ""
    return row.get(sort) or ""


def _list_leads_db(
    client: Any,
    org_id: UUID,
    filters: LeadFilters,
    *,
    page: int,
    page_size: int,
    sort: str,
    order: str,
) -> tuple[list[dict], int]:
    """DB-pushed fast path — one ``count="exact"`` round-trip + one
    ``.order().range()`` round-trip for the page, instead of fetching
    every matching row. See the module docstring for the exact
    fallback conditions (never called for those)."""
    start = (page - 1) * page_size
    end = start + page_size - 1

    count_query = _table(client, "leads").select("id", count="exact").eq("org_id", str(org_id))
    count_query = apply_db_filters(count_query, filters)
    total = count_query.execute().count or 0

    page_query = _table(client, "leads").select("*").eq("org_id", str(org_id))
    page_query = apply_db_filters(page_query, filters)
    # `.order("id")` tiebreaker: `sort` alone has no stable ordering
    # guarantee across ties (~14 leads/day on `data_entrada` across
    # 12,177 rows makes ties the norm, not the exception) — without a
    # deterministic secondary key Postgres can return overlapping/missing
    # rows for the same tied group across two page requests, so the same
    # lead shows on page 3 AND page 4 while another never appears at all.
    # `id` is unique, so appending it as the secondary sort makes the
    # ordering total and every page request reproducible.
    page_query = (
        page_query.order(sort, desc=(order == "desc")).order("id").range(start, end)
    )
    rows = [backfill_generated_columns(r) for r in list(page_query.execute().data or [])]
    return rows, total


def list_leads(
    client: Any,
    org_id: UUID,
    filters: LeadFilters,
    *,
    page: int = 1,
    page_size: int = 50,
    sort: str = "data_entrada",
    order: str = "desc",
    refs: Optional[dict] = None,
) -> tuple[list[dict], int]:
    """Return ``(page_rows, total)``. Pushes count + page to Postgres for
    the common case (see the module docstring); falls back to the
    original filter-all-then-Python-sort-then-slice path (via
    ``fetch_filtered``) when the sort needs a joined label or any of
    ``q``/``ano``/``mes`` is set."""
    sort = sort if sort in _SORTABLE else "data_entrada"
    order = order if order in ("asc", "desc") else "desc"
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    needs_python_fallback = sort not in _DB_SORTABLE or filters.q or filters.ano or filters.mes
    if not needs_python_fallback:
        return _list_leads_db(
            client, org_id, filters, page=page, page_size=page_size, sort=sort, order=order
        )

    rows = fetch_filtered(client, org_id, filters)
    refs = refs or {"sources_by_id": {}, "corretores_by_id": {}}
    rows.sort(key=lambda r: _sort_key(r, sort, refs), reverse=(order == "desc"))

    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total


def _reference_facets(client: Any, org_id: UUID, filters: LeadFilters) -> dict:
    """Original Python implementation — kept as the equivalence oracle
    for ``social_wiring.leads_facets`` (migration 027). See
    ``analytics_service.py``'s module docstring for why this is
    retained rather than deleted."""
    rows = fetch_filtered(client, org_id, filters)
    emp_counts: dict[str, int] = {}
    reg_counts: dict[str, int] = {}
    anos: set[int] = set()
    for r in rows:
        if r.get("empreendimento"):
            emp_counts[r["empreendimento"]] = emp_counts.get(r["empreendimento"], 0) + 1
        if r.get("regiao"):
            reg_counts[r["regiao"]] = reg_counts.get(r["regiao"], 0) + 1
        if r.get("ano") is not None:
            anos.add(int(r["ano"]))

    def _sorted_items(counts: dict[str, int]) -> list[dict]:
        return [
            {"value": k, "count": v}
            for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    return {
        "empreendimentos": _sorted_items(emp_counts),
        "regioes": _sorted_items(reg_counts),
        "anos": sorted(anos),
    }


def facets(client: Any, org_id: UUID, filters: LeadFilters) -> dict:
    """SQL-side (§5.2 ``GET /api/leads/facets``) — one round-trip via
    ``social_wiring.leads_facets`` instead of a full ``fetch_filtered``."""
    params = to_rpc_params(org_id, filters)
    resp = client.rpc("leads_facets", params).execute()
    return resp.data or {"empreendimentos": [], "regioes": [], "anos": []}


def build_refs(client: Any, org_id: UUID) -> dict:
    """``{sources_by_id, corretores_by_id}`` — fetched once per request and
    threaded through list/sort/serialize so a page of N leads costs 2
    extra queries total, not 2*N."""
    from app.modules.leads.services import dimensions_service

    sources = {r["id"]: r for r in dimensions_service.list_sources(client, org_id)}
    corretores = {r["id"]: r for r in dimensions_service.list_corretores(client, org_id)}
    return {"sources_by_id": sources, "corretores_by_id": corretores}


def resolve_lead_out(row: dict, refs: dict) -> dict:
    """Attach the joined ``origem``/``corretor`` nested refs (§5.3) to a
    raw ``leads`` row dict, ready for ``LeadOut.model_validate``."""
    out = dict(row)
    source = refs["sources_by_id"].get(row.get("origem_id"))
    out["origem"] = (
        {"id": source["id"], "slug": source["slug"], "label": source["label"], "cor": source.get("cor")}
        if source
        else None
    )
    corretor = refs["corretores_by_id"].get(row.get("corretor_id"))
    out["corretor"] = (
        {"id": corretor["id"], "nome": corretor["nome"], "cor": corretor.get("cor")}
        if corretor
        else None
    )
    return out


__all__ = [
    "create_lead",
    "get_lead",
    "update_lead",
    "delete_lead",
    "list_leads",
    "facets",
    "_reference_facets",
    "build_refs",
    "resolve_lead_out",
]
