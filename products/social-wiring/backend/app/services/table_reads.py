"""Org-scoped PostgREST reads + actor-name resolution — the canonical copies.

WHY THIS MODULE EXISTS (N=3, FORMALIZED)
----------------------------------------
Four helpers kept being re-answered per module:

- `batched` — PostgREST rides `in_()` values in the URL query string, so an
  unbatched ~1 000-item id list is a bare 400.
- `paged_rows` — PostgREST caps a response at 1 000 rows, so any unbounded
  read must page.
- `resolve_actors` / `actor` — a user id means nothing on a screen; the name
  lives in `public.noctus_users`, behind a DIFFERENT schema client.

`clientes_service` wrote `_batched` first. `card_hub/services` copied it, and
said so in its own docstring — "this module keeps its own copy rather than
importing that module's private helper". A third consumer (`imovel_hub`,
which lists an imóvel's documents and resolves its captador) is what the DRY
rule calls the point where copying stops being a judgement call.

🔴 WHY THESE PARTICULAR HELPERS ARE WORTH CENTRALISING, AND NOT OTHERS
----------------------------------------------------------------------
Not because they are repeated — plenty of two-line shapes are, harmlessly.
Because **their bodies are not what they look like.** Each one's real content
is a defence against a limit that is invisible at the call site: a URL length
nobody measures, a row cap that only bites past 1 000 rows, a pager that
never terminates if the backend ignores `range()`. A copy that drops the
batching, or pages without an `id_key`, is indistinguishable from a correct
one in every test with a small fixture — and wrong in production only once
the data grows.

That is the failure mode centralisation actually prevents here. Correctness
that is invisible until scale is exactly the correctness that must have one
home.

MIGRATION POSTURE — LOSSLESS, NOT A SWEEP
-----------------------------------------
The existing consumers keep their private names as thin aliases over these
(`_t = table`, `_batched = batched`, …), so all 47 existing call sites are
untouched and this commit carries no behavioural risk. New code imports the
public names directly. The aliases are not deprecated debt to chase — they
are the module's own vocabulary, now backed by one definition instead of
several.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

# The paged/batched reads are the SEED's (one definition): the fork here drifted into the 2026-11-23 Esteira 500,
# where a narrowed select dropped the pager's key. The seed's copy projects the key itself (``with_key_columns``).
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows, with_key_columns  # noqa: F401

from app.dependencies import get_core_client

#: PostgREST's response row cap. Reads page in chunks of this size.
PAGE_SIZE = 1000

#: Max ids per `in_()` filter. PostgREST puts them in the URL query string,
#: and an over-long request line comes back as a bare 400 with no hint that
#: length was the problem.
IN_FILTER_BATCH = 200


def table(client: Any, name: str):
    """The query builder for `name` on an already schema-scoped client."""
    return client.table(name)


def batched(items: list, size: int = IN_FILTER_BATCH) -> Iterator[list]:
    """Yield `items` in chunks of `size` — see `IN_FILTER_BATCH`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def resolve_actors(ids: set) -> dict[str, dict]:
    """`{id, nome}` for every id in `ids`, resolved against
    `public.noctus_users` (the trusted user table — see
    `app.dependencies.get_core_client`'s docstring for why this is the
    `public`-schema client, not `social_wiring`).

    Missing users fall back to `{"id": id, "nome": None}` — a stale/foreign
    id is not an error here, just an unresolved name.
    """
    clean_ids = {str(i) for i in ids if i}
    if not clean_ids:
        return {}
    core = get_core_client()
    out: dict[str, dict] = {}
    for batch in batched(sorted(clean_ids)):
        rows = (
            core.table("noctus_users")
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


def actor(resolved: dict[str, dict], raw_id: Optional[str]) -> Optional[dict]:
    """One `{id, nome}` out of a `resolve_actors` map, or `None` for no id."""
    if not raw_id:
        return None
    return resolved.get(str(raw_id)) or {"id": raw_id, "nome": None}


__all__ = [
    "IN_FILTER_BATCH",
    "PAGE_SIZE",
    "actor",
    "batched",
    "in_batched_rows",
    "paged_rows",
    "resolve_actors",
    "table",
]
