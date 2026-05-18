"""`FakeMetaAdapter` — deterministic in-memory adapter (dev/test default).

Mirrors the Graph response shapes so consumer code swaps real/fake
transparently. `auth_mode` is `"none"` (no real credentials) — but
`status()` reports `configured=False, adapter="fake"` so a consumer
can still introspect. Seeded via `seed(...)`; `limit` truncation
mirrors the real adapter's paging cap.

Read-only v1. When posting lands, the Fake gets no-op write methods
(the contract grows; the Fake stays network-free)."""

from __future__ import annotations

from noctusai_lib.integrations.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    MetaConnectionStatus,
    PostInsights,
)


class FakeMetaAdapter:
    """In-memory `MetaAdapter`. Default when no creds are configured."""

    auth_mode = "none"

    def __init__(self) -> None:
        self._pages: list[FacebookPage] = []
        self._posts_by_page: dict[str, list[FacebookPost]] = {}
        self._ig_accounts: list[InstagramAccount] = []
        self._media_by_ig_user: dict[str, list[InstagramMedia]] = {}
        self._post_insights: dict[str, PostInsights] = {}
        self._media_insights: dict[str, PostInsights] = {}
        self._me: dict[str, str] = {}

    def seed(
        self,
        *,
        pages: list[FacebookPage] | None = None,
        posts_by_page: dict[str, list[FacebookPost]] | None = None,
        ig_accounts: list[InstagramAccount] | None = None,
        media_by_ig_user: dict[str, list[InstagramMedia]] | None = None,
        post_insights: dict[str, PostInsights] | None = None,
        media_insights: dict[str, PostInsights] | None = None,
        me: dict[str, str] | None = None,
    ) -> "FakeMetaAdapter":
        if pages is not None:
            self._pages = list(pages)
        if posts_by_page is not None:
            self._posts_by_page = {k: list(v) for k, v in posts_by_page.items()}
        if ig_accounts is not None:
            self._ig_accounts = list(ig_accounts)
        if media_by_ig_user is not None:
            self._media_by_ig_user = {
                k: list(v) for k, v in media_by_ig_user.items()
            }
        if post_insights is not None:
            self._post_insights = dict(post_insights)
        if media_insights is not None:
            self._media_insights = dict(media_insights)
        if me is not None:
            self._me = dict(me)
        return self

    def status(self) -> MetaConnectionStatus:
        return MetaConnectionStatus(
            configured=False,
            adapter="fake",
            auth_mode="none",
            consent_required=True,
            user_id=self._me.get("id"),
            user_name=self._me.get("name"),
            pages_count=len(self._pages),
            instagram_accounts_count=len(self._ig_accounts),
        )

    def me(self) -> dict:
        return dict(self._me)

    def list_facebook_pages(self) -> list[FacebookPage]:
        return list(self._pages)

    def get_page(self, page_id: str) -> FacebookPage | None:
        for page in self._pages:
            if page.id == page_id:
                return page
        return None

    def list_facebook_posts(
        self, page_id: str, limit: int = 25
    ) -> list[FacebookPost]:
        return list(self._posts_by_page.get(page_id, []))[:limit]

    def get_facebook_post_insights(
        self, post_id: str, page_id: str | None = None
    ) -> PostInsights:
        return self._post_insights.get(
            post_id, PostInsights(object_id=post_id)
        )

    def list_instagram_accounts(self) -> list[InstagramAccount]:
        return list(self._ig_accounts)

    def list_instagram_media(
        self, ig_user_id: str, limit: int = 25
    ) -> list[InstagramMedia]:
        return list(self._media_by_ig_user.get(ig_user_id, []))[:limit]

    def get_instagram_media_insights(self, media_id: str) -> PostInsights:
        return self._media_insights.get(
            media_id, PostInsights(object_id=media_id)
        )


__all__ = ["FakeMetaAdapter"]
