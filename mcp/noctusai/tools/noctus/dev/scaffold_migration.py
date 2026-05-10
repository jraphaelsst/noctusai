"""Migration scaffolder — emits the next-numbered SQL file for a product.

WHY this tool exists
--------------------
Two slips this catches at authoring-time:

1. **Migration-numbering slip.** Every product holds an ordered, prefix-numbered
   migration log (``001_seed.sql`` → ``002_status_pagina.sql`` → …). Hand-rolled
   numbering drifts: agents skip ahead, repeat a number, or invent the next slot
   wrong. This tool walks the directory and computes ``max(NN) + 1`` from the
   actual filesystem, so the consumer never has to count.

2. **Canonical-SQL drift.** New migrations must use the helpers from
   ``noctusai_lib.domain.sql_templates`` (``set_search_path`` /
   ``updated_at_function`` / ``updated_at_trigger`` / ``rls_subquery_policy``)
   so the platform-wide DDL conventions don't fork per-product. The emitted
   skeleton wires these in by default and points at the helpers in a comment
   block — no consumer re-reading the SQL conventions doc.

WHEN to use
-----------
Every fresh product migration. Authoring scratch SQL by hand still works (the
file is plain SQL once written), but reach for the scaffolder first — it pairs
with ``noctus.dev.scaffold_product`` (which emits ``001_seed.sql`` for new
products) for migrations 002+.

Mirrors ``mcp/noctusai/tools/noctus/dev/scaffold.py`` end-to-end: same
workspace-aware path resolution via ``settings.REPO_ROOT`` / ``PRODUCTS_DIR``,
same ``register(server)`` per-file MCP registration shape.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

# Per `feedback_mcp_path_constants_from_settings.md` — every MCP tool module
# imports REPO_ROOT/PRODUCTS_DIR from settings, never computes via parents[N].
from settings import PRODUCTS_DIR

# Seed-lib lookup is a separate concern from REPO_ROOT — settings doesn't
# expose it because the seed-lib path is not a tool-resolution constant. We
# reach `noctusai_lib.domain.sql_templates` via the seed-lib `sys.path` shim
# the test harness installs; in the running MCP server, `noctusai_lib` is
# already importable because the server's venv has it installed.
from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    set_search_path,
    updated_at_function,
    updated_at_trigger,
)

# Authoring-ergonomic wrappers — `prelude` bundles the schema-lock with a
# why-block; `noctusai_lib.sql.updated_at_trigger` emits function + trigger
# in one call. Used for the top-of-file prelude and the multi-table
# `with_updated_at=[...]` shortcut. Single-table `with_table=` keeps the
# existing canonical-helper composition for backward compatibility.
from noctusai_lib.sql import (
    prelude as sql_prelude,
    updated_at_trigger as sql_updated_at_trigger,
)

logger = logging.getLogger(__name__)

# Numeric prefix matcher — matches `NNN_<rest>.sql` where NNN is 1+ digits.
# Width is *whatever the existing files use* (3 digits today, future-proof).
_NN_RE = re.compile(r"^(\d+)_.+\.sql$")


def _slug_to_default_schema(product_slug: str) -> str:
    """`youtube-crawler` → `youtube_crawler` (matches scaffold_product convention)."""
    return product_slug.replace("-", "_")


def _migrations_dir(product_slug: str, products_dir: Path) -> Path:
    return products_dir / product_slug / "backend" / "migrations"


def _next_number(migrations_dir: Path) -> int | None:
    """Walk migrations_dir, return max(NN)+1, or None if no migrations exist.

    None = "scaffold the product first" — we do NOT silently start at 001
    because a missing migrations dir means the product itself is missing
    the seed migration `001_seed.sql`, and a 001 emitted by the migration
    scaffolder would step on the product scaffolder's territory.
    """
    found_any = False
    max_nn = 0
    for child in migrations_dir.iterdir():
        if not child.is_file():
            continue
        m = _NN_RE.match(child.name)
        if not m:
            continue
        found_any = True
        nn = int(m.group(1))
        if nn > max_nn:
            max_nn = nn
    if not found_any:
        return None
    return max_nn + 1


def _format_number(n: int) -> str:
    """Three-digit zero-padded prefix to match the platform convention."""
    return f"{n:03d}"


def _build_with_table_block(schema: str, table: str) -> str:
    """Emit a CREATE TABLE skeleton + updated_at_function + trigger + RLS policy hook.

    Idempotency: ``updated_at_function(schema)`` uses ``CREATE OR REPLACE``
    inside the helper, so emitting it again is safe (per-schema, the function
    converges to the same body). The trigger uses ``CREATE OR REPLACE TRIGGER``
    for the same reason.
    """
    table_ddl = (
        f"CREATE TABLE IF NOT EXISTS {schema}.{table} (\n"
        f"    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        f"    -- TODO: add columns here\n"
        f"    created_at timestamptz NOT NULL DEFAULT now(),\n"
        f"    updated_at timestamptz NOT NULL DEFAULT now()\n"
        f");"
    )

    rls_enable = (
        f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;"
    )

    rls_policy_stub = rls_subquery_policy(
        schema,
        table,
        f"{table}_select_own",
        "SELECT",
        using="(SELECT auth.uid()) IS NOT NULL  -- TODO: tighten to ownership predicate",
    )

    return "\n\n".join(
        [
            f"-- ----- Table: {schema}.{table} -----",
            table_ddl,
            "-- updated_at trigger wiring (idempotent — function uses CREATE OR REPLACE)",
            updated_at_function(schema),
            updated_at_trigger(schema, table),
            "-- Row-Level Security",
            rls_enable,
            rls_policy_stub,
        ]
    )


def _build_updated_at_block(schema: str, tables: list[str]) -> str:
    """Emit one function declaration + N trigger blocks for ``tables``.

    The function lives once per migration (CREATE OR REPLACE — idempotent),
    and each table gets its own ``CREATE OR REPLACE TRIGGER`` block via
    :func:`noctusai_lib.sql.updated_at_trigger` with
    ``include_function=False`` so the function is declared exactly once.
    """
    sections: list[str] = [
        "-- ----- updated_at auto-touch (function + per-table triggers) -----",
        # First trigger emission carries the function declaration.
        sql_updated_at_trigger(tables[0], schema=schema),
    ]
    # Subsequent triggers reuse the function declared above.
    for table in tables[1:]:
        sections.append(
            sql_updated_at_trigger(table, schema=schema, include_function=False)
        )
    return "\n\n".join(sections)


def _build_sql(
    *,
    migration_name: str,
    schema: str,
    with_table: str | None,
    with_updated_at: list[str] | None,
    today_str: str,
) -> str:
    """Build the full SQL body for the new migration file."""
    header = (
        f"-- Migration: {migration_name}\n"
        f"-- Generated by noctus.dev.scaffold_migration on {today_str}\n"
        f"-- Schema: {schema}\n"
    )
    # `noctusai_lib.sql.prelude` bundles the schema-lock with a why-block
    # (RLS isolation, cross-product safety) and a trailing newline. Strip
    # the trailing newline here because we re-join with `\n\n` below.
    prelude = sql_prelude(schema).rstrip("\n")
    helpers_comment = (
        "-- =======================================================\n"
        "-- TODO: Add your DDL here. Patterns available:\n"
        "--   updated_at_function(schema)     -- emit once per schema\n"
        "--   updated_at_trigger(schema, table) -- per table that has updated_at\n"
        "--   rls_subquery_policy(table, ...)  -- per RLS-enabled table\n"
        "-- See seed/lib/backend/noctusai_lib/domain/sql_templates.py\n"
        "-- ======================================================="
    )

    parts = [header, prelude, helpers_comment]
    if with_table:
        parts.append(_build_with_table_block(schema, with_table))
    if with_updated_at:
        parts.append(_build_updated_at_block(schema, with_updated_at))
    return "\n\n".join(parts) + "\n"


def scaffold_migration(
    product_slug: str,
    migration_name: str,
    *,
    schema: str | None = None,
    with_table: str | None = None,
    with_updated_at: list[str] | None = None,
    products_dir: Path | None = None,
) -> dict:
    """Emit the next-numbered migration SQL file for ``<product_slug>``.

    Args:
        product_slug: Product directory name under ``products/`` (e.g.
            ``youtube-crawler``, ``personal-finance``).
        migration_name: Snake-case-ish suffix for the file (e.g.
            ``oauth_credentials``). Used in the filename + header comment.
        schema: Schema name to bind ``set_search_path`` and emit table DDL
            against. Defaults to ``product_slug.replace("-", "_")``.
        with_table: Optional table name. When set, the emitted SQL includes
            a ``CREATE TABLE IF NOT EXISTS`` skeleton + idempotent
            ``updated_at_function`` + ``updated_at_trigger`` + a
            ``rls_subquery_policy`` stub. Convenient for the common case
            "add a new table".
        with_updated_at: Optional list of table names. When set, appends
            an ``updated_at`` function + per-table BEFORE-UPDATE trigger
            block via :func:`noctusai_lib.sql.updated_at_trigger`. The
            function is declared exactly once (CREATE OR REPLACE — idempotent),
            triggers attach to each named table. Convenient when adding
            ``updated_at`` auto-touch to several existing tables in one
            migration.
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to the module-level :data:`PRODUCTS_DIR` from
            ``settings``. Tests pass tmp_path-based dirs; the MCP tool
            registration leaves it as None so the seed-aware default wins.

    Returns ``{"created": True, "path": str, "number": int, "schema": str}``
    on success, or ``{"error": str}`` on failure. NEVER raises — the caller
    (MCP server) is meant to surface the error string verbatim.
    """
    if not product_slug:
        return {"error": "product_slug must be a non-empty string"}
    if not migration_name:
        return {"error": "migration_name must be a non-empty string"}
    if with_updated_at is not None:
        if not isinstance(with_updated_at, list):
            return {
                "error": (
                    "with_updated_at must be a list of table names, "
                    f"got {type(with_updated_at).__name__}"
                )
            }
        if any(not isinstance(t, str) or not t.strip() for t in with_updated_at):
            return {
                "error": "with_updated_at entries must be non-empty strings"
            }

    base_products_dir = products_dir if products_dir is not None else PRODUCTS_DIR

    product_dir = base_products_dir / product_slug
    if not product_dir.is_dir():
        return {
            "error": (
                f"Product '{product_slug}' not found at {product_dir}. "
                f"Scaffold the product first via noctus.dev.scaffold_product."
            )
        }

    migrations_dir = _migrations_dir(product_slug, base_products_dir)
    if not migrations_dir.is_dir():
        return {
            "error": (
                f"Product '{product_slug}' has no backend/migrations/ directory "
                f"(expected at {migrations_dir}). Scaffold the product first via "
                f"noctus.dev.scaffold_product — it ships 001_seed.sql."
            )
        }

    next_n = _next_number(migrations_dir)
    if next_n is None:
        return {
            "error": (
                f"Product '{product_slug}' has an empty migrations/ directory. "
                f"Scaffold the product first via noctus.dev.scaffold_product — "
                f"it ships 001_seed.sql, after which subsequent migrations land "
                f"via this tool."
            )
        }

    resolved_schema = schema if schema is not None else _slug_to_default_schema(product_slug)
    if not resolved_schema:
        return {"error": "Resolved schema is empty (slug derived to '')"}

    filename = f"{_format_number(next_n)}_{migration_name}.sql"
    target = migrations_dir / filename
    if target.exists():
        # Defensive — _next_number already advances past the highest NN, so
        # this should be unreachable unless something raced us. Surface it
        # explicitly rather than silently overwriting (no-silent-errors rule).
        return {"error": f"Refusing to overwrite existing file at {target}"}

    sql_body = _build_sql(
        migration_name=migration_name,
        schema=resolved_schema,
        with_table=with_table,
        with_updated_at=with_updated_at,
        today_str=date.today().isoformat(),
    )

    try:
        target.write_text(sql_body)
    except OSError as exc:
        logger.warning("scaffold_migration: cannot write %s (%s)", target, exc)
        return {"error": f"Failed to write {target}: {exc}"}

    logger.info(
        "scaffold_migration: created %s (schema=%s, with_table=%s)",
        target,
        resolved_schema,
        with_table,
    )
    return {
        "created": True,
        "path": str(target),
        "number": next_n,
        "schema": resolved_schema,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_migration",
        description=(
            "Emit the next-numbered migration SQL file for a product, "
            "pre-wired with set_search_path / updated_at / RLS helpers from "
            "noctusai_lib.domain.sql_templates."
        ),
    )
    def _scaffold_migration(
        product_slug: str,
        migration_name: str,
        schema: str | None = None,
        with_table: str | None = None,
        with_updated_at: list[str] | None = None,
    ) -> dict:
        return scaffold_migration(
            product_slug,
            migration_name,
            schema=schema,
            with_table=with_table,
            with_updated_at=with_updated_at,
        )
