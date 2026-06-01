"""Per-org clients CRUD service.

Provides CRUD over ``social_wiring.clients``. No Fernet — clients are
metadata only (no credential blob). Mirrors the shape of
``IntegrationAccountService`` but simpler: no encryption, no default-flag
semantics.

``clients`` is the canonical entity produced by migration 007 which folds
in ``mc_brand_owners`` (the branding-catalog agency layer). The compat view
``mc_brand_owners`` re-routes callers that still read the old table name.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

__all__ = [
    "Client",
    "ClientService",
    "ClientNotFound",
    "build_client_service",
]

_SCHEMA = "social_wiring"
_TABLE = "clients"


@dataclass(frozen=True)
class Client:
    """Public representation of a social_wiring.clients row."""

    id: UUID
    org_id: UUID
    slug: str
    name: str
    kind: str
    notes: Optional[str]
    created_at: Any
    updated_at: Any


class ClientNotFound(Exception):
    """Raised when a client row doesn't exist or isn't owned by the org."""


class ClientService:
    """CRUD over ``social_wiring.clients``. Backed by an admin / service-role
    Supabase client; every query filters ``org_id`` explicitly (defense in
    depth on top of RLS)."""

    def __init__(self, client: Any):
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _row_to_client(self, row: dict) -> Client:
        return Client(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            slug=row["slug"],
            name=row["name"],
            kind=row.get("kind") or "real_estate_agent",
            notes=row.get("notes"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _require_row(self, client_id: UUID, org_id: UUID) -> dict:
        """Fetch a row owner-scoped or raise ``ClientNotFound``."""
        resp = (
            self._table()
            .select("*")
            .eq("id", str(client_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise ClientNotFound(
                f"client {client_id} not found for org {org_id}"
            )
        return rows[0]

    # ─── CRUD ─────────────────────────────────────────────────────────

    def list_clients(self, org_id: UUID) -> list[Client]:
        """List all clients for an org, ordered by name."""
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .order("name")
            .execute()
        )
        return [self._row_to_client(r) for r in (resp.data or [])]

    def get_client(self, client_id: UUID, org_id: UUID) -> Optional[Client]:
        """Fetch one client or return None if not found / wrong org."""
        try:
            row = self._require_row(client_id, org_id)
            return self._row_to_client(row)
        except ClientNotFound:
            return None

    def create_client(
        self,
        org_id: UUID,
        slug: str,
        name: str,
        kind: str = "real_estate_agent",
        notes: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> Client:
        """Create a new client row."""
        row_id = str(uuid4())
        data: dict = {
            "id": row_id,
            "org_id": str(org_id),
            "slug": slug.strip(),
            "name": name.strip(),
            "kind": kind,
        }
        if notes is not None:
            data["notes"] = notes
        if created_by is not None:
            data["created_by"] = str(created_by)

        resp = self._table().insert(data).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError("clients insert returned no data")
        return self._row_to_client(rows[0])

    def update_client(
        self,
        client_id: UUID,
        org_id: UUID,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        kind: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Client:
        """Patch name / slug / kind / notes. All fields optional."""
        self._require_row(client_id, org_id)

        updates: dict = {}
        if name is not None:
            updates["name"] = name.strip()
        if slug is not None:
            updates["slug"] = slug.strip()
        if kind is not None:
            updates["kind"] = kind
        if notes is not None:
            updates["notes"] = notes

        if not updates:
            return self._row_to_client(self._require_row(client_id, org_id))

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = (
            self._table()
            .update(updates)
            .eq("id", str(client_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise ClientNotFound(
                f"client {client_id} not found for org {org_id}"
            )
        return self._row_to_client(rows[0])

    def delete_client(self, client_id: UUID, org_id: UUID) -> bool:
        """Delete a client. Returns True if deleted, False if not found."""
        resp = (
            self._table()
            .delete()
            .eq("id", str(client_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        deleted = resp.data or []
        return len(deleted) > 0


def build_client_service(admin_client: Any) -> ClientService:
    """Build a ``ClientService`` wired to the given Supabase admin client.

    DI seam: tests inject a SQLiteClient; production passes the admin
    Supabase client. No encryption — clients are metadata only.
    """
    return ClientService(admin_client)
