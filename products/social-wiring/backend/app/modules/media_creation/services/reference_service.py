"""Brand-reference CRUD — URL-only assets in v1."""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)


class ReferenceService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_references(self, brand_kit_id: str) -> list[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_references")
            .select("*")
            .eq("org_id", self.org_id)
            .eq("brand_kit_id", brand_kit_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def create_reference(
        self, brand_kit_id: str, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        # Confirm the parent kit lives in this org (defense-in-depth alongside RLS).
        kit_check = (
            self.db.table("mc_brand_kits")
            .select("id")
            .eq("id", brand_kit_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        if not kit_check.data:
            return None
        payload = {**data, "org_id": self.org_id, "brand_kit_id": brand_kit_id}
        result = self.db.table("mc_brand_references").insert(payload).execute()
        return result.data[0] if result.data else None

    def delete_reference(self, reference_id: str) -> bool:
        delete_or_404(
            self.db,
            "mc_brand_references",
            ("id", reference_id),
            ("org_id", self.org_id),
            message="Referência não encontrada",
        )
        return True
