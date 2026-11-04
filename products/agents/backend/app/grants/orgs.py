"""The org directory a platform admin picks the target org from (CONTRACT D2: agent -> product -> org).

Orgs live in core (``public.organizations``); agents reads them with the ``public``-schema client it already uses
for ``noctus_users`` (``app.dependencies.get_core_client``). Seed IO shape: Protocol + Fake + Supabase + factory.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = ["FakeOrgDirectory", "OrgDirectory", "OrgRef", "SupabaseOrgDirectory", "get_org_directory", "ORG_LIST_MAX"]

#: Hard cap of one options page (the picker searches by name; it never needs the whole fleet at once).
ORG_LIST_MAX = 200


@dataclass(frozen=True)
class OrgRef:
    id: UUID
    nome: str
    slug: str | None = None


class OrgDirectory(Protocol):
    def search(self, q: str | None = None, *, limit: int = 50) -> list[OrgRef]:
        """Orgs by name (case-insensitive substring), ordered by name, at most ``limit`` (<= :data:`ORG_LIST_MAX`)."""
        ...

    def get(self, org_id: UUID) -> OrgRef | None:
        ...


def _clamp(limit: int) -> int:
    return max(1, min(int(limit), ORG_LIST_MAX))


class FakeOrgDirectory:
    def __init__(self, orgs: list[OrgRef] | None = None) -> None:
        self.orgs = list(orgs or [])

    def search(self, q: str | None = None, *, limit: int = 50) -> list[OrgRef]:
        needle = (q or "").strip().lower()
        rows = [o for o in self.orgs if needle in o.nome.lower()]
        return sorted(rows, key=lambda o: o.nome.lower())[: _clamp(limit)]

    def get(self, org_id: UUID) -> OrgRef | None:
        return next((o for o in self.orgs if o.id == org_id), None)


def _ref(row: dict[str, Any]) -> OrgRef:
    return OrgRef(id=UUID(str(row["id"])), nome=row.get("nome") or "", slug=row.get("slug"))


class SupabaseOrgDirectory:
    """Real directory over the core (``public``) client."""

    def __init__(self, core_client: Any) -> None:
        self._client = core_client

    def search(self, q: str | None = None, *, limit: int = 50) -> list[OrgRef]:
        query = self._client.table("organizations").select("id, nome, slug")
        needle = (q or "").strip().replace("%", "").replace(",", " ")
        if needle:
            query = query.ilike("nome", f"%{needle}%")
        rows = query.order("nome").limit(_clamp(limit)).execute().data or []
        return [_ref(r) for r in rows]

    def get(self, org_id: UUID) -> OrgRef | None:
        rows = self._client.table("organizations").select("id, nome, slug").eq("id", str(org_id)).limit(1).execute().data or []
        return _ref(rows[0]) if rows else None


def get_org_directory(settings: Any) -> OrgDirectory:
    """Real when a service-role key is configured, Fake (empty) otherwise -- same signal as the other stores."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeOrgDirectory()
    from app.database import get_core_client

    return SupabaseOrgDirectory(get_core_client())
