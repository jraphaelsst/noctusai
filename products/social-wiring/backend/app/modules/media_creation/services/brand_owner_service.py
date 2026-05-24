"""Brand-owner (agent) reads — the agency layer above brand kits.

Per-org over ``social_wiring.mc_brand_owners``; assembles each owner with
its brandings (``mc_brand_kits`` rows). Writes go through the catalog
``seed_catalog`` loader (the source of truth is the repo catalog), so this
service is read-only by design in v1.
"""
from __future__ import annotations

from typing import Any, Optional


class BrandOwnerService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def _brandings_for(self, owner_id: str) -> list[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_kits")
            .select("*")
            .eq("org_id", self.org_id)
            .eq("brand_owner_id", owner_id)
            .order("slug")
            .execute()
        )
        return result.data or []

    def list_owners(self) -> list[dict[str, Any]]:
        owners = (
            self.db.table("mc_brand_owners")
            .select("*")
            .eq("org_id", self.org_id)
            .order("name")
            .execute()
        )
        out: list[dict[str, Any]] = []
        for owner in owners.data or []:
            out.append({**owner, "brandings": self._brandings_for(owner["id"])})
        return out

    def get_owner(self, owner_id: str) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_owners")
            .select("*")
            .eq("id", owner_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        if not result.data:
            return None
        owner = result.data[0]
        return {**owner, "brandings": self._brandings_for(owner_id)}
