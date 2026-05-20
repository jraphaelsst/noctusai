"""Post CRUD + slide aggregation."""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)


class PostService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_posts(
        self,
        status: Optional[str] = None,
        brand_kit_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = self.db.table("mc_posts").select("*").eq("org_id", self.org_id)
        if status:
            query = query.eq("status", status)
        if brand_kit_id:
            query = query.eq("brand_kit_id", brand_kit_id)
        result = query.order("created_at", desc=True).execute()
        return result.data or []

    def get_post(self, post_id: str) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("mc_posts")
            .select("*")
            .eq("id", post_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_post_detail(self, post_id: str) -> Optional[dict[str, Any]]:
        """Return the post with its slides + brand kit aggregated."""
        post = self.get_post(post_id)
        if not post:
            return None
        slides = (
            self.db.table("mc_post_slides")
            .select("*")
            .eq("post_id", post_id)
            .eq("org_id", self.org_id)
            .order("slide_n")
            .execute()
        )
        kit = (
            self.db.table("mc_brand_kits")
            .select("id,name,persona,design_system,default_lang")
            .eq("id", post["brand_kit_id"])
            .eq("org_id", self.org_id)
            .execute()
        )
        post["slides"] = slides.data or []
        post["brand_kit"] = (kit.data or [None])[0]
        return post

    def create_post(self, data: dict[str, Any], user_id: str) -> Optional[dict[str, Any]]:
        # Confirm the brand_kit_id belongs to this org.
        kit_id = data.get("brand_kit_id")
        kit_check = (
            self.db.table("mc_brand_kits")
            .select("id")
            .eq("id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        if not kit_check.data:
            return None
        # Set status explicitly so the returned shape is identical under any
        # backing store (the SQL default exists for DB integrity, but the
        # service guarantees the field is set on insert).
        payload = {
            **data,
            "org_id": self.org_id,
            "created_by": user_id,
            "status": "draft",
        }
        result = self.db.table("mc_posts").insert(payload).execute()
        return result.data[0] if result.data else None

    def update_post(
        self, post_id: str, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not self.get_post(post_id):
            return None
        result = (
            self.db.table("mc_posts")
            .update(data)
            .eq("id", post_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def delete_post(self, post_id: str) -> bool:
        post = self.get_post(post_id)
        if not post or post["status"] not in ("draft", "ready"):
            return False
        delete_or_404(
            self.db,
            "mc_posts",
            ("id", post_id),
            ("org_id", self.org_id),
            message="Post não encontrado",
        )
        return True

    # ── Slide writes (used by generation services) ──────────────────────

    def upsert_slides(
        self, post_id: str, slides: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Replace the post's slides with the supplied set.

        Used by the storyboard generation stage. ``slide_n`` is the natural
        key — existing rows for the post are deleted, then new rows inserted.
        """
        # Confirm the post belongs to this org before any write.
        if not self.get_post(post_id):
            return []
        (
            self.db.table("mc_post_slides")
            .delete()
            .eq("post_id", post_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        if not slides:
            return []
        rows = [
            {**s, "post_id": post_id, "org_id": self.org_id} for s in slides
        ]
        result = self.db.table("mc_post_slides").insert(rows).execute()
        return result.data or []

    def patch_slide_prompts(
        self, post_id: str, slide_n: int, prompts: dict[str, str]
    ) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("mc_post_slides")
            .update(prompts)
            .eq("post_id", post_id)
            .eq("org_id", self.org_id)
            .eq("slide_n", slide_n)
            .execute()
        )
        return result.data[0] if result.data else None
