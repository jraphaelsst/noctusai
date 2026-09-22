"""Org-scoped PostgREST reads + actor-name resolution — the seed's copies.

Lifted from ``products/social-wiring/backend/app/services/table_reads.py``
(the N=3 formalization there: ``clientes_service`` → ``card_hub`` →
``imovel_hub``) when ``noctusai_lib.domain.card_hub`` became a fourth,
cross-product consumer. A MOVE, not a rewrite: the bodies are verbatim; the
one signature change is that :func:`resolve_actors` now takes the core
(``public``-schema) client as an argument instead of reaching for a
product-level ``get_core_client()`` the seed cannot import.

🔴 WHY THESE PARTICULAR HELPERS ARE WORTH ONE HOME
-------------------------------------------------
Not because they are repeated — because **their bodies are not what they
look like.** Each one's real content is a defence against a limit that is
invisible at the call site:

- :func:`batched` — PostgREST rides ``in_()`` values in the URL query string,
  so an unbatched ~1 000-item id list is a bare 400.
- :func:`paged_rows` — PostgREST caps a response at 1 000 rows, so any
  unbounded read must page (composes :func:`iter_paged_rows`, which also
  refuses to spin when the backend ignores ``range()``).
- :func:`in_batched_rows` — both hazards at once.
- :func:`resolve_actors` / :func:`actor` — a user id means nothing on a
  screen; the name lives in ``public.noctus_users``, behind a DIFFERENT
  schema client than the product's.

A copy that drops the batching, or pages without an ``id_key``, is
indistinguishable from a correct one in every test with a small fixture —
and wrong in production only once the data grows.

All of these operate on an ALREADY schema-scoped PostgREST client (the same
``db`` seam ``noctusai_lib.domain.pipeline`` uses). ``KB §
PATTERNS/backend/postgrest-row-cap.md``.
"""
from __future__ import annotations

from typing import Any, Callable, Iterator, Optional
from uuid import UUID

from .paging import iter_paged_rows

#: PostgREST's response row cap. Reads page in chunks of this size.
PAGE_SIZE = 1000

#: Max ids per ``in_()`` filter. PostgREST puts them in the URL query string,
#: and an over-long request line comes back as a bare 400 with no hint that
#: length was the problem.
IN_FILTER_BATCH = 200

#: ``ids -> {id: {"id", "nome"}}`` — see :func:`resolve_actors`.
ActorResolver = Callable[[set], dict]


def table(client: Any, name: str):
    """The query builder for ``name`` on an already schema-scoped client."""
    return client.table(name)


def batched(items: list, size: int = IN_FILTER_BATCH) -> Iterator[list]:
    """Yield ``items`` in chunks of ``size`` — see :data:`IN_FILTER_BATCH`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def paged_rows(
    client: Any,
    table_name: str,
    org_id: UUID,
    *,
    eq_filters: Optional[dict] = None,
    order_col: str = "id",
    id_key: str = "id",
    refine: Optional[Any] = None,
    select: str = "*",
) -> list[dict]:
    """Every row of ``table_name`` for ``org_id`` (+ ``eq_filters``), paged
    past PostgREST's row cap via the seed's shared pager.

    ``refine``, when given, is ``fn(query) -> query`` applied AFTER the eq
    filters and BEFORE ``.order()`` — for filter shapes ``eq_filters`` cannot
    express (e.g. ``.is_("deleted_at", "null")``).

    ``select`` overrides the default ``"*"`` for a read that needs embedded
    resources (a PostgREST join).

    Named ``refine``, NOT ``extra``: bandit's B610 flags any call to something
    named ``extra(...)`` as Django's ``QuerySet.extra()``. No SQL string exists
    here, but the check matches on the NAME; renaming is the honest fix, a
    ``# nosec`` would teach the next person to reach for suppression first.
    """
    eq_filters = eq_filters or {}

    def fetch_page(start: int, end: int):
        query = table(client, table_name).select(select).eq("org_id", str(org_id))
        for key, value in eq_filters.items():
            query = query.eq(key, value)
        if refine is not None:
            query = refine(query)
        return query.order(order_col).range(start, end).execute().data

    return list(
        iter_paged_rows(
            fetch_page,
            page_size=PAGE_SIZE,
            id_key=id_key,
            label=f"{table_name} for org_id={org_id}",
        )
    )


def in_batched_rows(
    client: Any,
    table_name: str,
    org_id: UUID,
    in_col: str,
    ids: list[str],
    *,
    select: str = "*",
    order_col: str = "id",
) -> list[dict]:
    """Every row of ``table_name`` matching ``in_col IN ids``, batched
    (URL-length safety) AND paged (row-cap safety).

    ``order_col`` exists because the pager needs a STABLE sort and ``id`` is
    only the usual name for it, not a universal one (a table keyed on
    ``atendimento_id`` has no ``id`` column). Paging without a deterministic
    order silently repeats and skips rows across pages.
    """
    if not ids:
        return []
    out: list[dict] = []
    for batch in batched(sorted(set(ids))):

        def fetch_page(start: int, end: int, _batch=batch):
            return (
                table(client, table_name)
                .select(select)
                .eq("org_id", str(org_id))
                .in_(in_col, _batch)
                .order(order_col)
                .range(start, end)
                .execute()
                .data
            )

        out.extend(
            iter_paged_rows(
                fetch_page,
                page_size=PAGE_SIZE,
                # The sort column IS the dedupe key — the pager's progress
                # guard needs a per-row identity, and the only column
                # guaranteed present is the one we ordered by.
                id_key=order_col,
                label=f"{table_name}.{in_col} batch for org_id={org_id}",
            )
        )
    return out


def resolve_actors(core_client: Any, ids: set) -> dict[str, dict]:
    """``{id, nome}`` for every id in ``ids``, resolved against
    ``public.noctus_users`` (the trusted user table) through ``core_client``
    — the ``public``-schema client, never the product-schema one.

    Missing users fall back to ``{"id": id, "nome": None}`` via :func:`actor`
    — a stale/foreign id is not an error here, just an unresolved name.
    """
    clean_ids = {str(i) for i in ids if i}
    if not clean_ids:
        return {}
    out: dict[str, dict] = {}
    for batch in batched(sorted(clean_ids)):
        rows = (
            core_client.table("noctus_users")
            .select("id,nome,email")
            .in_("id", batch)
            .execute()
            .data
            or []
        )
        for row in rows:
            out[str(row["id"])] = {
                "id": row["id"],
                "nome": row.get("nome") or row.get("email"),
            }
    return out


def actor_resolver(get_core_client: Callable[[], Any]) -> ActorResolver:
    """Bind :func:`resolve_actors` to a product's core-client accessor.

    The accessor is called PER RESOLUTION, never captured at construction —
    so a test's patched/overridden core client is seen, and a process that
    constructs its config at import time does not freeze a client instance.
    """

    def _resolve(ids: set) -> dict[str, dict]:
        return resolve_actors(get_core_client(), ids)

    return _resolve


def actor(resolved: dict[str, dict], raw_id: Optional[str]) -> Optional[dict]:
    """One ``{id, nome}`` out of a :func:`resolve_actors` map, or ``None``."""
    if not raw_id:
        return None
    return resolved.get(str(raw_id)) or {"id": raw_id, "nome": None}


__all__ = [
    "ActorResolver",
    "IN_FILTER_BATCH",
    "PAGE_SIZE",
    "actor",
    "actor_resolver",
    "batched",
    "in_batched_rows",
    "paged_rows",
    "resolve_actors",
    "table",
]
