"""Publish a rendered media_creation post to Meta (Instagram / Facebook).

Composes the seed ``noctusai_lib.integrations.meta`` adapter (IG carousel
N+2-step / IG single 2-step / FB Pages photo) with the local
``mc_posts`` + ``mc_post_slides`` state. The Meta adapter is
constructor-injectable for tests — production picks it via
``get_meta_adapter`` from the ``META_SYSTEM_USER_TOKEN`` env (or returns
``FakeMetaAdapter`` for dev/test, per the seed default).

Per ``KB § INTEGRATIONS/meta.md``: production needs the IG
``instagram_content_publish`` (and FB ``pages_manage_posts``) scope
approved through Meta App Review — without it the live adapter raises
``MetaGraphError`` with ``requires_app_review=True``. We surface that as
a 422 with a structured reason so the FE can show a "scope pending
approval" prompt.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.integrations.meta import (
    FakeMetaAdapter,
    MetaAdapter,
    MetaGraphError,
    get_meta_adapter,
)

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """Raised when the post can't be published (missing data, scope absent, …)."""

    def __init__(self, reason: str, *, requires_app_review: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.requires_app_review = requires_app_review


class PublishService:
    """Publish a media_creation post to Meta and persist the publication state.

    ``meta_adapter`` is constructor-injectable for tests. Production resolves
    it through ``get_meta_adapter`` — pass a ``META_SYSTEM_USER_TOKEN`` env
    var (workspace-global) OR wire a per-tenant resolver into the seed
    factory; without either, the Fake fires (deterministic, no network).
    """

    def __init__(
        self,
        db,
        org_id: str,
        *,
        meta_adapter: MetaAdapter | None = None,
    ):
        self.db = db
        self.org_id = org_id
        self._meta_adapter = meta_adapter

    # ─── public surface ────────────────────────────────────────────────

    def publish_post(
        self,
        post: dict[str, Any],
        *,
        target: str,
        destination_id: str,
    ) -> dict[str, Any]:
        """Publish ``post`` to Meta, persist publication state, return the result.

        ``target`` ∈ {"instagram_carousel", "instagram_single", "facebook_photo"}.
        ``destination_id`` is the IG user id (for instagram_*) or the FB page
        id (for facebook_photo). Raises ``PublishError`` on missing slides /
        missing render / unsupported target / Meta App-Review gate.
        """

        if target not in ("instagram_carousel", "instagram_single", "facebook_photo"):
            raise PublishError("unsupported_target")

        slides = self._load_rendered_slides(post["id"])
        if not slides:
            raise PublishError("slides_missing")
        unrendered = [s for s in slides if not s.get("image_url")]
        if unrendered:
            raise PublishError("render_incomplete")

        caption = self._compose_caption(post)
        adapter = self._resolve_meta_adapter()
        configured = not isinstance(adapter, FakeMetaAdapter)

        try:
            if target == "instagram_carousel":
                if len(slides) < 2:
                    raise PublishError("carousel_needs_min_two_slides")
                published = adapter.publish_instagram_carousel(
                    destination_id,
                    [s["image_url"] for s in slides],
                    caption=caption,
                )
                media_id = published.id
                permalink = published.permalink
            elif target == "instagram_single":
                first = slides[0]
                published_media = adapter.publish_instagram_media(
                    destination_id,
                    first["image_url"],
                    caption=caption,
                )
                media_id = published_media.id
                permalink = published_media.permalink
            else:  # facebook_photo
                first = slides[0]
                published_post = adapter.publish_facebook_post(
                    destination_id,
                    caption or "",
                    photo_url=first["image_url"],
                )
                media_id = published_post.id
                permalink = published_post.permalink_url
        except MetaGraphError as exc:
            if exc.requires_app_review:
                raise PublishError(
                    "meta_scope_pending_app_review",
                    requires_app_review=True,
                ) from exc
            raise PublishError(f"meta_error:{exc}") from exc

        published_at = datetime.now(timezone.utc).isoformat()
        (
            self.db.table("mc_posts")
            .update(
                {
                    "status": "published",
                    "published_target": target,
                    "published_media_id": media_id,
                    "published_permalink": permalink,
                    "published_at": published_at,
                }
            )
            .eq("id", post["id"])
            .eq("org_id", self.org_id)
            .execute()
        )

        return {
            "configured": configured,
            "target": target,
            "media_id": media_id,
            "permalink": permalink,
            "published_at": published_at,
        }

    # ─── helpers ───────────────────────────────────────────────────────

    def _resolve_meta_adapter(self) -> MetaAdapter:
        if self._meta_adapter is not None:
            return self._meta_adapter
        return get_meta_adapter(
            system_user_token=os.getenv("META_SYSTEM_USER_TOKEN") or None,
        )

    def _load_rendered_slides(self, post_id: str) -> list[dict[str, Any]]:
        resp = (
            self.db.table("mc_post_slides")
            .select("*")
            .eq("post_id", post_id)
            .eq("org_id", self.org_id)
            .order("slide_n")
            .execute()
        )
        return resp.data or []

    def _compose_caption(self, post: dict[str, Any]) -> Optional[str]:
        caption = (post.get("copy_caption") or "").strip()
        tags = post.get("copy_hashtags") or []
        if tags:
            joined = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
            caption = f"{caption}\n\n{joined}".strip()
        return caption or None
