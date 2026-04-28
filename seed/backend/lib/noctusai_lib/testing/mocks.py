"""
Mock Supabase builders that mirror the real postgrest SDK hierarchy.

Builder hierarchy (postgrest 0.17.2):
  table(name)        → MockRequestBuilder
    .select(...)     → MockSelectBuilder   (filters, order, limit, range, single, execute)
    .insert(...)     → MockQueryBuilder    (execute only)
    .update(...)     → MockFilterBuilder   (filters, execute)
    .delete()        → MockFilterBuilder
    .upsert(...)     → MockFilterBuilder

All builders support optional response queues for sequential test scenarios.

Schema validation (opt-in, from `MockSupabaseClient(validate_schema=True)`):
  .eq/.neq/.in_/... and .select("col1,col2") and .insert({col: val}) etc.
  consult the migration-file-derived schema cache and raise `MockSchemaError`
  if a referenced column does not exist on the bound table. Closes the
  compliance-audit silent-fail class (`projects/mock-supabase-schema-validation`).
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional
from unittest.mock import MagicMock

from noctusai_lib.testing._schema_cache import get_schema_map
from noctusai_lib.testing.schema_errors import MockSchemaError, MockUnknownTableError


class MockSupabaseResponse:
    """Simulates a Supabase PostgREST response."""

    def __init__(self, data=None, error=None, count=None):
        self.data = data or []
        self.error = error
        self.count = count


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------


def _resolve_table_entry(
    schema: Optional[str], table: Optional[str]
) -> tuple[Optional[str], Optional[set[str]]]:
    """Look up `<schema>.<table>` in the cache. Returns (qualified_name, cols).

    If the table is missing from the cache, returns (qualified_name, None)
    to signal "unknown — skip validation, don't raise" (Q4 WARN+skip).
    """
    if not table:
        return None, None
    cache = get_schema_map()
    if not cache:
        return None, None
    qualified = f"{(schema or 'public').lower()}.{table.lower()}"
    return qualified, cache.get(qualified)


def _validate_column(
    schema: Optional[str],
    table: Optional[str],
    column: str,
    operation: str,
    *,
    strict_unknown_tables: bool = False,
) -> None:
    """Raise MockSchemaError if column is not in the cached schema for this table.

    Silently returns if validation is disabled (schema/table missing). If
    the table is unknown to the cache and `strict_unknown_tables=False`,
    returns silently (Q4 WARN+skip default). If `strict_unknown_tables=True`
    (Tier 1.5 G4 opt-in), raises `MockUnknownTableError` instead.
    """
    if not schema and not table:
        return
    qualified, cols = _resolve_table_entry(schema, table)
    if cols is None:
        if strict_unknown_tables:
            raise MockUnknownTableError(
                schema=schema or "public",
                table=table or "",
                operation=operation,
            )
        return  # Unknown table → WARN+skip per Q4 default.
    if column not in cols:
        raise MockSchemaError(
            schema=schema or "public",
            table=table or "",
            invalid_column=column,
            valid_columns=cols,
            operation=operation,
        )


def _validate_select_cols(
    schema: Optional[str],
    table: Optional[str],
    cols_expr: str,
    *,
    strict_unknown_tables: bool = False,
) -> None:
    """Validate a select-columns expression.

    Accepted shapes:
      - "*"                                    (star — always OK)
      - "id, name, email"                      (column list)
      - "id, name, alias:other_col"            (aliased)
      - "*, products(*)"                       (star + PostgREST join — bail on any `(` or `!`)

    PostgREST-joined selects have complex shapes; the presence of any `(` or
    `!` anywhere in the expression means we bail (no false positives) rather
    than try to parse the join structure.
    """
    if cols_expr.strip() == "*" or not cols_expr.strip():
        # Even for `*`, strict mode wants to know if the table itself exists.
        if strict_unknown_tables:
            _validate_column(
                schema, table, "*", operation="select",
                strict_unknown_tables=True,
            ) if False else None  # noqa — see below
            qualified, cols = _resolve_table_entry(schema, table)
            if cols is None:
                raise MockUnknownTableError(
                    schema=schema or "public", table=table or "",
                    operation="select",
                )
        return
    # If the expression contains a PostgREST join (`(` or `!`), skip validation
    # wholesale — we'd be guessing the shape.
    if "(" in cols_expr or "!" in cols_expr:
        return
    for part in cols_expr.split(","):
        col = part.strip()
        if not col or col == "*":
            continue
        # Strip alias (e.g. "id:uuid")
        col = col.split(":", 1)[0].strip()
        _validate_column(
            schema, table, col, operation="select",
            strict_unknown_tables=strict_unknown_tables,
        )


def _validate_payload_keys(
    schema: Optional[str],
    table: Optional[str],
    payload,
    operation: str,
    *,
    strict_unknown_tables: bool = False,
) -> None:
    """Validate every key in an insert/update/upsert payload."""
    if payload is None:
        return
    # Supabase accepts dict (single row) or list[dict] (batch).
    if isinstance(payload, Mapping):
        rows = [payload]
    elif isinstance(payload, (list, tuple)):
        rows = [r for r in payload if isinstance(r, Mapping)]
    else:
        return
    for row in rows:
        for key in row.keys():
            _validate_column(
                schema, table, str(key), operation=operation,
                strict_unknown_tables=strict_unknown_tables,
            )


# ---------------------------------------------------------------------------
# Base mixin with shared execute logic
# ---------------------------------------------------------------------------

class _MockExecuteMixin:
    """Shared execute() logic for all builder types."""

    _data: list
    _single_mode: bool
    _count: Optional[int]
    _response_queue: Optional[list]
    _response_idx: Optional[list]

    def _do_execute(self):
        if self._response_queue is not None:
            idx = self._response_idx[0]
            self._response_idx[0] += 1
            if idx < len(self._response_queue):
                resp = self._response_queue[idx]
            else:
                resp = MockSupabaseResponse(data=[])
            # Apply single-mode unwrapping to queued responses too
            if self._single_mode and isinstance(resp.data, list):
                resp = MockSupabaseResponse(
                    data=resp.data[0] if resp.data else None,
                    error=resp.error,
                    count=resp.count,
                )
            self._single_mode = False
            return resp

        data = self._data
        if self._single_mode and isinstance(data, list):
            data = data[0] if data else None
        self._single_mode = False
        return MockSupabaseResponse(data=data, count=self._count)


# ---------------------------------------------------------------------------
# Filter methods mixin (DRY — used by SelectBuilder and FilterBuilder)
# ---------------------------------------------------------------------------

class _FilterMixin:
    """All PostgREST filter methods. Returns self for chaining.

    When `_validate_schema` is True and `_table` is set, column-arg filter
    methods consult the schema cache and raise `MockSchemaError` on unknowns.
    `_strict_unknown_tables` flips unknown-table behavior from WARN+skip to
    raise (Tier 1.5 G4).
    """

    _validate_schema: bool = False
    _strict_unknown_tables: bool = False
    _schema: Optional[str] = None
    _table: Optional[str] = None

    def _check_col(self, col: str, op: str) -> None:
        if self._validate_schema:
            _validate_column(
                self._schema, self._table, col, operation=op,
                strict_unknown_tables=self._strict_unknown_tables,
            )

    def eq(self, col, *a, **k):
        self._check_col(col, "eq")
        return self

    def neq(self, col, *a, **k):
        self._check_col(col, "neq")
        return self

    def in_(self, col, *a, **k):
        self._check_col(col, "in_")
        return self

    def gt(self, col, *a, **k):
        self._check_col(col, "gt")
        return self

    def lt(self, col, *a, **k):
        self._check_col(col, "lt")
        return self

    def gte(self, col, *a, **k):
        self._check_col(col, "gte")
        return self

    def lte(self, col, *a, **k):
        self._check_col(col, "lte")
        return self

    def ilike(self, col, *a, **k):
        self._check_col(col, "ilike")
        return self

    def like(self, col, *a, **k):
        self._check_col(col, "like")
        return self

    def is_(self, col, *a, **k):
        self._check_col(col, "is_")
        return self

    def contains(self, col, *a, **k):
        self._check_col(col, "contains")
        return self

    def contained_by(self, col, *a, **k):
        self._check_col(col, "contained_by")
        return self

    def overlaps(self, col, *a, **k):
        self._check_col(col, "overlaps")
        return self

    def fts(self, col, *a, **k):
        self._check_col(col, "fts")
        return self

    def text_search(self, col, *a, **k):
        self._check_col(col, "text_search")
        return self

    def filter(self, col, *a, **k):
        self._check_col(col, "filter")
        return self

    def match(self, query, *a, **k):
        if self._validate_schema and isinstance(query, Mapping):
            for key in query.keys():
                _validate_column(
                    self._schema, self._table, str(key), operation="match",
                    strict_unknown_tables=self._strict_unknown_tables,
                )
        return self

    def or_(self, *a, **k):
        # PostgREST expression like "status.eq.active,tier.gte.3" — skip
        # validation (Q4-style: don't false-positive on complex expressions;
        # adding a PostgREST-expression parser is out of scope per project §4).
        return self

    @property
    def not_(self):
        return self


# ---------------------------------------------------------------------------
# MockSelectBuilder — returned by .select()
# ---------------------------------------------------------------------------

class MockSelectBuilder(_FilterMixin, _MockExecuteMixin):
    """Mirrors SyncSelectRequestBuilder."""

    def __init__(
        self,
        data=None,
        count=None,
        response_queue=None,
        response_idx=None,
        *,
        validate_schema: bool = False,
        schema: Optional[str] = None,
        table: Optional[str] = None,
        strict_unknown_tables: bool = False,
    ):
        self._data = data or []
        self._single_mode = False
        self._count = count
        self._response_queue = response_queue
        self._response_idx = response_idx
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables

    def order(self, col, *a, **k):
        self._check_col(col, "order")
        return self

    def limit(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def offset(self, *a, **k):
        return self

    def single(self):
        self._single_mode = True
        return self

    def maybe_single(self):
        self._single_mode = True
        return self

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockFilterBuilder — returned by .update() / .delete()
# ---------------------------------------------------------------------------

class MockFilterBuilder(_FilterMixin, _MockExecuteMixin):
    """Mirrors SyncFilterRequestBuilder."""

    def __init__(
        self,
        data=None,
        response_queue=None,
        response_idx=None,
        *,
        validate_schema: bool = False,
        schema: Optional[str] = None,
        table: Optional[str] = None,
        strict_unknown_tables: bool = False,
    ):
        self._data = data or []
        self._single_mode = False
        self._count = None
        self._response_queue = response_queue
        self._response_idx = response_idx
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockQueryBuilder — returned by .insert() / .upsert()
# ---------------------------------------------------------------------------

class MockQueryBuilder(_MockExecuteMixin):
    """Mirrors SyncQueryRequestBuilder."""

    def __init__(
        self,
        data=None,
        response_queue=None,
        response_idx=None,
        *,
        validate_schema: bool = False,
        schema: Optional[str] = None,
        table: Optional[str] = None,
        strict_unknown_tables: bool = False,
    ):
        self._data = data or []
        self._single_mode = False
        self._count = None
        self._response_queue = response_queue
        self._response_idx = response_idx
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockRequestBuilder — returned by .table()
# ---------------------------------------------------------------------------

class MockRequestBuilder:
    """Mirrors SyncRequestBuilder — the object returned by .table(name).

    Tracks every `insert(...)` payload in `inserted_payloads` so tests can
    assert write side-effects without patching the production helper that
    issues the insert. Use `db.table("notifications").inserted_payloads`
    to read back what was inserted during the run. List-payloads are
    flattened (each row appended individually).
    """

    def __init__(
        self,
        data=None,
        *,
        validate_schema: bool = False,
        schema: Optional[str] = None,
        table: Optional[str] = None,
        strict_unknown_tables: bool = False,
    ):
        self.inserted_payloads: list = []
        self._data = data or []
        if isinstance(self._data, dict):
            self._data = [self._data]
        self._response_queue = None
        self._response_idx = None
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables

    def set_responses(self, responses):
        """Configure sequential responses for this table."""
        self._response_queue = responses
        self._response_idx = [0]

    def _builder_kwargs(self) -> dict:
        return {
            "validate_schema": self._validate_schema,
            "schema": self._schema,
            "table": self._table,
            "strict_unknown_tables": self._strict_unknown_tables,
        }

    def select(self, cols="*", *a, **k):
        if self._validate_schema and isinstance(cols, str):
            _validate_select_cols(
                self._schema, self._table, cols,
                strict_unknown_tables=self._strict_unknown_tables,
            )
        count = k.get("count")
        return MockSelectBuilder(
            self._data,
            count=len(self._data) if count == "exact" else None,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def insert(self, data=None, *a, **k):
        if self._validate_schema:
            _validate_payload_keys(
                self._schema, self._table, data, operation="insert",
                strict_unknown_tables=self._strict_unknown_tables,
            )
        if isinstance(data, list):
            self.inserted_payloads.extend(data)
        elif data is not None:
            self.inserted_payloads.append(data)
        return MockQueryBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def update(self, data=None, *a, **k):
        if self._validate_schema:
            _validate_payload_keys(
                self._schema, self._table, data, operation="update",
                strict_unknown_tables=self._strict_unknown_tables,
            )
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def upsert(self, data=None, *a, **k):
        if self._validate_schema:
            _validate_payload_keys(
                self._schema, self._table, data, operation="upsert",
                strict_unknown_tables=self._strict_unknown_tables,
            )
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def delete(self, *a, **k):
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )


# ---------------------------------------------------------------------------
# MockSupabaseClient
# ---------------------------------------------------------------------------

class MockSupabaseClient:
    """Mocked Supabase client with per-table data control and response queues.

    Args:
        data: default row data returned by every table's builders.
        validate_schema: when True, mock filter/select/insert/update/upsert
            calls consult the migration-file-derived schema cache and raise
            `MockSchemaError` on unknown columns. Opt-in during rollout
            (`projects/mock-supabase-schema-validation` Phase 3); flips to
            default-True in Phase 4.
        schema: the PostgREST schema to bind to (for `.schema(name).from_(...)`
            chains). Defaults to `public`.
    """

    def __init__(
        self,
        data=None,
        *,
        validate_schema: bool = True,
        schema: Optional[str] = "public",
        strict_unknown_tables: bool = False,
    ):
        self._data = data
        self.auth = MagicMock()
        self.storage = MagicMock()
        self._tables: dict[str, MockRequestBuilder] = {}
        self._rpcs: dict = {}
        self._validate_schema = validate_schema
        self._schema = schema
        self._strict_unknown_tables = strict_unknown_tables

    def _builder_for(self, name: str, data=None) -> MockRequestBuilder:
        # If the caller passes "schema.table", split it; otherwise use bound schema.
        if "." in name:
            schema, table = name.split(".", 1)
        else:
            schema, table = self._schema, name
        payload = data if data is not None else self._data
        return MockRequestBuilder(
            payload,
            validate_schema=self._validate_schema,
            schema=schema,
            table=table,
            strict_unknown_tables=self._strict_unknown_tables,
        )

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = self._builder_for(name)
        return self._tables[name]

    def from_(self, name):
        """Supabase .from_(name) alias for .table(name)."""
        return self.table(name)

    def schema(self, name: str) -> "MockSupabaseClient":
        """Return a client bound to a different schema."""
        scoped = MockSupabaseClient(
            self._data,
            validate_schema=self._validate_schema,
            schema=name,
            strict_unknown_tables=self._strict_unknown_tables,
        )
        scoped.auth = self.auth
        scoped.storage = self.storage
        scoped._rpcs = self._rpcs
        return scoped

    def set_table_data(self, name, data):
        """Set mock data for a specific table."""
        self._tables[name] = self._builder_for(name, data=data)

    def set_sequential_responses(self, table_name, responses):
        """Configure a table to return sequential responses on each execute()."""
        builder = self.table(table_name)
        builder.set_responses(responses)

    def set_rpc_data(self, name, data):
        """Set mock data for an RPC call."""
        self._rpcs[name] = data

    def rpc(self, name, params=None):
        """Simulate an RPC call."""
        data = self._rpcs.get(name, [])
        return MockSelectBuilder(data)
