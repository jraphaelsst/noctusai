"""Brand-kit CRUD — persona + design system text blobs per org."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BrandKitService:
    """Per-org CRUD over ``social_wiring.mc_brand_kits``.

    Mirrors the email_marketing service shape: ``(db, org_id)`` ctor,
    plain methods returning dicts (or ``None`` on not-found).
    """

    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_kits(self) -> list[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_kits")
            .select("*")
            .eq("org_id", self.org_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_kit(self, kit_id: str) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_kits")
            .select("*")
            .eq("id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def create_kit(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        payload = {**data, "org_id": self.org_id, "created_by": user_id}
        result = self.db.table("mc_brand_kits").insert(payload).execute()
        return result.data[0] if result.data else None

    def update_kit(self, kit_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.get_kit(kit_id):
            return None
        result = (
            self.db.table("mc_brand_kits")
            .update(data)
            .eq("id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None
