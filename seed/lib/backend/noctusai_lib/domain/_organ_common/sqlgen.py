"""SQL generators shared by the organ migrations (authoring-time, pure string emission)."""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import rls_subquery_policy, service_role_bypass


def org_rls(schema: str, table: str, org_id_expr: str, *, grants: bool = False, authenticated_select: bool = True) -> str:
    """RLS on + own-org SELECT for `authenticated` + `service_role_bypass` (+ explicit GRANTs when `grants`).

    `authenticated_select=False` is for tables that carry a person's document (CPF/CNPJ): the backend reads them
    through the service role, so a direct `authenticated` read path (PostgREST with the user's JWT) would only be a way
    around the per-role masking the API applies. No SELECT policy, and the table's privileges are revoked from
    `anon` / `authenticated` (re-runnable: a previously-granted table is closed on the next apply).
    """
    select_name = f"{table}_select_own_org"
    lines = [f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;", f'DROP POLICY IF EXISTS "{select_name}" ON {schema}.{table};']
    if authenticated_select:
        lines.append(rls_subquery_policy(schema, table, select_name, "SELECT", using=f"org_id = (SELECT {org_id_expr})"))
    lines += [f'DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{table};', service_role_bypass(table, schema=schema)]
    if not authenticated_select:
        lines.append(f"REVOKE ALL ON {schema}.{table} FROM PUBLIC, anon, authenticated;")
    if grants:
        if authenticated_select:
            lines.append(f"GRANT SELECT ON {schema}.{table} TO authenticated;")
        lines.append(f"GRANT ALL ON {schema}.{table} TO service_role;")
    return "\n".join(lines)


def definer_search_path(schema: str) -> str:
    """The `search_path` of a SECURITY DEFINER function / trigger: `pg_catalog` FIRST, `pg_temp` LAST.

    `sql_templates.set_search_path` (`<schema>, public`) is a session prelude for a migration script;
    a definer function must never resolve an operator or function through a writable schema ahead
    of `pg_catalog`, so every organ's definer SQL goes through this one.
    """
    if not schema or not schema.strip():
        raise ValueError("definer_search_path requires a non-empty schema")
    return f"SET search_path = pg_catalog, {schema}, pg_temp"


__all__ = ["definer_search_path", "org_rls"]
