"""Pydantic In/Out schemas for the Supabase connector MCP tools.

One In + one Out per tool (cloudflare/n8n/waha/hostinger/github/vista
shape). Out models keep the raw Supabase object as a `dict`/`list` where
full fidelity matters (project payloads, query result-sets, migration
records) — lossy normalization would hide state. `supabase` imports as a
top-level package (PyPI-`mcp`-shadow trick, `mcp/_kit/README.md`), so
`types.py` is safe here.

Shapes verified 2026-05-21 against the live Supabase Management API v1
OpenAPI spec (`https://api.supabase.com/api/v1-json`) — there is no live
token yet, so these are documented-shape Pydantic schemas; LIVE
validation is deferred until the user pastes a Personal Access Token:
- project.list → array of project objects
  ({id, ref, organization_id, name, region, created_at, status, database}).
- project.get  → single project object.
- db.query → `POST /v1/projects/{ref}/database/query` body
  {query (req), parameters?, read_only?} → the query result-set (a JSON
  array of row objects for SELECTs; may be empty/None for statements).
- migration.list  → `GET /v1/projects/{ref}/database/migrations` → the
  applied-migrations record set.
- migration.apply → `POST /v1/projects/{ref}/database/migrations` body
  {query (req), name?} → applies + records a migration.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

# ─── Shared write-gate field (mirrors cloudflare/hostinger/waha/n8n) ──────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False/omitted returns a "
        "typed error (status 412) and performs NO side-effect. This is "
        "the confirm-then-execute gate for a state-changing Supabase "
        "action (a mutating SQL statement via db.query, or migration.apply)."
    ),
)

_PROJECT_REF = Field(
    None,
    description="Supabase project reference (e.g. abcdefghijklmnop). "
    "Optional — defaults to the connector's configured "
    "SUPABASE_PROJECT_REF when omitted.",
)


# ═══════════════════════════════════════════════════════════════════════
# PROJECT
# ═══════════════════════════════════════════════════════════════════════


class ProjectListInput(BaseModel):
    """List the projects on the account. PURE read. Not project-scoped —
    needs only the access token."""


class ProjectListOutput(BaseModel):
    projects: List[dict] = Field(default_factory=list)
    error: Optional[dict] = None


class ProjectGetInput(BaseModel):
    """Inspect one project — status, region, organization, database host.
    PURE read."""

    project_ref: Optional[str] = _PROJECT_REF


class ProjectGetOutput(BaseModel):
    project: Optional[dict] = None
    error: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════
# DATABASE (db.query — the core — + information_schema-backed reads)
# ═══════════════════════════════════════════════════════════════════════


class DbQueryInput(BaseModel):
    """Run a raw SQL statement against the project's database via
    `POST /v1/projects/{ref}/database/query`.

    **Confirm gate is BEST-EFFORT.** A PURE read (leading keyword ∈
    {SELECT, EXPLAIN, SHOW, WITH...SELECT}) runs free. ANYTHING else
    (INSERT/UPDATE/DELETE/DDL/CALL/TRUNCATE/...) is treated as a write and
    requires `confirm=true` (412 until then). The keyword heuristic is a
    convenience guard, NOT a security boundary — a `WITH ... DELETE` or a
    function call with side-effects can still mutate; when in doubt the
    caller should pass `confirm=true` deliberately. This honesty about the
    heuristic's limits is the gated-capability-honesty contract.
    """

    query: str = Field(..., description="The SQL statement to execute.")
    project_ref: Optional[str] = _PROJECT_REF
    confirm: bool = _CONFIRM


class DbQueryOutput(BaseModel):
    rows: Optional[Any] = None
    ok: bool = False
    read_only: Optional[bool] = None
    error: Optional[dict] = None


class DbListTablesInput(BaseModel):
    """List tables in the database (PURE read — implemented via a
    `db.query` against `information_schema.tables`). Optional `schema`
    filters to one schema (default: all user schemas, excluding the
    pg_/information_schema internals)."""

    project_ref: Optional[str] = _PROJECT_REF
    schema_name: Optional[str] = Field(
        None,
        description="Restrict to one schema (e.g. public). Optional — "
        "omitted lists all non-internal schemas.",
    )


class DbListTablesOutput(BaseModel):
    tables: Optional[Any] = None
    ok: bool = False
    error: Optional[dict] = None


class DbListSchemasInput(BaseModel):
    """List schemas in the database (PURE read — implemented via a
    `db.query` against `information_schema.schemata`, excluding the
    pg_/information_schema internals)."""

    project_ref: Optional[str] = _PROJECT_REF


class DbListSchemasOutput(BaseModel):
    schemas: Optional[Any] = None
    ok: bool = False
    error: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════
# MIGRATIONS
# ═══════════════════════════════════════════════════════════════════════


class MigrationListInput(BaseModel):
    """List the applied migrations on the project. PURE read
    (`GET /v1/projects/{ref}/database/migrations`)."""

    project_ref: Optional[str] = _PROJECT_REF


class MigrationListOutput(BaseModel):
    migrations: Optional[Any] = None
    ok: bool = False
    error: Optional[dict] = None


class MigrationApplyInput(BaseModel):
    """Apply (and record) a database migration. WRITE — confirm-gated
    (`POST /v1/projects/{ref}/database/migrations`); this runs DDL/SQL
    against the live database AND records it in the migration history.

    `query` is the migration SQL; `name` is the optional human label
    Supabase records for it.
    """

    query: str = Field(..., description="The migration SQL to apply.")
    name: Optional[str] = Field(
        None,
        description="Optional human-readable migration name recorded by "
        "Supabase.",
    )
    project_ref: Optional[str] = _PROJECT_REF
    confirm: bool = _CONFIRM


class MigrationApplyOutput(BaseModel):
    ok: bool = False
    result: Optional[Any] = None
    error: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════
# DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════


class ConnectionStatusInput(BaseModel):
    """Introspect the Supabase dependency. PURE read.

    Gated-capability honesty: distinguishes not-configured (no token) vs
    host-down (network failure) vs token-rejected (401/403) vs ok (token
    verified) — so the operator gets a real tri-state signal rather than
    a conflated failure. Probes `GET /v1/projects` (the cheapest authed
    read).
    """


class ConnectionStatusOutput(BaseModel):
    configured: bool = False
    root: Optional[str] = None
    reachable: Optional[bool] = None
    authenticated: Optional[bool] = None
    project_ref_present: bool = False
    error: Optional[dict] = None


__all__ = [
    # project
    "ProjectListInput",
    "ProjectListOutput",
    "ProjectGetInput",
    "ProjectGetOutput",
    # db
    "DbQueryInput",
    "DbQueryOutput",
    "DbListTablesInput",
    "DbListTablesOutput",
    "DbListSchemasInput",
    "DbListSchemasOutput",
    # migration
    "MigrationListInput",
    "MigrationListOutput",
    "MigrationApplyInput",
    "MigrationApplyOutput",
    # diagnostics
    "ConnectionStatusInput",
    "ConnectionStatusOutput",
]
