"""`OrgTableStore` -- the org-scoped row store the metas / engagement organs are written against.

Protocol + Fake + Real + factory (`KB § PATTERNS/backend/seed-fake-real-adapter.md`). Rows are plain dicts keyed by
column. EVERY call names the `org_id` and the store filters on it, so an id from another org is indistinguishable from
a missing one (RLS is the floor, never the only check). Tables are addressed by their LOGICAL name; a :class:`TableSpec`
maps it to the prefixed physical table and declares the UNIQUE guards the DDL carries, so the Fake refuses exactly what
the database refuses (:class:`StoreConflict`) and the same suite runs against both stores.

Real is a thin PostgREST adapter: one call = one statement = one transaction (a multi-row `insert` is atomic).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, runtime_checkable
from uuid import uuid4

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

__all__ = [
    "FakeOrgTableStore",
    "OrgTableStore",
    "StoreConflict",
    "SupabaseOrgTableStore",
    "TableSpec",
    "UniqueKey",
    "make_org_table_store",
]


class StoreConflict(Exception):
    """A UNIQUE guard refused a write. `guard` is the unique index name (or the table when the driver hid it)."""

    def __init__(self, guard: str, table: str) -> None:
        super().__init__(f"unique violation on {table} ({guard})")
        self.guard = guard
        self.table = table


@dataclass(frozen=True)
class UniqueKey:
    """One UNIQUE index of a table: `name` (the DDL index name), the `columns`, and an optional partial `where`.

    `where(row) -> bool` mirrors the index predicate (`WHERE left_at IS NULL`); a column holding NULL never collides
    (SQL semantics) unless it is listed in `nulls_equal` (the DDL coalesces it to a sentinel).
    """

    name: str
    columns: tuple[str, ...]
    where: Optional[Callable[[Mapping[str, Any]], bool]] = None
    nulls_equal: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableSpec:
    """A logical table: physical `name`, whether it has `id` / `created_at` / `updated_at` defaults, its UNIQUE keys."""

    name: str
    unique: tuple[UniqueKey, ...] = ()
    has_id: bool = True
    timestamps: tuple[str, ...] = ("created_at", "updated_at")
    #: columns the DB defaults on insert when the caller omitted them (`{"active": True}`) -- mirrored by the Fake.
    defaults: Mapping[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@runtime_checkable
class OrgTableStore(Protocol):
    """Org-scoped row access. `select` filters: `eq` / `neq` / `gte` / `lte` / `in_` map `{column: value(s)}`, `is_null`
    lists columns that must be NULL, `not_null` those that must not; `order` is `[(column, descending)]`."""

    def insert(self, table: str, org_id: str, rows: Sequence[Mapping[str, Any]]) -> list[dict]: ...

    def get(self, table: str, org_id: str, row_id: str) -> Optional[dict]: ...

    def select(
        self,
        table: str,
        org_id: str,
        *,
        eq: Optional[Mapping[str, Any]] = None,
        neq: Optional[Mapping[str, Any]] = None,
        gte: Optional[Mapping[str, Any]] = None,
        lte: Optional[Mapping[str, Any]] = None,
        in_: Optional[Mapping[str, Sequence[Any]]] = None,
        is_null: Sequence[str] = (),
        not_null: Sequence[str] = (),
        order: Sequence[tuple[str, bool]] = (),
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def update(self, table: str, org_id: str, row_id: str, patch: Mapping[str, Any]) -> Optional[dict]: ...

    def delete(self, table: str, org_id: str, row_id: str) -> bool: ...


# -- Fake ------------------------------------------------------------------------------------------------------------


class FakeOrgTableStore:
    """In-memory store for dev + tests; refuses UNIQUE violations like the database (single process only)."""

    def __init__(self, specs: Mapping[str, TableSpec]) -> None:
        self._specs = dict(specs)
        self._rows: dict[str, list[dict]] = {name: [] for name in specs}

    def _spec(self, table: str) -> TableSpec:
        try:
            return self._specs[table]
        except KeyError:
            raise KeyError(f"unknown table {table!r}; declared: {sorted(self._specs)}") from None

    @staticmethod
    def _key(spec_key: UniqueKey, row: Mapping[str, Any]) -> Optional[tuple]:
        if spec_key.where is not None and not spec_key.where(row):
            return None
        out = []
        for col in spec_key.columns:
            value = row.get(col)
            if value is None and col not in spec_key.nulls_equal:
                return None  # a NULL never collides
            out.append(value)
        return tuple(out)

    def _check_unique(self, table: str, org_id: str, row: Mapping[str, Any], *, ignore_id: Optional[str] = None) -> None:
        spec = self._spec(table)
        for uk in spec.unique:
            mine = self._key(uk, row)
            if mine is None:
                continue
            for other in self._rows[table]:
                if other.get("org_id") != org_id or (ignore_id is not None and other.get("id") == ignore_id):
                    continue
                if self._key(uk, other) == mine:
                    raise StoreConflict(uk.name, spec.name)

    def insert(self, table: str, org_id: str, rows: Sequence[Mapping[str, Any]]) -> list[dict]:
        spec = self._spec(table)
        staged: list[dict] = []
        for raw in rows:
            row = {**spec.defaults, **raw, "org_id": str(org_id)}
            if spec.has_id and not row.get("id"):
                row["id"] = str(uuid4())
            for ts in spec.timestamps:
                row.setdefault(ts, _now_iso())
            # a multi-row insert is ONE transaction: check against the committed rows AND the rows staged before it
            self._check_unique(table, str(org_id), row)
            for earlier in staged:
                for uk in spec.unique:
                    key = self._key(uk, row)
                    if key is not None and key == self._key(uk, earlier):
                        raise StoreConflict(uk.name, spec.name)
            staged.append(row)
        self._rows[table].extend(staged)
        return [dict(r) for r in staged]

    def get(self, table: str, org_id: str, row_id: str) -> Optional[dict]:
        self._spec(table)
        for row in self._rows[table]:
            if row.get("org_id") == str(org_id) and row.get("id") == str(row_id):
                return dict(row)
        return None

    def select(
        self,
        table: str,
        org_id: str,
        *,
        eq: Optional[Mapping[str, Any]] = None,
        neq: Optional[Mapping[str, Any]] = None,
        gte: Optional[Mapping[str, Any]] = None,
        lte: Optional[Mapping[str, Any]] = None,
        in_: Optional[Mapping[str, Sequence[Any]]] = None,
        is_null: Sequence[str] = (),
        not_null: Sequence[str] = (),
        order: Sequence[tuple[str, bool]] = (),
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[dict]:
        self._spec(table)
        out = [dict(r) for r in self._rows[table] if r.get("org_id") == str(org_id)]
        for col, val in (eq or {}).items():
            out = [r for r in out if _same(r.get(col), val)]
        for col, val in (neq or {}).items():
            out = [r for r in out if not _same(r.get(col), val)]
        for col, val in (gte or {}).items():
            out = [r for r in out if r.get(col) is not None and _cmp(r[col]) >= _cmp(val)]
        for col, val in (lte or {}).items():
            out = [r for r in out if r.get(col) is not None and _cmp(r[col]) <= _cmp(val)]
        for col, vals in (in_ or {}).items():
            wanted = [str(v) for v in vals]
            out = [r for r in out if r.get(col) is not None and str(r[col]) in wanted]
        for col in is_null:
            out = [r for r in out if r.get(col) is None]
        for col in not_null:
            out = [r for r in out if r.get(col) is not None]
        for col, desc in reversed(list(order)):
            out.sort(key=lambda r, c=col: (r.get(c) is None, _cmp(r.get(c)) if r.get(c) is not None else 0), reverse=desc)
        if offset:
            out = out[offset:]
        if limit is not None:
            out = out[:limit]
        return out

    def update(self, table: str, org_id: str, row_id: str, patch: Mapping[str, Any]) -> Optional[dict]:
        spec = self._spec(table)
        for i, row in enumerate(self._rows[table]):
            if row.get("org_id") == str(org_id) and row.get("id") == str(row_id):
                new = {**row, **{k: v for k, v in patch.items() if k not in ("id", "org_id")}}
                if "updated_at" in spec.timestamps:
                    new["updated_at"] = _now_iso()
                self._check_unique(table, str(org_id), new, ignore_id=str(row_id))
                self._rows[table][i] = new
                return dict(new)
        return None

    def delete(self, table: str, org_id: str, row_id: str) -> bool:
        self._spec(table)
        before = len(self._rows[table])
        self._rows[table] = [
            r for r in self._rows[table] if not (r.get("org_id") == str(org_id) and r.get("id") == str(row_id))
        ]
        return len(self._rows[table]) < before

    def clear(self) -> None:
        for rows in self._rows.values():
            rows.clear()


def _cmp(value: Any) -> Any:
    """A comparable form: numbers numerically, everything else (ISO dates / timestamps / text) as text."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if isinstance(value, str) and value.replace(".", "", 1).lstrip("-").isdigit() else str(value)
    except ValueError:
        return str(value)


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    return str(a) == str(b) if not isinstance(a, (int, float, bool)) else _cmp(a) == _cmp(b)


# -- Real ------------------------------------------------------------------------------------------------------------


class SupabaseOrgTableStore:
    """The Real store over a SERVICE-ROLE PostgREST client (a schema-pinned `get_admin_client()` of the product, or a
    root client plus `schema=`). Every query is filtered by `org_id`."""

    def __init__(self, client: Any, specs: Mapping[str, TableSpec], *, schema: Optional[str] = None) -> None:
        self._client = client
        self._specs = dict(specs)
        self._schema = schema

    def _spec(self, table: str) -> TableSpec:
        try:
            return self._specs[table]
        except KeyError:
            raise KeyError(f"unknown table {table!r}; declared: {sorted(self._specs)}") from None

    def _t(self, table: str) -> Any:
        base = self._client.schema(self._schema) if self._schema else self._client
        return base.table(self._spec(table).name)

    @staticmethod
    def _rows(resp: Any) -> list[dict]:
        data = getattr(resp, "data", None)
        if isinstance(data, list):
            return [dict(r) for r in data]
        return [dict(data)] if isinstance(data, dict) else []

    def _conflict(self, table: str, exc: BaseException) -> StoreConflict:
        spec = self._spec(table)
        text = str(exc)
        guard = next((uk.name for uk in spec.unique if uk.name in text), spec.name)
        return StoreConflict(guard, spec.name)

    def insert(self, table: str, org_id: str, rows: Sequence[Mapping[str, Any]]) -> list[dict]:
        payload = [{**r, "org_id": str(org_id)} for r in rows]
        if not payload:
            return []
        try:
            return self._rows(self._t(table).insert(payload).execute())
        except Exception as exc:  # noqa: BLE001 - narrowed: only a unique violation is translated, the rest re-raises
            if is_unique_violation(exc):
                raise self._conflict(table, exc) from exc
            raise

    def get(self, table: str, org_id: str, row_id: str) -> Optional[dict]:
        rows = self._rows(self._t(table).select("*").eq("org_id", str(org_id)).eq("id", str(row_id)).limit(1).execute())
        return rows[0] if rows else None

    def select(
        self,
        table: str,
        org_id: str,
        *,
        eq: Optional[Mapping[str, Any]] = None,
        neq: Optional[Mapping[str, Any]] = None,
        gte: Optional[Mapping[str, Any]] = None,
        lte: Optional[Mapping[str, Any]] = None,
        in_: Optional[Mapping[str, Sequence[Any]]] = None,
        is_null: Sequence[str] = (),
        not_null: Sequence[str] = (),
        order: Sequence[tuple[str, bool]] = (),
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[dict]:
        q = self._t(table).select("*").eq("org_id", str(org_id))
        for col, val in (eq or {}).items():
            q = q.eq(col, val)
        for col, val in (neq or {}).items():
            q = q.neq(col, val)
        for col, val in (gte or {}).items():
            q = q.gte(col, val)
        for col, val in (lte or {}).items():
            q = q.lte(col, val)
        for col, vals in (in_ or {}).items():
            if not len(vals):
                return []  # `IN ()` matches nothing; PostgREST would reject the empty list
            q = q.in_(col, [str(v) for v in vals])
        for col in is_null:
            q = q.is_(col, "null")
        for col in not_null:
            q = q.not_.is_(col, "null")
        for col, desc in order:
            q = q.order(col, desc=desc)
        if limit is not None:
            q = q.range(offset, offset + limit - 1)
        elif offset:
            q = q.range(offset, offset + 10_000 - 1)
        return self._rows(q.execute())

    def update(self, table: str, org_id: str, row_id: str, patch: Mapping[str, Any]) -> Optional[dict]:
        body = {k: v for k, v in patch.items() if k not in ("id", "org_id")}
        if not body:
            return self.get(table, org_id, row_id)
        if "updated_at" in self._spec(table).timestamps:
            body["updated_at"] = _now_iso()  # no DB trigger: the store stamps it (the Fake does the same)
        try:
            rows = self._rows(self._t(table).update(body).eq("org_id", str(org_id)).eq("id", str(row_id)).execute())
        except Exception as exc:  # noqa: BLE001 - narrowed: only a unique violation is translated, the rest re-raises
            if is_unique_violation(exc):
                raise self._conflict(table, exc) from exc
            raise
        return rows[0] if rows else None

    def delete(self, table: str, org_id: str, row_id: str) -> bool:
        return bool(self._rows(self._t(table).delete().eq("org_id", str(org_id)).eq("id", str(row_id)).execute()))


def make_org_table_store(
    specs: Mapping[str, TableSpec],
    *,
    use_fake: bool = False,
    supabase_client: Any = None,
    schema: Optional[str] = None,
) -> OrgTableStore:
    """The fake store (`use_fake=True`) or the Supabase one. A missing client is a loud error, never a silent Fake."""
    if use_fake:
        return FakeOrgTableStore(specs)
    if supabase_client is None:
        raise RuntimeError("make_org_table_store: supabase_client is required when use_fake=False")
    return SupabaseOrgTableStore(supabase_client, specs, schema=schema)
