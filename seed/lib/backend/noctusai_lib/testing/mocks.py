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

Write-to-read propagation (added 2026-05-10):
  INSERT/UPDATE/DELETE on a `MockRequestBuilder` mutate the table's shared
  in-memory rows so subsequent SELECT calls on the same builder reflect the
  write — closes the gap surfaced N=4 in AdConnect MVP. The rules:
    - INSERT appends response rows (with auto-id) to the shared list.
    - UPDATE evaluates accumulated filter predicates and `dict.update`s each
      matching row in place. Returns the mutated rows in `response.data`.
    - DELETE evaluates accumulated filter predicates and removes each
      matching row in place. Returns the deleted rows in `response.data`.
    - SELECT evaluates accumulated filter predicates and returns only matching
      rows in `response.data`. Empty predicate list = match-all. Added
      2026-05-11 (closes the SELECT-side gap surfaced by the UPDATE/DELETE
      filter-wiring; before the fix, `.select().eq(...).execute()` returned
      ALL seeded rows regardless of predicates, masking ~43 latent test bugs
      across 7 products).
    - When `set_sequential_responses(...)` is configured for the table, the
      queue dictates the response AND propagation / predicate-filtering is
      suppressed (lets tests simulate insert failures without implicit data
      seeding).
    - Filter ops with simple equality/membership/comparison/string-pattern
      /collection-contains semantics are evaluated literally (eq, neq, in_,
      gt, lt, gte, lte, is_, like, ilike, contains). Other ops (PostgREST
      expressions like `or_`, `text_search`, `fts`, `filter`, `overlaps`,
      `contained_by`) fall back to "match all rows" — see
      `_PREDICATE_EVALUATORS`. `match({col: val})` is decomposed to eq
      predicates at record time.
  Project: `projects/mock-supabase-write-propagation/` (Phase 2:
  `projects/mock-supabase-select-predicate-filter/`).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Optional
from unittest.mock import MagicMock

from noctusai_lib.testing._schema_cache import get_schema_map
from noctusai_lib.testing.schema_errors import MockSchemaError, MockUnknownTableError
import copy

logger = logging.getLogger(__name__)


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
# Predicate evaluation (used by UPDATE / DELETE filtering)
# ---------------------------------------------------------------------------


def _eval_eq(row: dict, col: str, value: Any) -> bool:
    return row.get(col) == value


def _eval_neq(row: dict, col: str, value: Any) -> bool:
    return row.get(col) != value


def _eval_in(row: dict, col: str, value: Any) -> bool:
    try:
        return row.get(col) in value
    except TypeError:
        return False


def _eval_gt(row: dict, col: str, value: Any) -> bool:
    cell = row.get(col)
    if cell is None or value is None:
        return False
    try:
        return cell > value
    except TypeError:
        return False


def _eval_lt(row: dict, col: str, value: Any) -> bool:
    cell = row.get(col)
    if cell is None or value is None:
        return False
    try:
        return cell < value
    except TypeError:
        return False


def _eval_gte(row: dict, col: str, value: Any) -> bool:
    cell = row.get(col)
    if cell is None or value is None:
        return False
    try:
        return cell >= value
    except TypeError:
        return False


def _eval_lte(row: dict, col: str, value: Any) -> bool:
    cell = row.get(col)
    if cell is None or value is None:
        return False
    try:
        return cell <= value
    except TypeError:
        return False


def _eval_is(row: dict, col: str, value: Any) -> bool:
    return row.get(col) is value


def _eval_like(row: dict, col: str, value: Any) -> bool:
    """SQL LIKE (case-sensitive). `%` → `.*`, `_` → `.`. Non-string cell → False."""
    cell = row.get(col)
    if not isinstance(cell, str) or not isinstance(value, str):
        return False
    return _like_match(cell, value, case_sensitive=True)


def _eval_ilike(row: dict, col: str, value: Any) -> bool:
    """SQL ILIKE (case-insensitive). `%` → `.*`, `_` → `.`. Non-string cell → False."""
    cell = row.get(col)
    if not isinstance(cell, str) or not isinstance(value, str):
        return False
    return _like_match(cell, value, case_sensitive=False)


def _like_match(cell: str, pattern: str, *, case_sensitive: bool) -> bool:
    """Translate a SQL LIKE/ILIKE pattern to a regex anchored at both ends.

    PostgREST passes patterns with `%` (any-substring) and `_` (single-char).
    We escape every other regex metachar so a stray `.` in the pattern doesn't
    behave as a wildcard.
    """
    import re

    out = []
    for ch in pattern:
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(re.escape(ch))
    regex = "^" + "".join(out) + "$"
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.match(regex, cell, flags) is not None
    except re.error:
        return False


def _eval_contains(row: dict, col: str, value: Any) -> bool:
    """PostgREST `contains` — cell-collection contains value-collection.

    Three shapes:
      - cell is a list/tuple/set + value is a list/tuple/set → every value in cell
      - cell is a dict + value is a dict → every key in cell with equal values
      - cell is a string + value is a string → substring (PostgREST text-array
        carve-out; rare, mirrored for completeness)

    Anything else (None, type mismatch) → False.
    """
    cell = row.get(col)
    if cell is None:
        return False
    # List-of-elements vs list-of-elements
    if isinstance(value, (list, tuple, set)):
        if not isinstance(cell, (list, tuple, set)):
            return False
        try:
            return all(v in cell for v in value)
        except TypeError:
            return False
    # Dict subset
    if isinstance(value, Mapping):
        if not isinstance(cell, Mapping):
            return False
        return all(cell.get(k) == v for k, v in value.items())
    # String substring fallback
    if isinstance(value, str) and isinstance(cell, str):
        return value in cell
    return False


# Map op → evaluator. Ops not in this map are recorded but evaluate as
# "match all" (with a debug log) so unsupported PostgREST expressions don't
# silently mismatch. Ops covered: every PostgREST filter call site exercised
# across the workspace (eq/neq/in_/gt/lt/gte/lte/is_/like/ilike/contains).
# Match-all fallback ops: or_/fts/text_search/filter/overlaps/contained_by/match
# (match is decomposed to eq predicates at record time, so it never hits here).
_PREDICATE_EVALUATORS = {
    "eq": _eval_eq,
    "neq": _eval_neq,
    "in_": _eval_in,
    "gt": _eval_gt,
    "lt": _eval_lt,
    "gte": _eval_gte,
    "lte": _eval_lte,
    "is_": _eval_is,
    "like": _eval_like,
    "ilike": _eval_ilike,
    "contains": _eval_contains,
}


def _row_matches_predicates(
    row: dict, predicates: list[tuple[str, str, Any]]
) -> bool:
    """Evaluate every predicate against `row`; AND-conjoin. Empty list
    returns True (match-all, matches PostgREST).
    """
    if not predicates:
        return True
    for op, col, value in predicates:
        evaluator = _PREDICATE_EVALUATORS.get(op)
        if evaluator is None:
            # Unsupported op — match-all fallback. Logged at debug so tests
            # opting in via log capture can see the fallback firing.
            logger.debug(
                "MockSupabase: predicate op %r on column %r evaluates as "
                "match-all (no literal evaluator). Predicates: %r",
                op,
                col,
                predicates,
            )
            continue
        if not evaluator(row, col, value):
            return False
    return True


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

    Filter calls also append a `(op, col, value)` tuple to `_predicates` so
    the SELECT / UPDATE / DELETE execute paths can evaluate which rows match.
    Ops with simple literal semantics (`eq`, `neq`, `in_`, `gt`, `lt`, `gte`,
    `lte`, `is_`, `like`, `ilike`, `contains`) are evaluated literally;
    complex PostgREST expressions (`or_`, `text_search`, `fts`, `filter`,
    `overlaps`, `contained_by`) accumulate as predicates but evaluate as
    match-all (debug log). `match({col: val})` is decomposed to literal `eq`
    predicates at record time.
    """

    _validate_schema: bool = False
    _strict_unknown_tables: bool = False
    _schema: Optional[str] = None
    _table: Optional[str] = None
    _predicates: list  # populated by __init__ on concrete builders

    def _check_col(self, col: str, op: str) -> None:
        if self._validate_schema:
            _validate_column(
                self._schema, self._table, col, operation=op,
                strict_unknown_tables=self._strict_unknown_tables,
            )

    def _record(self, op: str, col: str, value: Any) -> None:
        """Append (op, col, value) to the predicate list. Filter methods
        accept extra positional / keyword args (postgrest SDK compat) but
        only the first value is used for predicate evaluation.
        """
        # `_predicates` is set on every concrete builder __init__; the
        # `getattr` guard tolerates a future builder that forgets to wire it.
        preds = getattr(self, "_predicates", None)
        if preds is None:
            preds = []
            self._predicates = preds
        preds.append((op, col, value))

    def eq(self, col, value=None, *a, **k):
        self._check_col(col, "eq")
        self._record("eq", col, value)
        return self

    def neq(self, col, value=None, *a, **k):
        self._check_col(col, "neq")
        self._record("neq", col, value)
        return self

    def in_(self, col, value=None, *a, **k):
        self._check_col(col, "in_")
        self._record("in_", col, value)
        return self

    def gt(self, col, value=None, *a, **k):
        self._check_col(col, "gt")
        self._record("gt", col, value)
        return self

    def lt(self, col, value=None, *a, **k):
        self._check_col(col, "lt")
        self._record("lt", col, value)
        return self

    def gte(self, col, value=None, *a, **k):
        self._check_col(col, "gte")
        self._record("gte", col, value)
        return self

    def lte(self, col, value=None, *a, **k):
        self._check_col(col, "lte")
        self._record("lte", col, value)
        return self

    def ilike(self, col, value=None, *a, **k):
        self._check_col(col, "ilike")
        self._record("ilike", col, value)
        return self

    def like(self, col, value=None, *a, **k):
        self._check_col(col, "like")
        self._record("like", col, value)
        return self

    def is_(self, col, value=None, *a, **k):
        self._check_col(col, "is_")
        self._record("is_", col, value)
        return self

    def contains(self, col, value=None, *a, **k):
        self._check_col(col, "contains")
        self._record("contains", col, value)
        return self

    def contained_by(self, col, value=None, *a, **k):
        self._check_col(col, "contained_by")
        self._record("contained_by", col, value)
        return self

    def overlaps(self, col, value=None, *a, **k):
        self._check_col(col, "overlaps")
        self._record("overlaps", col, value)
        return self

    def fts(self, col, value=None, *a, **k):
        self._check_col(col, "fts")
        self._record("fts", col, value)
        return self

    def text_search(self, col, value=None, *a, **k):
        self._check_col(col, "text_search")
        self._record("text_search", col, value)
        return self

    def filter(self, col, *a, **k):
        self._check_col(col, "filter")
        # `filter("col", "op", "value")` — record the value if provided,
        # else None. Evaluation falls back to match-all anyway.
        value = a[1] if len(a) > 1 else None
        self._record("filter", col, value)
        return self

    def match(self, query, *a, **k):
        if self._validate_schema and isinstance(query, Mapping):
            for key in query.keys():
                _validate_column(
                    self._schema, self._table, str(key), operation="match",
                    strict_unknown_tables=self._strict_unknown_tables,
                )
        # `match({col: val, ...})` is logically AND of `eq` per key. Record
        # each pair as a literal `eq` predicate so UPDATE/DELETE filter
        # correctly.
        if isinstance(query, Mapping):
            for k_, v_ in query.items():
                self._record("eq", str(k_), v_)
        return self

    def or_(self, *a, **k):
        # PostgREST expression like "status.eq.active,tier.gte.3" — adding a
        # parser is out of scope per project §4. Record as a synthetic
        # match-all predicate (op="or_") so the predicate list reflects the
        # call, but evaluation falls back to match-all (debug log).
        expr = a[0] if a else None
        self._record("or_", "<or_expression>", expr)
        return self

    @property
    def not_(self):
        return self


# ---------------------------------------------------------------------------
# MockSelectBuilder — returned by .select()
# ---------------------------------------------------------------------------

class MockSelectBuilder(_FilterMixin, _MockExecuteMixin):
    """Mirrors SyncSelectRequestBuilder.

    Holds a reference to the table's shared row list so reads see writes
    that mutated the shared list. The reference is captured once at __init__
    (the shared list is mutated in place by INSERT/UPDATE/DELETE; SELECT
    reads through the same reference).
    """

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
        # Preserve the original semantics: `data or []` → empty list when
        # None or empty. Note: we trust callers to pass in the shared list
        # reference so reads see writes.
        self._data = data if data is not None else []
        self._single_mode = False
        self._count = count
        self._response_queue = response_queue
        self._response_idx = response_idx
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables
        self._predicates: list[tuple[str, str, Any]] = []

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

    def _filtered_rows(self) -> list:
        """Evaluate `_predicates` against the shared list and return matches.

        Empty predicate list → return all rows (PostgREST match-all). Non-dict
        rows are passed through unchanged (defensive — matches the UPDATE/DELETE
        path's handling at `_apply_mutation`).
        """
        if not isinstance(self._data, list):
            return self._data
        if not self._predicates:
            # Snapshot the list — callers shouldn't accidentally mutate the
            # shared store via response.data. Mirrors the empty-predicates
            # PostgREST contract while keeping isolation.
            return list(self._data)
        out = []
        for row in self._data:
            if not isinstance(row, dict):
                # Non-dict rows survive at the same position as the UPDATE/DELETE
                # path — keep them in the output unconditionally (no predicate
                # can match a non-dict literally).
                out.append(row)
                continue
            if _row_matches_predicates(row, self._predicates):
                out.append(row)
        return out

    def execute(self):
        # Response queue wins — propagation / predicate-filtering suppressed,
        # mirroring the UPDATE/DELETE contract documented at module-level.
        if self._response_queue is not None:
            return self._do_execute()
        filtered = self._filtered_rows()
        data = filtered
        if self._single_mode and isinstance(data, list):
            data = data[0] if data else None
        self._single_mode = False
        return MockSupabaseResponse(data=data, count=self._count)


# ---------------------------------------------------------------------------
# MockFilterBuilder — returned by .update() / .delete()
# ---------------------------------------------------------------------------

class MockFilterBuilder(_FilterMixin, _MockExecuteMixin):
    """Mirrors SyncFilterRequestBuilder.

    Returned by `update(...)` / `delete()` / `upsert(...)` chains. Holds a
    reference to the table's shared row list and (for update/delete) a
    `_mutation_kind` flag plus optional `_update_payload`. On `execute()`:

      - If a response-queue is set, the queue dictates the response and
        propagation is suppressed.
      - Otherwise the accumulated `_predicates` are evaluated against the
        shared list. Matching rows are mutated in place (UPDATE) or
        removed (DELETE). The mutated/deleted rows are returned in
        `response.data`.
    """

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
        mutation_kind: Optional[str] = None,  # "update" | "delete" | None
        update_payload: Optional[Mapping] = None,
    ):
        self._data = data if data is not None else []
        self._single_mode = False
        self._count = None
        self._response_queue = response_queue
        self._response_idx = response_idx
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables
        self._predicates: list[tuple[str, str, Any]] = []
        self._mutation_kind = mutation_kind
        self._update_payload = update_payload

    def _apply_mutation(self) -> list[dict]:
        """Evaluate predicates against the shared list and apply the mutation.

        Returns the list of affected rows (mutated for UPDATE, removed for
        DELETE) which becomes `response.data`. Empty predicate list means
        match-all (PostgREST semantics). Non-dict rows are skipped (defensive).
        """
        if not isinstance(self._data, list):
            return []
        affected: list[dict] = []
        survivors: list[dict] = []
        for row in self._data:
            if not isinstance(row, dict):
                survivors.append(row)
                continue
            if _row_matches_predicates(row, self._predicates):
                affected.append(row)
            else:
                survivors.append(row)

        if self._mutation_kind == "update":
            payload = self._update_payload or {}
            for row in affected:
                row.update(payload)
            # Affected rows are still in self._data via the original list
            # (we didn't remove them — only computed `affected` for the
            # response). The mutation is in place.
            return list(affected)

        if self._mutation_kind == "delete":
            # Replace contents in place so the shared reference stays
            # stable. Slice-assignment mutates the same list object that
            # downstream SELECT builders hold.
            self._data[:] = survivors
            return list(affected)

        return list(affected)

    def execute(self):
        # Response queue wins — suppress propagation.
        if self._response_queue is not None:
            return self._do_execute()
        # Apply mutation against the shared list, then return the result.
        if self._mutation_kind in ("update", "delete"):
            affected = self._apply_mutation()
            if self._single_mode:
                affected = affected[0] if affected else None
                self._single_mode = False
            return MockSupabaseResponse(data=affected, count=self._count)
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockQueryBuilder — returned by .insert() / .upsert()
# ---------------------------------------------------------------------------

class MockQueryBuilder(_MockExecuteMixin):
    """Mirrors SyncQueryRequestBuilder.

    Returned by `insert(...)`. The propagation step (appending response
    rows to the shared list) already happened in `MockRequestBuilder.insert`
    by the time this builder is constructed — `_data` here is the
    response-side rows (with auto-id), not the shared table list. This
    keeps the response shape (`result.data[0]['id']`) intact.
    """

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
        self._data = data if data is not None else []
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

    Write-to-read propagation (2026-05-10): `self._data` is a stable list
    reference shared with every downstream builder created by `select`,
    `insert`, `update`, `delete`, `upsert`. INSERT extends this list with
    response rows; UPDATE mutates matching rows in place via `dict.update`;
    DELETE replaces contents via slice assignment. SELECT readers see all
    three because they hold the same list reference.
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
        # Mirror of `inserted_payloads` for `.update(...)` calls. Tests
        # read `db.table(t).updated_payloads` to assert that an update
        # was issued with the expected dict — same shape as the
        # insert-side pattern. The list collects every dict passed to
        # `update(...)`, in call order.
        self.updated_payloads: list = []
        # Materialize the seed data as a fresh mutable list with deep-copied
        # rows. Callers that passed a dict (single row), a tuple, or shared a
        # list with another builder all get a stable, owned-by-this-builder
        # list — write propagation mutates this exact reference. Deep-copy of
        # rows isolates module-level test fixtures from in-place mutation by
        # UPDATE / DELETE / INSERT propagation (closes the 2026-05-11 test-
        # isolation pollution bug: tests passing SAMPLE_X module dicts into
        # `set_table_data` were getting them mutated by earlier tests' updates).
        if data is None:
            self._data = []
        elif isinstance(data, dict):
            self._data = copy.deepcopy([data])
        elif isinstance(data, list):
            self._data = copy.deepcopy(list(data))
        else:
            self._data = copy.deepcopy(list(data) if isinstance(data, Iterable) else [data])
        self._response_queue = None
        self._response_idx = None
        self._validate_schema = validate_schema
        self._schema = schema
        self._table = table
        self._strict_unknown_tables = strict_unknown_tables
        # Running counter for auto-id generation. Incremented per row
        # appended via insert; survives across calls so successive inserts
        # get distinct ids (mock-<table>-1, mock-<table>-2, ...).
        self._auto_id_seq = 0

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

    def _check_table_known(self, op: str) -> None:
        """When `strict_unknown_tables=True`, raise `MockUnknownTableError`
        if the bound table is absent from the migration-derived schema cache.

        Runs regardless of `_validate_schema` — orthogonal to column
        validation. This lets a product opt in to *table-existence*
        checking even while it carries known column-level drift that
        keeps `validate_schema` off. Used by `therapy-platform-drift-sweep`
        (2026-05-11) to guard against re-introducing the 11 phantom
        table names the sweep removed.
        """
        if not self._strict_unknown_tables:
            return
        # Empty cache (no migrations loaded) → no-op; otherwise we'd raise
        # on every table for products that don't ship migrations under the
        # auto-discovered roots. Tier 1.5 G4 contract.
        cache = get_schema_map()
        if not cache:
            return
        qualified = f"{(self._schema or 'public').lower()}.{(self._table or '').lower()}"
        if qualified not in cache:
            raise MockUnknownTableError(
                schema=self._schema or "public",
                table=self._table or "",
                operation=op,
            )

    def select(self, cols="*", *a, **k):
        self._check_table_known("select")
        if self._validate_schema and isinstance(cols, str):
            _validate_select_cols(
                self._schema, self._table, cols,
                strict_unknown_tables=self._strict_unknown_tables,
            )
        count = k.get("count")
        # Pass the SHARED LIST REFERENCE so mutations (already-applied or
        # subsequent inside the same chain — though that's atypical) are
        # visible. The select builder reads through the reference at
        # execute() time.
        return MockSelectBuilder(
            self._data,
            count=len(self._data) if count == "exact" else None,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def insert(self, data=None, *a, **k):
        """Track the insert payload AND return the inserted row(s) so that
        production code reading `result.data` after `insert(...).execute()`
        sees what was inserted — matching real Supabase behavior.

        Two readers exist for an insert:
          1. **Production code** that does `result = db.table(t).insert(row).execute()`
             then `first_or_none(result)` — needs `result.data` to contain the
             inserted row(s) with `id` set. This pattern is in `messaging_service.
             send_message`, `audit_service.log`, and dozens of other places.
          2. **Tests** that read `db.table(t).inserted_payloads` to assert the
             write happened with the right shape. This pattern is documented
             in `KB § PATTERNS/testing.md § Side-effect verification via
             inserted_payloads`.

        Both are preserved. `inserted_payloads` keeps the original payload
        (without auto-generated id, so tests can assert the exact dict the
        production code passed); `execute().data` returns the normalized rows
        (with auto-id) so production code's `first_or_none(result)["id"]`
        access works.

        **Auto-id generation:** if a row's `id` is absent or None, fill with
        a stable mock-id of the form `mock-<table>-<n>` where `n` is the
        running count of inserts on this table. Tests that need a specific
        id should pass it in the payload.

        **Insert-failure simulation:** queue an empty response via
        `mock_db.set_sequential_responses(name, [MockSupabaseResponse(data=[])])`.
        `set_table_data(name, [...])` controls SELECT seeding only — it does
        NOT influence insert response (use the queue for that).
        """
        self._check_table_known("insert")
        if self._validate_schema:
            _validate_payload_keys(
                self._schema, self._table, data, operation="insert",
                strict_unknown_tables=self._strict_unknown_tables,
            )

        # Normalize to list-of-dicts.
        if isinstance(data, list):
            payload_rows = list(data)
        elif data is not None:
            payload_rows = [data]
        else:
            payload_rows = []

        # Track raw payloads (no auto-id) — tests read `inserted_payloads`
        # and expect the exact dict the caller passed.
        if isinstance(data, list):
            self.inserted_payloads.extend(data)
        elif data is not None:
            self.inserted_payloads.append(data)

        # Build the response rows (with auto-id) so production callers reading
        # `result.data[0]["id"]` get a value — matches real Supabase.
        response_rows = []
        for row in payload_rows:
            if not isinstance(row, dict):
                response_rows.append(row)
                continue
            response_row = dict(row)
            if not response_row.get("id"):
                self._auto_id_seq += 1
                table_label = self._table or "row"
                response_row["id"] = f"mock-{table_label}-{self._auto_id_seq}"
            response_rows.append(response_row)

        # Write-propagation: extend the shared list with the response rows
        # so subsequent SELECT sees them. Suppressed when a response queue
        # is set (queue dictates response, propagation would be surprising).
        if self._response_queue is None:
            self._data.extend(response_rows)

        return MockQueryBuilder(
            response_rows,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def update(self, data=None, *a, **k):
        self._check_table_known("update")
        if self._validate_schema:
            _validate_payload_keys(
                self._schema, self._table, data, operation="update",
                strict_unknown_tables=self._strict_unknown_tables,
            )
        # Mirror inserted_payloads — track the update payload so tests
        # can assert side effects without monkey-patching the helper.
        if isinstance(data, list):
            self.updated_payloads.extend(data)
        elif data is not None:
            self.updated_payloads.append(data)
        # The filter builder receives the SHARED LIST REFERENCE plus the
        # update payload. On execute() it evaluates predicates and mutates
        # matching rows in place via dict.update.
        update_payload: Optional[Mapping]
        if isinstance(data, Mapping):
            update_payload = data
        elif isinstance(data, list) and data and isinstance(data[0], Mapping):
            # PostgREST list-update is rare; merge keys (last wins) for our
            # propagation step. Tests reading updated_payloads still see
            # the raw list.
            merged: dict = {}
            for item in data:
                if isinstance(item, Mapping):
                    merged.update(item)
            update_payload = merged
        else:
            update_payload = None
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            mutation_kind="update",
            update_payload=update_payload,
            **self._builder_kwargs(),
        )

    def upsert(self, data=None, *a, **k):
        self._check_table_known("upsert")
        if self._validate_schema:
            _validate_payload_keys(
                self._schema, self._table, data, operation="upsert",
                strict_unknown_tables=self._strict_unknown_tables,
            )
        # Upsert propagation is deferred to a follow-up project (needs
        # conflict-target tracking via `on_conflict`). For now, the call
        # returns a filter builder with the shared list but no mutation
        # kind — execute() falls through to _do_execute which returns the
        # current data. Documented in §4 of PROJECT.md.
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            **self._builder_kwargs(),
        )

    def delete(self, *a, **k):
        self._check_table_known("delete")
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            mutation_kind="delete",
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
        """Set mock data for a specific table — controls SELECT seeding only.

        Insert/update/upsert/delete responses are NOT influenced by this.
        Use `set_sequential_responses(name, [MockSupabaseResponse(...)])` to
        control execute() output for write operations or to simulate failures.
        """
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
