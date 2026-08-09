"""Value objects + the ``RecordStore`` Protocol for the persistence seam.

The seam exists so a product can develop against SQLite and later land on
Supabase/Postgres without rewriting its domain layer. It is deliberately
NARROW: a record store, not an ORM and not a query builder. Anything a
caller cannot express through :class:`QuerySpec` belongs in a
product-owned repository method that composes several store calls, or —
when the shape recurs across products — in a widening of this Protocol.

**Org scoping is not optional.** Every read and write carries an
``org_id``. On the Supabase/Postgres path RLS is the real enforcement and
this argument is belt-and-braces; on the SQLite path there IS no RLS, so
this argument IS the tenant boundary. Making it a required positional on
every method means a caller cannot forget it — the failure mode is a
``TypeError`` at import/call time, not a silent cross-tenant read.

See ``KB § PATTERNS/backend/seed-fake-real-adapter.md`` for the
Protocol+Fake+Real+factory shape this module implements, and
``KB § PATTERNS/architect/seed-lib-layout.md`` for why it lives under
``integrations/`` (it touches the DB) rather than ``domain/``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Record",
    "Op",
    "Filter",
    "Order",
    "QuerySpec",
    "RecordStore",
    "RecordNotFound",
    "PersistenceError",
]

#: A single row, as a plain dict. Deliberately not a TypedDict/model — the
#: store is schema-agnostic; typing happens in the product's repository
#: layer where the entity shape is actually known.
Record = dict[str, Any]


class PersistenceError(RuntimeError):
    """Base for every error this seam raises.

    Adapters translate backend-specific failures into this hierarchy so a
    caller never has to catch ``sqlite3.IntegrityError`` in one
    environment and ``postgrest.APIError`` in another — which is exactly
    the consumer-side fork the seam exists to prevent.
    """


class RecordNotFound(PersistenceError):
    """A single-record operation matched nothing.

    Raised by :meth:`RecordStore.get` and :meth:`RecordStore.update` when
    the id/org pair does not resolve. Never returned as ``None`` — a
    silent ``None`` is the "no silent errors" violation this platform
    forbids (``KB § 01-PHILOSOPHY.md``).
    """


class Op(str, Enum):
    """Comparison operators a :class:`Filter` may use.

    Kept to the set that every backend implements natively and
    identically. Adding a member obliges you to implement it in ALL
    adapters in the same commit — a half-implemented operator is the
    "Real uses a primitive the Fake doesn't run" trap.
    """

    EQ = "eq"
    NEQ = "neq"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    CONTAINS = "contains"  # case-insensitive substring match
    IS_NULL = "is_null"    # value is a bool: True → IS NULL, False → IS NOT NULL


@dataclass(frozen=True, slots=True)
class Filter:
    """One column predicate. Combined with AND by :class:`QuerySpec`.

    OR is intentionally absent: every OR the products needed so far was
    better expressed as two calls or a purpose-built repository method.
    Add it here only when a real consumer needs it, not speculatively.
    """

    column: str
    op: Op
    value: Any = None

    def __post_init__(self) -> None:
        if self.op is Op.IN and not isinstance(self.value, (list, tuple, set)):
            raise ValueError(f"Op.IN on {self.column!r} needs a sequence, got {type(self.value).__name__}")
        if self.op is Op.IS_NULL and not isinstance(self.value, bool):
            raise ValueError(f"Op.IS_NULL on {self.column!r} needs a bool, got {type(self.value).__name__}")


@dataclass(frozen=True, slots=True)
class Order:
    """Sort directive. ``descending`` mirrors Postgres' default NULLS LAST."""

    column: str
    descending: bool = False


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """Everything a list query can express in this seam.

    ``limit=None`` means "no limit" — adapters must not silently cap it.
    A silent cap reads as "that's all the data" when it isn't, which is
    the same class of lie as a lying loading state.
    """

    filters: tuple[Filter, ...] = ()
    order_by: tuple[Order, ...] = ()
    limit: int | None = None
    offset: int = 0
    columns: tuple[str, ...] = ()  # empty → all columns

    def with_filter(self, column: str, op: Op, value: Any = None) -> "QuerySpec":
        """Return a copy with one more AND-ed predicate."""
        return QuerySpec(
            filters=self.filters + (Filter(column, op, value),),
            order_by=self.order_by,
            limit=self.limit,
            offset=self.offset,
            columns=self.columns,
        )


@runtime_checkable
class RecordStore(Protocol):
    """The surface every persistence backend implements.

    Sync by design. The platform's existing Supabase access is sync
    (``supabase-py``) and is already called from inside async FastAPI
    handlers; an async Protocol here would make this seam the ONLY async
    data path and force every product repository to grow two shapes. If
    the platform later moves to an async DB client wholesale, this
    Protocol moves with it — one edit, one commit, all consumers.

    Implementations: :class:`~.fake_adapter.InMemoryRecordStore` (tests),
    :class:`~.sqlite_adapter.SqliteRecordStore` (local dev),
    :class:`~.supabase_adapter.SupabaseRecordStore` (Postgres/Supabase).
    """

    def insert(self, table: str, org_id: str, values: Record) -> Record:
        """Insert one row scoped to ``org_id``; return it as persisted.

        The returned record includes backend-generated columns (id,
        created_at), so callers never need a follow-up read.
        """
        ...

    def get(self, table: str, org_id: str, record_id: str) -> Record:
        """Return one row by id within ``org_id``.

        Raises :class:`RecordNotFound` when absent — including when the
        row exists under a DIFFERENT org, which must be indistinguishable
        from "does not exist" so the store can't be used as a probe for
        other tenants' ids.
        """
        ...

    def list(self, table: str, org_id: str, spec: QuerySpec | None = None) -> list[Record]:
        """Return every row in ``org_id`` matching ``spec`` (AND-ed)."""
        ...

    def update(self, table: str, org_id: str, record_id: str, values: Record) -> Record:
        """Patch one row within ``org_id``; return the updated record.

        Raises :class:`RecordNotFound` when the id/org pair misses.
        """
        ...

    def delete(self, table: str, org_id: str, record_id: str) -> bool:
        """Delete one row within ``org_id``. ``True`` iff a row was removed."""
        ...

    def count(self, table: str, org_id: str, spec: QuerySpec | None = None) -> int:
        """Number of rows in ``org_id`` matching ``spec``."""
        ...
