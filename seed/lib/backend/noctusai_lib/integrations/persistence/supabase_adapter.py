"""Supabase/PostgREST :class:`~.types.RecordStore`.

This adapter is what makes the seam worth having: a product developed
against :class:`~.sqlite_adapter.SqliteRecordStore` moves to Supabase by
changing which store the factory returns, not by rewriting its
repositories.

**Isolation differs from the SQLite path, deliberately.** Here the
``org_id`` predicate is defence-in-depth layered *on top of* RLS, which
is the real boundary. Passing a user-scoped client (rather than the
service-role one) is what activates those policies — see
``KB § PATTERNS/backend/database-rls.md``. The explicit filter stays so
that a service-role client used for an admin path still cannot
accidentally read across tenants.

The client is injected, never constructed here: ``create_database_module()``
already owns Supabase client construction for the platform, and building
a second one in this module would be exactly the duplicated-factory
divergence ``KB § 03-SEED-ARCHITECTURE.md § 4`` calls out.
"""
from __future__ import annotations

from typing import Any, Protocol

from .types import Op, PersistenceError, QuerySpec, Record, RecordNotFound, RecordStore

__all__ = ["SupabaseRecordStore", "SupabaseLike"]


class SupabaseLike(Protocol):
    """The slice of ``supabase.Client`` this adapter uses.

    Narrow on purpose — it keeps the seam testable without the SDK and
    documents exactly what a substitute must provide.
    """

    def table(self, name: str) -> Any: ...


#: PostgREST operator names, keyed by our operator enum. ``CONTAINS`` maps
#: to ``ilike`` (case-insensitive LIKE) to match the SQLite adapter's
#: ``LOWER(col) LIKE`` semantics rather than PostgREST's ``cs`` (array
#: containment), which is a different operation entirely.
_OP_METHOD: dict[Op, str] = {
    Op.EQ: "eq",
    Op.NEQ: "neq",
    Op.LT: "lt",
    Op.LTE: "lte",
    Op.GT: "gt",
    Op.GTE: "gte",
}


class SupabaseRecordStore:
    """A :class:`~.types.RecordStore` over a Supabase client."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    # ── query construction ──────────────────────────────────────────
    def _apply(self, query: Any, org_id: str, spec: QuerySpec) -> Any:
        query = query.eq("org_id", org_id)
        for f in spec.filters:
            if f.op is Op.IS_NULL:
                # PostgREST spells NOT NULL as the `not` modifier on `is`.
                query = query.is_(f.column, "null") if f.value else query.not_.is_(f.column, "null")
            elif f.op is Op.IN:
                values = list(f.value)
                if not values:
                    # PostgREST renders `in.()` as a syntax error; an empty
                    # set matches nothing, so encode that with a predicate
                    # that is always false rather than emitting bad SQL.
                    query = query.eq("id", "00000000-0000-0000-0000-000000000000").eq(
                        "id", "11111111-1111-1111-1111-111111111111"
                    )
                    continue
                query = query.in_(f.column, values)
            elif f.op is Op.CONTAINS:
                query = query.ilike(f.column, f"%{f.value}%")
            else:
                query = getattr(query, _OP_METHOD[f.op])(f.column, f.value)
        for order in spec.order_by:
            query = query.order(order.column, desc=order.descending)
        if spec.limit is not None:
            query = query.range(spec.offset, spec.offset + spec.limit - 1)
        elif spec.offset:
            # PostgREST needs an upper bound; a very large one is the
            # documented way to express "from offset to the end".
            query = query.range(spec.offset, spec.offset + 1_000_000)
        return query

    @staticmethod
    def _data(response: Any) -> list[Record]:
        data = getattr(response, "data", None)
        if data is None:
            raise PersistenceError(f"supabase response carried no data: {response!r}")
        return list(data)

    # ── RecordStore ─────────────────────────────────────────────────
    def insert(self, table: str, org_id: str, values: Record) -> Record:
        payload = dict(values)
        payload["org_id"] = org_id
        rows = self._data(self._client.table(table).insert(payload).execute())
        if not rows:
            raise PersistenceError(f"insert into {table} returned no row")
        return rows[0]

    def get(self, table: str, org_id: str, record_id: str) -> Record:
        rows = self._data(
            self._client.table(table).select("*").eq("id", record_id).eq("org_id", org_id).execute()
        )
        if not rows:
            raise RecordNotFound(f"{table}:{record_id} not found in org {org_id}")
        return rows[0]

    def list(self, table: str, org_id: str, spec: QuerySpec | None = None) -> list[Record]:
        spec = spec or QuerySpec()
        columns = ",".join(spec.columns) if spec.columns else "*"
        query = self._apply(self._client.table(table).select(columns), org_id, spec)
        return self._data(query.execute())

    def update(self, table: str, org_id: str, record_id: str, values: Record) -> Record:
        patch = {k: v for k, v in values.items() if k not in {"id", "org_id"}}
        if not patch:
            return self.get(table, org_id, record_id)
        rows = self._data(
            self._client.table(table)
            .update(patch)
            .eq("id", record_id)
            .eq("org_id", org_id)
            .execute()
        )
        if not rows:
            raise RecordNotFound(f"{table}:{record_id} not found in org {org_id}")
        return rows[0]

    def delete(self, table: str, org_id: str, record_id: str) -> bool:
        rows = self._data(
            self._client.table(table).delete().eq("id", record_id).eq("org_id", org_id).execute()
        )
        return bool(rows)

    def count(self, table: str, org_id: str, spec: QuerySpec | None = None) -> int:
        spec = spec or QuerySpec()
        # `select("id")` + len() rather than PostgREST's count header:
        # the header shape varies across supabase-py versions, and this
        # seam's contract is an int either way.
        query = self._apply(self._client.table(table).select("id"), org_id, spec)
        return len(self._data(query.execute()))

