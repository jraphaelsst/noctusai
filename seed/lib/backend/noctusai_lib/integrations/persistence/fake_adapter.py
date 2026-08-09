"""Deterministic in-memory :class:`~.types.RecordStore` for tests.

Mirrors the observable behaviour of the real adapters — same org
scoping, same :class:`~.types.RecordNotFound` on a miss, same operator
semantics. When a real adapter and this Fake disagree, the Fake has a
bug worth fixing here; reaching for a real backend in tests is the
anti-pattern this module exists to remove
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``).

Deterministic on purpose: ids are sequential per table (``1``, ``2``, …)
rather than random UUIDs, so a test can assert on an id without
capturing it first, and a failure reproduces byte-for-byte.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from .types import Op, QuerySpec, Record, RecordNotFound, RecordStore

__all__ = ["InMemoryRecordStore", "matches"]


def _coerce(value: Any) -> Any:
    """Normalise a value for comparison.

    Ids arrive as ``str`` from HTTP and may be ``int`` in-memory; without
    this, ``get(table, org, "1")`` would miss a row stored with id ``1``
    and the Fake would diverge from SQLite (which is type-affine and
    matches across the two).
    """
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def matches(record: Record, filters: tuple, /) -> bool:
    """True iff ``record`` satisfies every filter (AND).

    Exposed because the SQLite adapter's tests reuse it as the
    independent oracle — if both the Fake and SQLite are checked against
    the same predicate definition, a divergence surfaces as a test
    failure rather than as production drift.
    """
    for f in filters:
        actual = record.get(f.column)
        if f.op is Op.IS_NULL:
            if (actual is None) != f.value:
                return False
            continue
        if f.op is Op.IN:
            if _coerce(actual) not in {_coerce(v) for v in f.value}:
                return False
            continue
        if f.op is Op.CONTAINS:
            if actual is None or str(f.value).lower() not in str(actual).lower():
                return False
            continue
        if actual is None:
            # NULL compares false to everything except IS NULL — matches
            # SQL three-valued logic, which the Postgres path enforces.
            return False
        if f.op is Op.EQ and _coerce(actual) != _coerce(f.value):
            return False
        if f.op is Op.NEQ and _coerce(actual) == _coerce(f.value):
            return False
        if f.op is Op.LT and not actual < f.value:
            return False
        if f.op is Op.LTE and not actual <= f.value:
            return False
        if f.op is Op.GT and not actual > f.value:
            return False
        if f.op is Op.GTE and not actual >= f.value:
            return False
    return True


class InMemoryRecordStore:
    """In-memory :class:`~.types.RecordStore`. Satisfies the Protocol.

    ``store.rows(table)`` exposes the raw contents for assertions — the
    bi-directional half of the Fake contract (records writes, accepts
    injected reads via :meth:`seed`).
    """

    def __init__(self, *, now: datetime | None = None) -> None:
        self._tables: dict[str, list[Record]] = {}
        self._counters: dict[str, int] = {}
        self._now = now

    # ── test affordances ────────────────────────────────────────────
    def rows(self, table: str) -> list[Record]:
        """Every row in ``table`` across all orgs (assertion helper)."""
        return copy.deepcopy(self._tables.get(table, []))

    def seed(self, table: str, records: list[Record]) -> None:
        """Inject rows directly, bypassing :meth:`insert`.

        For arranging read-path tests without exercising the write path.
        Rows must already carry ``id`` and ``org_id``.
        """
        for r in records:
            missing = {"id", "org_id"} - r.keys()
            if missing:
                raise ValueError(f"seeded row missing {sorted(missing)}: {r!r}")
        self._tables.setdefault(table, []).extend(copy.deepcopy(records))

    # ── RecordStore ─────────────────────────────────────────────────
    def _timestamp(self) -> str:
        return (self._now or datetime.now(timezone.utc)).isoformat()

    def insert(self, table: str, org_id: str, values: Record) -> Record:
        rows = self._tables.setdefault(table, [])
        self._counters[table] = self._counters.get(table, 0) + 1
        row = copy.deepcopy(values)
        row.setdefault("id", str(self._counters[table]))
        row["org_id"] = org_id
        row.setdefault("created_at", self._timestamp())
        rows.append(row)
        return copy.deepcopy(row)

    def _find(self, table: str, org_id: str, record_id: str) -> Record | None:
        for row in self._tables.get(table, []):
            if _coerce(row.get("id")) == _coerce(record_id) and row.get("org_id") == org_id:
                return row
        return None

    def get(self, table: str, org_id: str, record_id: str) -> Record:
        row = self._find(table, org_id, record_id)
        if row is None:
            raise RecordNotFound(f"{table}:{record_id} not found in org {org_id}")
        return copy.deepcopy(row)

    def list(self, table: str, org_id: str, spec: QuerySpec | None = None) -> list[Record]:
        spec = spec or QuerySpec()
        out = [
            copy.deepcopy(r)
            for r in self._tables.get(table, [])
            if r.get("org_id") == org_id and matches(r, spec.filters)
        ]
        for order in reversed(spec.order_by):
            # Stable sort applied right-to-left yields correct multi-key
            # ordering. `None` sorts last in both directions, mirroring
            # Postgres' NULLS LAST default.
            out.sort(
                key=lambda r, c=order.column: (r.get(c) is None, r.get(c)),
                reverse=order.descending,
            )
        out = out[spec.offset:]
        if spec.limit is not None:
            out = out[: spec.limit]
        if spec.columns:
            out = [{k: r.get(k) for k in spec.columns} for r in out]
        return out

    def update(self, table: str, org_id: str, record_id: str, values: Record) -> Record:
        row = self._find(table, org_id, record_id)
        if row is None:
            raise RecordNotFound(f"{table}:{record_id} not found in org {org_id}")
        for key, value in values.items():
            # id/org_id are structural — a patch may not move a row
            # between tenants or rewrite its identity.
            if key in {"id", "org_id"}:
                continue
            row[key] = value
        row["updated_at"] = self._timestamp()
        return copy.deepcopy(row)

    def delete(self, table: str, org_id: str, record_id: str) -> bool:
        rows = self._tables.get(table, [])
        for i, row in enumerate(rows):
            if _coerce(row.get("id")) == _coerce(record_id) and row.get("org_id") == org_id:
                rows.pop(i)
                return True
        return False

    def count(self, table: str, org_id: str, spec: QuerySpec | None = None) -> int:
        spec = spec or QuerySpec()
        return sum(
            1
            for r in self._tables.get(table, [])
            if r.get("org_id") == org_id and matches(r, spec.filters)
        )

