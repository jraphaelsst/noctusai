"""
Schema-validation error types for MockSupabaseClient.

When `validate_schema=True`, mock filter/select/insert/update/upsert calls
that reference a column not present in the migration-file-derived schema
raise `MockSchemaError` with a clear message naming the offending table,
the invalid column, and the valid column list.

This closes the silent-fail class that shipped 12+ wrong-column filters
through the therapy test suite undetected (ref:
`projects/compliance-audit-reconciliation` Phase 2).
"""
from __future__ import annotations


class MockSchemaError(AssertionError):
    """Raised when a mock call references a column not in the schema cache.

    Subclasses AssertionError so pytest treats it like any failed assertion
    — red test, clear stack trace. Callers should never `except` this.
    """

    def __init__(
        self,
        *,
        schema: str,
        table: str,
        invalid_column: str,
        valid_columns: list[str] | set[str] | tuple[str, ...],
        operation: str = "filter",
    ):
        self.schema = schema
        self.table = table
        self.invalid_column = invalid_column
        self.valid_columns = sorted(valid_columns)
        self.operation = operation

        qualified = f"{schema}.{table}" if schema else table
        message = (
            f"{qualified} has no column {invalid_column!r} "
            f"(called via {operation}). "
            f"Valid columns: {', '.join(self.valid_columns) or '<none>'}."
        )
        super().__init__(message)


class MockCheckViolation(AssertionError):
    """Raised when a mock INSERT/UPDATE writes a CHECK-violating literal.

    Activated when `MockSupabaseClient(validate_schema_constraints=True,
    manifest={table: {column: (allowed_values, ...)}})` is configured. On
    INSERT or UPDATE, every row literal whose `(table, column)` appears in
    the manifest is compared against the allowed-values tuple — a miss
    raises `MockCheckViolation` so the test fails loudly, mirroring the
    PostgreSQL CHECK-constraint behavior the real DB would emit at INSERT
    time (`new row for relation "X" violates check constraint "X_status_check"`).

    Closes the silent-success class where tests would pass with a write that
    Postgres rejects at runtime. Default-OFF so existing tests are
    unchanged; products opt in by passing a manifest in `conftest.py`.

    Subclasses `AssertionError` so pytest treats it as a failed assertion
    (red, with stack trace).
    """

    def __init__(
        self,
        *,
        schema: str | None,
        table: str,
        column: str,
        invalid_value,
        allowed_values,
        operation: str = "insert",
    ):
        self.schema = schema
        self.table = table
        self.column = column
        self.invalid_value = invalid_value
        self.allowed_values = tuple(allowed_values)
        self.operation = operation

        qualified = f"{schema}.{table}" if schema else table
        allowed_repr = ", ".join(repr(v) for v in self.allowed_values) or "<none>"
        message = (
            f"{qualified}.{column}: {invalid_value!r} not in ({allowed_repr}) "
            f"(called via {operation}). CHECK constraint violated — the real "
            f"database would reject this write."
        )
        super().__init__(message)


class MockUnknownTableError(MockSchemaError):
    """Raised when a mock call references a table that does not appear in any
    migration file, AND the client was constructed with
    `strict_unknown_tables=True` (Tier 1.5 G4 hardening, 2026-04-24).

    Default behavior remains WARN+skip so existing tests keep passing; the
    strict mode is opt-in for products whose schema-drift reconciliation
    has finished. Inherits from `MockSchemaError` so `except MockSchemaError`
    catches both classes.
    """

    def __init__(self, *, schema: str, table: str, operation: str = "filter"):
        # Construct with a sentinel column + empty valid-columns list, but
        # override the parent's message via __init__ to make the failure
        # mode obvious.
        self.schema = schema
        self.table = table
        self.invalid_column = "<table-not-found>"
        self.valid_columns: list[str] = []
        self.operation = operation
        qualified = f"{schema}.{table}" if schema else table
        message = (
            f"Table {qualified} does not exist in any migration file "
            f"(called via {operation}, strict_unknown_tables=True). "
            f"Either add the migration file under products/<product>/backend/migrations/ "
            f"or correct the table name."
        )
        # Skip MockSchemaError.__init__ — call AssertionError directly.
        AssertionError.__init__(self, message)
