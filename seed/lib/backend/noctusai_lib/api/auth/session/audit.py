"""``ApiTokenAuditWriter`` — best-effort audit trail for resolved
product-token calls (SEED-1, contract §B.0: "every resolved
product-token call writes ``api_token_audit(api_token_id, org_id,
method, path, status, at)``, best-effort and logged loudly on
failure").

Seed IO module — ships Protocol + Fake + Real + factory (no half-ship;
``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Like the
resolver's ``last_used_at`` bump, an audit-write failure MUST NOT break
the request it's auditing — the ``SupabaseApiTokenAuditWriter`` never
raises; it logs loudly (``logger.exception``) and returns.

**Wiring note.** This module ships the writer itself. Composing it
into a live call site needs the RESPONSE status code, which is only
known after the route handler runs (i.e. ASGI middleware, not a plain
``Depends(...)`` alongside ``get_auth_context``) — no product wires
this yet; a future slice adds the middleware once a route consumes it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_TABLE = "api_token_audit"


class ApiTokenAuditWriter(Protocol):
    """Records one resolved product-token call. Never raises — a
    concrete impl swallows its own IO failures (see module docstring)."""

    async def record(
        self,
        *,
        api_token_id: UUID,
        org_id: UUID,
        method: str,
        path: str,
        status: int,
    ) -> None:
        ...


class FakeApiTokenAuditWriter:
    """In-memory recorder — tests assert on ``.records``."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        api_token_id: UUID,
        org_id: UUID,
        method: str,
        path: str,
        status: int,
    ) -> None:
        self.records.append(
            {
                "api_token_id": api_token_id,
                "org_id": org_id,
                "method": method,
                "path": path,
                "status": status,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )


class SupabaseApiTokenAuditWriter:
    """Best-effort ``INSERT`` into ``<schema>.api_token_audit``.

    Args:
        admin_client: A supabase client built with the service-role
            key — the audit table's ``service_role_bypass`` RLS policy
            is what this client relies on (there is no user-scoped
            write path for an audit trail).
        schema: The product's own Postgres schema.
    """

    def __init__(self, admin_client: Any, *, schema: str) -> None:
        self._sb = admin_client
        self._schema = schema

    async def record(
        self,
        *,
        api_token_id: UUID,
        org_id: UUID,
        method: str,
        path: str,
        status: int,
    ) -> None:
        try:
            (
                self._sb.schema(self._schema)
                .table(_TABLE)
                .insert(
                    {
                        "api_token_id": str(api_token_id),
                        "org_id": str(org_id),
                        "method": method,
                        "path": path,
                        "status": status,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .execute()
            )
        except Exception:
            logger.exception(
                "api_token_audit_write_failed schema=%s api_token_id=%s "
                "org_id=%s method=%s path=%s status=%s",
                self._schema,
                api_token_id,
                org_id,
                method,
                path,
                status,
            )


def make_api_token_audit_writer(
    admin_client: Optional[Any] = None,
    *,
    schema: Optional[str] = None,
) -> ApiTokenAuditWriter:
    """Return the appropriate writer for the environment.

    Args:
        admin_client: The product's admin Supabase client. When
            ``None`` (dev/test — no DB configured), returns the
            in-memory Fake regardless of ``schema``.
        schema: The product's own schema. Required alongside
            ``admin_client`` to build the Real adapter.

    Returns:
        ``SupabaseApiTokenAuditWriter`` when both ``admin_client`` and
        ``schema`` are given; ``FakeApiTokenAuditWriter()`` otherwise.
    """
    if admin_client is not None and schema:
        return SupabaseApiTokenAuditWriter(admin_client, schema=schema)
    return FakeApiTokenAuditWriter()


__all__ = [
    "ApiTokenAuditWriter",
    "FakeApiTokenAuditWriter",
    "SupabaseApiTokenAuditWriter",
    "make_api_token_audit_writer",
]
