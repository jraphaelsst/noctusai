"""In-memory Meta adapter for tests + the no-credentials fallback.

Mirrors the read-side of Graph API: list_pages / list_facebook_posts /
list_instagram_accounts / list_instagram_media / insights against an
internal dict of dataclass rows. Tests can seed it via ``adapter.seed(...)``.

The Fake exists primarily so:

1. ``get_meta_adapter()`` can return SOMETHING even when no Meta app is
   configured — the chatbot tools should return a structured "not
   connected" response, not raise.
2. Unit tests can validate the chatbot's tool plumbing without hitting
   live Graph endpoints.
"""
from __future__ import annotations

from typing import Any

from app.services.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    PostInsights,
)


class FakeMetaAdapter:
    """Read-only in-memory Meta adapter."""

    def __init__(self) -> None:
        self._pages: dict[str, FacebookPage] = {}
        self._posts: dict[str, list[FacebookPost]] = {}
        self._ig_accounts: dict[str, InstagramAccount] = {}
        self._ig_media: dict[str, list[InstagramMedia]] = {}
        self._post_insights: dict[str, PostInsights] = {}
        self._media_insights: dict[str, PostInsights] = {}
        self._me: dict[str, Any] = {"id": "fake-user", "name": "Fake User"}

    def seed(
        self,
        *,
        pages: list[FacebookPage] | None = None,
        posts_by_page: dict[str, list[FacebookPost]] | None = None,
        ig_accounts: list[InstagramAccount] | None = None,
        media_by_ig_user: dict[str, list[InstagramMedia]] | None = None,
        post_insights: dict[str, PostInsights] | None = None,
        media_insights: dict[str, PostInsights] | None = None,
        me: dict[str, Any] | None = None,
    ) -> None:
        if pages is not None:
            self._pages = {p.page_id: p for p in pages}
        if posts_by_page is not None:
            self._posts = dict(posts_by_page)
        if ig_accounts is not None:
            self._ig_accounts = {a.ig_user_id: a for a in ig_accounts}
        if media_by_ig_user is not None:
            self._ig_media = dict(media_by_ig_user)
        if post_insights is not None:
            self._post_insights = dict(post_insights)
        if media_insights is not None:
            self._media_insights = dict(media_insights)
        if me is not None:
            self._me = dict(me)

    def list_pages(self) -> list[FacebookPage]:
        return list(self._pages.values())

    def get_page(self, page_id: str) -> FacebookPage | None:
        return self._pages.get(page_id)

    def list_facebook_posts(
        self,
        page_id: str,
        *,
        limit: int = 10,
    ) -> list[FacebookPost]:
        return self._posts.get(page_id, [])[:limit]

    def get_facebook_post_insights(
        self,
        post_id: str,
        *,
        page_id: str | None = None,  # noqa: ARG002
    ) -> PostInsights | None:
        return self._post_insights.get(post_id)

    def list_instagram_accounts(self) -> list[InstagramAccount]:
        return list(self._ig_accounts.values())

    def list_instagram_media(
        self,
        ig_user_id: str,
        *,
        limit: int = 10,
    ) -> list[InstagramMedia]:
        return self._ig_media.get(ig_user_id, [])[:limit]

    def get_instagram_media_insights(
        self,
        media_id: str,
    ) -> PostInsights | None:
        return self._media_insights.get(media_id)

    def me(self) -> dict[str, Any]:
        return dict(self._me)
