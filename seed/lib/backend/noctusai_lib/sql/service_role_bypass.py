"""``service_role_bypass`` policy emitter — single-table canonical shape.

The canonical pattern (40+ instances in
``products/therapy-platform/backend/migrations/001_therapy_platform.sql:846+``
plus the per-table policies the audit
(`projects/keeper-trio-platform-triage/phase-0-triage.md`) identified
across core / erp / mailing / pf) is:

    CREATE POLICY "service_role_bypass" ON <schema>.<table>
        FOR ALL TO service_role
        USING (true) WITH CHECK (true);

Every product backend uses the Supabase ``service_role`` JWT through
``get_admin_client()``. The JWT bypasses RLS at the connection level, so
runtime is fine even without the explicit policy. But the platform's
``check_admin_endpoint_service_role_bypass`` keeper detector looks for a
policy whose *literal name* is ``service_role_bypass`` — equivalently-
shaped policies under a different name are flagged as defense-in-depth
gaps. **The literal name is what closes the keeper finding.** Renaming
the policy in a future cleanup pass re-opens every finding for that
table.

The helper here delegates to
:func:`noctusai_lib.domain.sql_templates.service_role_bypass` so the
canonical string has a single source of truth. Drift would surface as a
test failure here AND in ``test_sql_templates.py`` simultaneously.

Use in fresh migrations alongside :func:`prelude` and
:func:`updated_at_trigger`::

    from noctusai_lib.sql import prelude, updated_at_trigger, service_role_bypass

    body = "\\n".join([
        prelude("erp"),
        updated_at_trigger("clientes", schema="erp"),
        "",
        service_role_bypass("clientes", schema="erp"),
        service_role_bypass("contratos", schema="erp"),
    ])
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import (
    service_role_bypass as _canonical_service_role_bypass,
)


def service_role_bypass(table: str, schema: str = "public") -> str:
    """Return the canonical ``service_role_bypass`` policy SQL for one table.

    Thin wrapper over
    :func:`noctusai_lib.domain.sql_templates.service_role_bypass`.

    Args:
        table: Table name within ``schema`` (e.g. ``"clinics"``).
        schema: Schema-qualifying the table. Defaults to ``"public"``.
            Pass the product schema for every real adopter (``"therapy"``,
            ``"erp"``, ``"mailing"``, ``"personal-finance"``, ...). The
            schema string passes through unchanged; Postgres-quoting for
            dashed schema names is the caller's responsibility.

    Returns:
        A single-line ``CREATE POLICY`` string terminated with ``;``. No
        trailing newline — callers compose with ``"\\n"``-joined sections.

    Example::

        >>> from noctusai_lib.sql import service_role_bypass
        >>> service_role_bypass("clinics", schema="therapy")
        'CREATE POLICY "service_role_bypass" ON therapy.clinics FOR ALL TO service_role USING (true) WITH CHECK (true);'

    Raises:
        ValueError: If ``table`` or ``schema`` is empty / all-whitespace
            (propagated from the canonical implementation).
    """
    if not table or not table.strip():
        raise ValueError("service_role_bypass requires a non-empty table")
    if not schema or not schema.strip():
        raise ValueError("service_role_bypass requires a non-empty schema")
    return _canonical_service_role_bypass(table, schema=schema)
