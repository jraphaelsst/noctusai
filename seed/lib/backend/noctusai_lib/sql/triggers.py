"""``updated_at`` trigger emission — one-call function + trigger pair.

The canonical pattern (28 instances across 5 products as of the
2026-05-09 audit) is:

1. Declare ``<schema>.set_updated_at()`` once per migration (re-running
   is safe — the helper uses ``CREATE OR REPLACE FUNCTION``).
2. For each table needing the auto-touch, attach a BEFORE-UPDATE
   trigger that calls that function.

This module exposes :func:`updated_at_trigger` as a single-call
convenience that emits BOTH parts. For finer control (multiple tables
sharing one function declaration in the same file), call
:func:`updated_at_function` once and :func:`updated_at_trigger` per
table — the public surface mirrors
:mod:`noctusai_lib.domain.sql_templates` so consumers can compose freely.

The function name defaults to ``set_updated_at`` (matches therapy /
daily-life / personal-finance / mailing). ERP's earliest migration used
``update_updated_at_column``; pass ``function_name=`` explicitly there.

Idempotency:

- The function declaration uses ``CREATE OR REPLACE FUNCTION`` (always
  safe to re-run — converges to the same body per schema).
- The trigger uses ``CREATE OR REPLACE TRIGGER`` (Postgres 14+; matches
  every adopter's current shape).

Both helpers delegate to
:mod:`noctusai_lib.domain.sql_templates` for the canonical strings.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import (
    updated_at_function as _canonical_function,
    updated_at_trigger as _canonical_trigger,
)


def updated_at_function(schema: str, *, function_name: str = "set_updated_at") -> str:
    """Emit ``CREATE OR REPLACE FUNCTION <schema>.<function_name>()``.

    Wraps :func:`noctusai_lib.domain.sql_templates.updated_at_function`
    with a kwarg-only ``function_name`` to match the
    :func:`updated_at_trigger` signature in this module.

    Args:
        schema: Schema the function is declared in (e.g. ``"erp"``).
        function_name: Defaults to ``"set_updated_at"`` (the platform
            default). Pass ``"update_updated_at_column"`` for fresh
            ERP migrations that want to match the legacy adopter name.

    Returns:
        A multi-line string ending without a trailing newline (callers
        compose with ``"\\n"``-joined sections).
    """
    if not schema or not schema.strip():
        raise ValueError("updated_at_function requires a non-empty schema")
    return _canonical_function(schema, function_name=function_name)


def updated_at_trigger(
    table: str,
    *,
    schema: str | None = None,
    function_name: str = "set_updated_at",
    trigger_name: str | None = None,
    include_function: bool = True,
) -> str:
    """Emit the BEFORE-UPDATE trigger (and optionally its function) for ``table``.

    Args:
        table: Table name within ``schema`` (e.g. ``"posts"``).
        schema: Schema-qualifying the table. Defaults to ``"public"``
            because that matches the few migrations that don't use a
            product-private schema; pass the product schema for every
            real adopter (``"erp"``, ``"personal-finance"``, …).
        function_name: Auto-touch function name. Defaults to
            ``"set_updated_at"``. ERP legacy migrations use
            ``"update_updated_at_column"`` — pass it explicitly there.
        trigger_name: Override the default trigger name
            (``"set_updated_at_<table>"``). Same default as
            :func:`noctusai_lib.domain.sql_templates.updated_at_trigger`.
        include_function: When True (default), prepends the
            ``CREATE OR REPLACE FUNCTION`` declaration so the result is
            self-contained — re-running the migration is safe. Set
            False when emitting multiple triggers in the same file
            and you've already declared the function once at the top.

    Returns:
        A multi-line string with (optionally) the function declaration
        followed by a blank line, then the trigger declaration. No
        trailing newline.

    Example::

        >>> from noctusai_lib.sql import updated_at_trigger
        >>> out = updated_at_trigger("posts", schema="blog")
        >>> "CREATE OR REPLACE FUNCTION blog.set_updated_at()" in out
        True
        >>> "BEFORE UPDATE ON blog.posts" in out
        True
    """
    if not table or not table.strip():
        raise ValueError("updated_at_trigger requires a non-empty table")

    resolved_schema = schema if schema is not None else "public"
    if not resolved_schema or not resolved_schema.strip():
        raise ValueError("updated_at_trigger requires a non-empty schema")

    trigger_sql = _canonical_trigger(
        resolved_schema,
        table,
        function_name=function_name,
        trigger_name=trigger_name,
    )

    if not include_function:
        return trigger_sql

    function_sql = _canonical_function(resolved_schema, function_name=function_name)
    return f"{function_sql}\n\n{trigger_sql}"
