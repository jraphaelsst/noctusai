"""Authoring-time helpers for canonical SQL DDL the platform reuses.

Pure string emission — no IO, no DB access. Use these in migration files
and the scaffold tool so the SECURITY DEFINER / search_path / updated_at /
RLS subquery conventions can't drift across products.

The shapes here mirror what every product schema currently authors by
hand. They are *authoring-time* helpers — existing migration files are
authoritative replay logs and MUST stay verbatim per the
"MCP migrations mirror the file" rule. Use these in:
- New migrations being authored fresh.
- The product-scaffold tool that bootstraps a new product's schema.

Adopted 2026-05-01 by `projects/sql-templates-absorption/` (Wave A of
the first-batch absorptions queue).
"""
from __future__ import annotations

from typing import Iterable


def set_search_path(*schemas: str) -> str:
    """Emit ``SET search_path = <schemas>, public`` — schema-lock prelude.

    Used inside a SECURITY DEFINER function declaration to pin name
    resolution. Always trails with ``, public`` automatically because
    every adopter follows that convention.

        >>> set_search_path("erp")
        'SET search_path = erp, public'
        >>> set_search_path("therapy", "core")
        'SET search_path = therapy, core, public'

    Raises ``ValueError`` if no schema is provided — calling
    ``set_search_path()`` with no args is always a bug.
    """
    if not schemas:
        raise ValueError("set_search_path requires at least one schema")
    parts = [*schemas, "public"]
    return f"SET search_path = {', '.join(parts)}"


def updated_at_function(
    schema: str,
    function_name: str = "set_updated_at",
) -> str:
    """Emit the canonical auto-touch helper function for ``<schema>``.

    Every schema needs exactly one of these — invoked by every
    ``BEFORE UPDATE`` trigger that wants ``updated_at`` to track the
    last modification. The function is SECURITY DEFINER + search-path
    locked so it works correctly when called by RLS-enforced clients.

        >>> print(updated_at_function("erp"))
        CREATE OR REPLACE FUNCTION erp.set_updated_at()
        RETURNS TRIGGER
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
        AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

    The default ``function_name="set_updated_at"`` matches therapy /
    daily-life / personal-finance / mailing. ERP's first migration
    used ``update_updated_at_column`` — pass it explicitly there.
    """
    return (
        f"CREATE OR REPLACE FUNCTION {schema}.{function_name}()\n"
        f"RETURNS TRIGGER\n"
        f"LANGUAGE plpgsql SECURITY DEFINER SET search_path = {schema}, public\n"
        f"AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;"
    )


def updated_at_trigger(
    schema: str,
    table: str,
    function_name: str = "set_updated_at",
    trigger_name: str | None = None,
) -> str:
    """Emit a ``BEFORE UPDATE`` trigger that calls ``<schema>.<function_name>``.

    ``trigger_name`` defaults to ``set_updated_at_<table>`` (the
    convention every adopter follows). Override only when the table
    name collides with a reserved identifier or the schema-wide
    naming convention demands something else.

        >>> print(updated_at_trigger("therapy", "clinics"))
        CREATE OR REPLACE TRIGGER set_updated_at_clinics
            BEFORE UPDATE ON therapy.clinics
            FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();
    """
    name = trigger_name or f"set_updated_at_{table}"
    return (
        f"CREATE OR REPLACE TRIGGER {name}\n"
        f"    BEFORE UPDATE ON {schema}.{table}\n"
        f"    FOR EACH ROW EXECUTE FUNCTION {schema}.{function_name}();"
    )


def rls_subquery_policy(
    schema: str,
    table: str,
    policy_name: str,
    command: str,
    using: str | None = None,
    with_check: str | None = None,
    to_role: str = "authenticated",
) -> str:
    """Emit a ``CREATE POLICY`` that uses the ``(SELECT auth.uid())`` subquery shape.

    Why subquery? Postgres planner evaluates ``(SELECT auth.uid())``
    once per query, not per row — meaningful speedup on large tables.
    Plain ``auth.uid()`` re-evaluates per row. This is the platform
    standard documented in ``KB § PATTERNS/database-rls.md``.

    Args:
        schema: Schema-qualifying the table (``erp``, ``therapy``, …).
        table: Table name within the schema.
        policy_name: Name of the policy. Quoted in output.
        command: One of ``SELECT``, ``INSERT``, ``UPDATE``, ``DELETE``,
            ``ALL``. Case-insensitive.
        using: ``USING`` clause body (without the keyword). Required
            for SELECT/UPDATE/DELETE/ALL; optional for INSERT.
        with_check: ``WITH CHECK`` clause body. Required for
            INSERT/UPDATE; optional for ALL.
        to_role: Role the policy applies to. Defaults to
            ``authenticated`` — the platform default. Pass
            ``"anon"`` for a deny-policy on unauthenticated traffic.

    Caller is responsible for using the canonical subquery shape in
    the ``using`` / ``with_check`` strings. Example:

        >>> print(rls_subquery_policy(
        ...     "erp", "metas", "metas_select", "SELECT",
        ...     using="(SELECT auth.uid()) = usuario_id",
        ... ))
        CREATE POLICY "metas_select" ON erp.metas FOR SELECT TO authenticated
          USING ((SELECT auth.uid()) = usuario_id);
    """
    cmd = command.strip().upper()
    valid = {"SELECT", "INSERT", "UPDATE", "DELETE", "ALL"}
    if cmd not in valid:
        raise ValueError(
            f"command must be one of {sorted(valid)}; got {command!r}"
        )
    if using is None and with_check is None:
        raise ValueError(
            "rls_subquery_policy needs at least one of `using` or `with_check`"
        )
    if cmd == "INSERT" and with_check is None:
        raise ValueError("INSERT policies require `with_check`")
    if cmd in {"SELECT", "DELETE"} and using is None:
        raise ValueError(f"{cmd} policies require `using`")

    lines = [f'CREATE POLICY "{policy_name}" ON {schema}.{table} FOR {cmd} TO {to_role}']
    if using is not None:
        lines.append(f"  USING ({using})")
    if with_check is not None:
        # Append `WITH CHECK` to the previous line if no USING, otherwise on its own line.
        suffix = f"  WITH CHECK ({with_check})"
        lines.append(suffix)
    return "\n".join(lines) + ";"
