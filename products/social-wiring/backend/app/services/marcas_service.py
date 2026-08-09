"""Per-org marcas CRUD service.

Provides CRUD over ``social_wiring.marcas`` — a MARCA is a brand / profile
whose social accounts are connected (One Consultoria, João Raphael). No
Fernet: marcas are metadata only (no credential blob). Mirrors the shape of
``IntegrationAccountService`` but simpler: no encryption, no default-flag
semantics.

The entity was produced by migration 007 (folding in ``mc_brand_owners``,
the branding-catalog agency layer) under the name ``clients``, and RENAMED
to ``marcas`` by migration 046 — see
``project-history/roadmaps/lead-card-hub-2026-08.md`` Phase 0. The name had
to be freed because ``clientes`` now means the PERSON entity (the lead a
Funil card is about), and two tables one letter apart meaning two unrelated
things is a permanent reading hazard.

🔴 A marca has NOTHING to do with an OAuth ``client_id``. That name survives
untouched elsewhere in this product (``settings.google_oauth_client_id``,
``settings.youtube_client_id``) and must never be folded into this rename.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

__all__ = [
    "Marca",
    "MarcaService",
    "MarcaNotFound",
    "build_marca_service",
]

_SCHEMA = "social_wiring"
_TABLE = "marcas"


@dataclass(frozen=True)
class Marca:
    """Public representation of a social_wiring.marcas row."""

    id: UUID
    org_id: UUID
    slug: str
    name: str
    kind: str
    notes: Optional[str]
    created_at: Any
    updated_at: Any


class MarcaNotFound(Exception):
    """Raised when a marca row doesn't exist or isn't owned by the org."""


class MarcaService:
    """CRUD over ``social_wiring.marcas``. Backed by an admin / service-role
    Supabase client; every query filters ``org_id`` explicitly (defense in
    depth on top of RLS)."""

    def __init__(self, client: Any):
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _row_to_marca(self, row: dict) -> Marca:
        return Marca(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            slug=row["slug"],
            name=row["name"],
            kind=row.get("kind") or "real_estate_agent",
            notes=row.get("notes"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _require_row(self, marca_id: UUID, org_id: UUID) -> dict:
        """Fetch a row owner-scoped or raise ``MarcaNotFound``."""
        resp = (
            self._table()
            .select("*")
            .eq("id", str(marca_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise MarcaNotFound(
                f"marca {marca_id} not found for org {org_id}"
            )
        return rows[0]

    # ─── CRUD ─────────────────────────────────────────────────────────

    def list_marcas(self, org_id: UUID) -> list[Marca]:
        """List all marcas for an org, ordered by name."""
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .order("name")
            .execute()
        )
        return [self._row_to_marca(r) for r in (resp.data or [])]

    def get_marca(self, marca_id: UUID, org_id: UUID) -> Optional[Marca]:
        """Fetch one marca or return None if not found / wrong org."""
        try:
            row = self._require_row(marca_id, org_id)
            return self._row_to_marca(row)
        except MarcaNotFound:
            return None

    def create_marca(
        self,
        org_id: UUID,
        slug: str,
        name: str,
        kind: str = "real_estate_agent",
        notes: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> Marca:
        """Create a new marca row."""
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
            raise RuntimeError("marcas insert returned no data")
        return self._row_to_marca(rows[0])

    def update_marca(
        self,
        marca_id: UUID,
        org_id: UUID,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        kind: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Marca:
        """Patch name / slug / kind / notes. All fields optional."""
        self._require_row(marca_id, org_id)

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
            return self._row_to_marca(self._require_row(marca_id, org_id))

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = (
            self._table()
            .update(updates)
            .eq("id", str(marca_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise MarcaNotFound(
                f"marca {marca_id} not found for org {org_id}"
            )
        return self._row_to_marca(rows[0])

    def delete_marca(self, marca_id: UUID, org_id: UUID) -> bool:
        """Delete a marca. Returns True if deleted, False if not found."""
        resp = (
            self._table()
            .delete()
            .eq("id", str(marca_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        deleted = resp.data or []
        return len(deleted) > 0


def build_marca_service(admin_client: Any) -> MarcaService:
    """Build a ``MarcaService`` wired to the given Supabase admin client.

    DI seam: tests inject a SQLiteClient; production passes the admin
    Supabase client. No encryption — marcas are metadata only.
    """
    return MarcaService(admin_client)
