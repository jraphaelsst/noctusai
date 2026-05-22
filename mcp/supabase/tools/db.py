"""supabase.db.* tools — the core SQL surface.

- `supabase.db.query` — run raw SQL via
  `POST /v1/projects/{ref}/database/query`. A PURE read runs free; a
  mutating statement is confirm-gated (412 until `confirm=true`). The
  read/write classification is a BEST-EFFORT leading-keyword heuristic
  (see `is_read_only_sql`), NOT a security boundary — documented honestly
  (gated-capability honesty, CLAUDE.md §1).
- `supabase.db.list_tables` / `supabase.db.list_schemas` — convenience
  reads implemented ON TOP OF `db.query` against `information_schema`
  (no confirm needed; they are pure reads).

Every tool routes through the single `api.request_json` HTTP seam (tests
patch `supabase.api.request_json`). API failure ⇒ a typed-error
envelope, never a fabricated success.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    DbListSchemasInput,
    DbListSchemasOutput,
    DbListTablesInput,
    DbListTablesOutput,
    DbQueryInput,
    DbQueryOutput,
)

logger = logging.getLogger(__name__)

# Leading SQL keywords that begin a PURE read. A statement starting with
# one of these (after stripping comments/whitespace) runs without a
# confirm gate. WITH (CTE) is included because the COMMON case is a
# read-only `WITH ... SELECT`; a `WITH ... DELETE` is a known false-read
# of the heuristic (documented in DbQueryInput / the README — the
# heuristic is a convenience guard, not a security boundary).
_READ_LEADERS = ("SELECT", "EXPLAIN", "SHOW", "WITH", "TABLE", "VALUES")


def _query_base(ref: str) -> str:
    return f"/v1/projects/{ref}/database/query"


def _ctx() -> dict:
    s = get_settings()
    return {
        "access_token": s.access_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


def _resolve_ref(passed: str | None) -> tuple[str, dict | None]:
    """Resolve the project ref reading THIS module's `get_settings` (so a
    test patching `supabase.tools.db.get_settings` is honoured); render any
    error as the typed-error dict. Shared precedence/424 logic lives in
    `api.resolve_ref`."""
    ref, err = api.resolve_ref(get_settings(), passed)
    return ref, (typed_error(err) if err else None)


def _strip_sql_lead(sql: str) -> str:
    """Return the SQL with leading whitespace + line/block comments
    removed, so the first real keyword can be classified. Best-effort —
    strips `--` line comments and `/* */` block comments only at the
    LEADING edge (enough to read the first keyword)."""
    s = sql.lstrip()
    changed = True
    while changed:
        changed = False
        if s.startswith("--"):
            nl = s.find("\n")
            s = "" if nl == -1 else s[nl + 1:]
            s = s.lstrip()
            changed = True
        elif s.startswith("/*"):
            end = s.find("*/")
            s = "" if end == -1 else s[end + 2:]
            s = s.lstrip()
            changed = True
    return s


def is_read_only_sql(sql: str) -> bool:
    """BEST-EFFORT: True iff `sql` begins with a read-only leading keyword
    (after stripping leading comments/whitespace). NOT a security
    boundary — a `WITH ... DELETE`, a writable function call, or a
    multi-statement batch can still mutate. See `DbQueryInput`."""
    head = _strip_sql_lead(sql).upper()
    first = head.split(None, 1)[0] if head.split() else ""
    return first in _READ_LEADERS


async def db_query(args: dict) -> dict:
    inp = DbQueryInput(**args)
    read_only = is_read_only_sql(inp.query)
    if not read_only and not inp.confirm:
        return DbQueryOutput(
            read_only=False,
            error=typed_error(api.ConfirmationRequiredError(
                "supabase.db.query",
                "runs a NON-read SQL statement against the live database "
                "(INSERT/UPDATE/DELETE/DDL/etc. — the read/write check is a "
                "best-effort leading-keyword heuristic, not a guarantee)",
            )),
        ).model_dump()
    ref, err = _resolve_ref(inp.project_ref)
    if err:
        return DbQueryOutput(read_only=read_only, error=err).model_dump()
    # Pass the heuristic verdict to Supabase too (it supports a read_only
    # flag on the query endpoint) so a read is double-guarded server-side.
    body = {"query": inp.query, "read_only": read_only}
    try:
        data = api.request_json("POST", _query_base(ref), body=body, **_ctx())
    except api.SupabaseApiError as e:
        return DbQueryOutput(read_only=read_only, error=typed_error(e)).model_dump()
    return DbQueryOutput(rows=data, ok=True, read_only=read_only).model_dump()


async def db_list_tables(args: dict) -> dict:
    inp = DbListTablesInput(**args)
    ref, err = _resolve_ref(inp.project_ref)
    if err:
        return DbListTablesOutput(error=err).model_dump()
    if inp.schema_name:
        where = f"table_schema = '{inp.schema_name}'"
    else:
        where = "table_schema NOT IN ('pg_catalog', 'information_schema')"
    sql = (
        "SELECT table_schema, table_name, table_type "
        "FROM information_schema.tables "
        f"WHERE {where} "
        "ORDER BY table_schema, table_name"
    )
    body = {"query": sql, "read_only": True}
    try:
        data = api.request_json("POST", _query_base(ref), body=body, **_ctx())
    except api.SupabaseApiError as e:
        return DbListTablesOutput(error=typed_error(e)).model_dump()
    return DbListTablesOutput(tables=data, ok=True).model_dump()


async def db_list_schemas(args: dict) -> dict:
    inp = DbListSchemasInput(**args)
    ref, err = _resolve_ref(inp.project_ref)
    if err:
        return DbListSchemasOutput(error=err).model_dump()
    sql = (
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name NOT IN ('pg_catalog', 'information_schema') "
        "AND schema_name NOT LIKE 'pg_%' "
        "ORDER BY schema_name"
    )
    body = {"query": sql, "read_only": True}
    try:
        data = api.request_json("POST", _query_base(ref), body=body, **_ctx())
    except api.SupabaseApiError as e:
        return DbListSchemasOutput(error=typed_error(e)).model_dump()
    return DbListSchemasOutput(schemas=data, ok=True).model_dump()


HANDLERS = {
    "supabase.db.query": db_query,
    "supabase.db.list_tables": db_list_tables,
    "supabase.db.list_schemas": db_list_schemas,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="supabase.db.query",
             description="Run raw SQL against the project DB. A pure read "
             "(SELECT/EXPLAIN/SHOW/WITH...) runs free; any mutating "
             "statement is WRITE — confirm-gated (412). The read/write "
             "check is a BEST-EFFORT leading-keyword heuristic, NOT a "
             "security boundary.",
             inputSchema=DbQueryInput.model_json_schema()),
        Tool(name="supabase.db.list_tables",
             description="List tables (via information_schema.tables). "
             "READ-ONLY. Optional schema_name filter.",
             inputSchema=DbListTablesInput.model_json_schema()),
        Tool(name="supabase.db.list_schemas",
             description="List schemas (via information_schema.schemata, "
             "excluding internals). READ-ONLY.",
             inputSchema=DbListSchemasInput.model_json_schema()),
    ]


__all__ = [
    "register",
    "tool_descriptors",
    "HANDLERS",
    "is_read_only_sql",
]
