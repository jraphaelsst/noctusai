"""Top-of-migration prelude — schema-lock + comment block.

The canonical schema-lock is ``SET search_path = '<schema>', public;``
emitted at the very top of every product migration. The audit
(2026-05-09) found this exact line recurring 100 times across 9/9
products — every migration writes its own copy.

This module wraps the canonical
:func:`noctusai_lib.domain.sql_templates.set_search_path` with a brief
comment block explaining the why, so a fresh migration looks like::

    -- ============================================================
    -- Schema lock — pin name resolution to <schema>, public
    -- WHY:
    --   * RLS isolation: every product's tables live in its own
    --     schema; un-locked search_path leaks resolution to whatever
    --     the caller's session set.
    --   * Cross-product safety: prevents accidental shadowing when
    --     two products define identically-named helpers (e.g.
    --     `current_org_id()`) in different schemas.
    -- IDEMPOTENT: session-level setting; no DDL emitted.
    -- ============================================================
    SET search_path = <schema>, public;

The string the helper returns is verbatim what to drop into a new
migration file — comment block, blank line, schema-lock, trailing
newline.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import set_search_path


def prelude(schema: str) -> str:
    """Return the top-of-migration prelude string for ``schema``.

    Args:
        schema: The schema this migration is authored against (e.g.
            ``"erp"``, ``"personal-finance"``, ``"daily_life"``). Passed
            through to
            :func:`noctusai_lib.domain.sql_templates.set_search_path`
            unchanged — the caller is responsible for quoting if the
            schema name contains a hyphen (Postgres requires it).

    Returns:
        A string containing a comment block + blank line + schema-lock
        + trailing newline. Drop verbatim at the top of a new migration.

    Example::

        >>> from noctusai_lib.sql import prelude
        >>> body = prelude("daily_life")
        >>> body.startswith("--")
        True
        >>> "SET search_path = daily_life, public;" in body
        True

    Raises:
        ValueError: If ``schema`` is empty or all-whitespace —
            propagated from
            :func:`noctusai_lib.domain.sql_templates.set_search_path`.
    """
    if not schema or not schema.strip():
        raise ValueError("prelude requires a non-empty schema")

    schema_lock = f"{set_search_path(schema)};"
    comment_block = (
        "-- ============================================================\n"
        f"-- Schema lock — pin name resolution to {schema}, public\n"
        "-- WHY:\n"
        "--   * RLS isolation: every product's tables live in its own\n"
        "--     schema; un-locked search_path leaks resolution to\n"
        "--     whatever the caller's session set.\n"
        "--   * Cross-product safety: prevents accidental shadowing\n"
        "--     when two products define identically-named helpers\n"
        "--     (e.g. `current_org_id()`) in different schemas.\n"
        "-- IDEMPOTENT: session-level setting; no DDL emitted.\n"
        "-- ============================================================"
    )
    return f"{comment_block}\n{schema_lock}\n"
