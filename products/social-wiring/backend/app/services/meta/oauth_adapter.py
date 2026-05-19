"""Meta Graph API adapter that acts AS the consenting Facebook user.

Same pattern as ``drive_api/oauth_adapter.py`` (the absorbed
``calendar/oauth_adapter.py`` was retired in Phase 5 of
``social-wiring-google-seed-consume`` — the calendar surface now
consumes the seed adapter directly):
load the encrypted credential bundle from :class:`CredentialStore`
(provider=``meta``), use the stored **user access token** for the few
endpoints that need it (``/me`` + ``/me/accounts``), then per-Page calls
go via the **page token** that ``/me/accounts`` issues (page tokens are
long-lived and don't expire while the user token is valid).

Token chain:

1. ``GET /v21.0/dialog/oauth?...`` → user consent → ``code``
2. ``GET /v21.0/oauth/access_token?code=...`` → short-lived user token (~2h)
3. ``GET /v21.0/oauth/access_token?grant_type=fb_exchange_token`` →
   long-lived user token (~60 days)
4. ``GET /v21.0/me/accounts`` → list of Pages, each with a Page token

The CredentialStore row stores all four artifacts:

* ``access_token`` — long-lived user token
* ``token_type``, ``expires_in``, ``scope``
* ``user_id`` — for /me probe
* (page tokens are NOT stored — they're fetched fresh from
  ``/me/accounts`` every adapter construction because Meta rotates
  them under some conditions and the round trip is cheap)

When the user token expires (or is revoked), the adapter raises
``MetaGraphError`` with ``is_auth_error=True`` — the chatbot tool layer
should surface that as "please reconnect" rather than swallowing.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.services.credential_vault import CredentialStore
from app.services.meta import _meta_api
from app.services.meta._meta_api import MetaGraphError
from app.services.meta.mappers import (
    FB_POST_INSIGHT_METRICS,
    IG_ACCOUNT_FIELDS,
    IG_MEDIA_FIELDS,
    IG_MEDIA_INSIGHT_METRICS,
    PAGE_FIELDS,
    POST_FIELDS,
    ig_account_body_to_instagram_account,
    insight_body_to_post_insights,
    media_body_to_instagram_media,
    page_body_to_facebook_page,
    post_body_to_facebook_post,
)
from app.services.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    PostInsights,
)

logger = logging.getLogger(__name__)

META_PROVIDER = "meta"


class MetaOAuthAdapter:
    """Meta Graph adapter — read-only access to FB Pages + IG Business.

    Despite the name, this adapter supports TWO auth modes:

    1. **System User Token** (``META_SYSTEM_USER_TOKEN`` in env) — the
       production-grade path. The token belongs to a System User in
       your Business Portfolio, has direct admin access to the BM's
       Pages + IG accounts, and never expires. **This is what works
       for BM-owned assets**; user-OAuth tokens cannot access
       Portfolio-owned Pages in modern Meta dev mode.

    2. **User OAuth credential** — the human-consent path. The token
       belongs to a Facebook user who consented via
       ``/api/meta/oauth/start``. Works for Pages the consenting user
       owns directly, NOT for Pages owned by a Business Portfolio.

    Resolution order: ``_user_token`` checks env-configured System User
    Token first; falls back to the OAuth credential store. Both paths
    feed into the same Graph calls downstream — page tokens come from
    ``/me/accounts`` either way.
    """

    def __init__(
        self,
        *,
        credential_store: CredentialStore | None = None,
        org_id: UUID | None = None,
        settings=None,
    ):
        self._store = credential_store
        self._org_id = org_id
        self._settings = settings
        self._pages_cache: list[FacebookPage] | None = None
        self._ig_accounts_cache: list[InstagramAccount] | None = None

    # ─── Credential plumbing ──────────────────────────────────────────
    @property
    def auth_mode(self) -> str:
        """``"system_user"`` when META_SYSTEM_USER_TOKEN is set,
        ``"user_oauth"`` otherwise. Surfaced on /api/meta/status so
        operators can tell which mode is active."""
        from app.config import settings as default_settings

        s = self._settings or default_settings
        if getattr(s, "meta_system_user_token", ""):
            return "system_user"
        return "user_oauth"

    def _user_token(self) -> str:
        from app.config import settings as default_settings

        s = self._settings or default_settings

        # 1) System User Token — preferred path for BM-owned assets.
        system_token = getattr(s, "meta_system_user_token", "")
        if system_token:
            return system_token

        # 2) Fall back to the OAuth credential store.
        if self._store is None or self._org_id is None:
            raise MetaGraphError(
                "Meta adapter has no auth source: META_SYSTEM_USER_TOKEN "
                "is empty AND no CredentialStore is configured.",
                http_status=401,
            )
        stored = self._store.get(str(self._org_id), META_PROVIDER)
        if stored is None:
            raise MetaGraphError(
                "No Meta credential available. Either set "
                "META_SYSTEM_USER_TOKEN in .env (recommended for BM-owned "
                "assets) or visit /api/meta/oauth/start to consent.",
                http_status=401,
            )
        token = stored.tokens.get("access_token")
        if not token:
            raise MetaGraphError(
                "Stored Meta credential is missing access_token. "
                "Re-consent at /api/meta/oauth/start.",
                http_status=401,
            )
        return token

    def _page_token_for(self, page_id: str) -> str:
        for page in self.list_pages():
            if page.page_id == page_id:
                return page.access_token
        raise MetaGraphError(
            f"Page {page_id} is not in /me/accounts — consenting user "
            "either doesn't manage it or didn't grant pages_show_list.",
            http_status=403,
        )

    # ─── Read surface ─────────────────────────────────────────────────
    def me(self) -> dict[str, Any]:
        return _meta_api.graph_get(
            "/me",
            access_token=self._user_token(),
            params={"fields": "id,name,email"},
            settings=self._settings,
        )

    def list_pages(self) -> list[FacebookPage]:
        if self._pages_cache is not None:
            return self._pages_cache
        rows = list(
            _meta_api.graph_paged(
                "/me/accounts",
                access_token=self._user_token(),
                params={"fields": PAGE_FIELDS, "limit": 100},
                page_limit=5,
                settings=self._settings,
            )
        )
        self._pages_cache = [page_body_to_facebook_page(r) for r in rows]
        return self._pages_cache

    def get_page(self, page_id: str) -> FacebookPage | None:
        for page in self.list_pages():
            if page.page_id == page_id:
                return page
        # Page might be on a paged response we didn't reach — try a
        # direct lookup (uses user token; succeeds only if the user
        # manages this page).
        try:
            body = _meta_api.graph_get(
                f"/{page_id}",
                access_token=self._user_token(),
                params={"fields": PAGE_FIELDS},
                settings=self._settings,
            )
        except MetaGraphError:
            return None
        return page_body_to_facebook_page(body)

    def list_facebook_posts(
        self,
        page_id: str,
        *,
        limit: int = 10,
    ) -> list[FacebookPost]:
        page_token = self._page_token_for(page_id)
        rows = list(
            _meta_api.graph_paged(
                f"/{page_id}/posts",
                access_token=page_token,
                params={"fields": POST_FIELDS, "limit": min(limit, 100)},
                page_limit=1,
                settings=self._settings,
            )
        )
        posts = [post_body_to_facebook_post(r, page_id=page_id) for r in rows]
        return posts[:limit]

    def get_facebook_post_insights(
        self,
        post_id: str,
        *,
        page_id: str | None = None,
    ) -> PostInsights | None:
        # Page insights need the page token — derive page_id from the
        # composite id when not explicitly passed (Graph post ids are
        # always ``{page_id}_{post_id}``).
        derived_page_id = page_id or (
            post_id.split("_", 1)[0] if "_" in post_id else None
        )
        if not derived_page_id:
            raise MetaGraphError(
                "post_id must be composite ({page_id}_{post_id}) or page_id given",
                http_status=400,
            )
        page_token = self._page_token_for(derived_page_id)
        body = _meta_api.graph_get(
            f"/{post_id}/insights",
            access_token=page_token,
            params={"metric": ",".join(FB_POST_INSIGHT_METRICS)},
            settings=self._settings,
        )
        return insight_body_to_post_insights(body, object_id=post_id)

    def list_instagram_accounts(self) -> list[InstagramAccount]:
        if self._ig_accounts_cache is not None:
            return self._ig_accounts_cache
        accounts: list[InstagramAccount] = []
        # For each Page we manage, ask Graph if it has an attached
        # Instagram Business account. Pages without one return null.
        for page in self.list_pages():
            try:
                body = _meta_api.graph_get(
                    f"/{page.page_id}",
                    access_token=page.access_token,
                    params={"fields": "instagram_business_account"},
                    settings=self._settings,
                )
            except MetaGraphError:
                continue
            ig_id = (body.get("instagram_business_account") or {}).get("id")
            if not ig_id:
                continue
            try:
                ig_body = _meta_api.graph_get(
                    f"/{ig_id}",
                    access_token=page.access_token,
                    params={"fields": IG_ACCOUNT_FIELDS},
                    settings=self._settings,
                )
            except MetaGraphError as exc:
                logger.warning(
                    "ig account lookup failed (page=%s, ig=%s): %s",
                    page.page_id, ig_id, exc,
                )
                continue
            accounts.append(
                ig_account_body_to_instagram_account(
                    ig_body,
                    linked_page_id=page.page_id,
                )
            )
        self._ig_accounts_cache = accounts
        return accounts

    def list_instagram_media(
        self,
        ig_user_id: str,
        *,
        limit: int = 10,
    ) -> list[InstagramMedia]:
        # IG media is fetched with the linked Page token.
        page_token = self._page_token_for_ig(ig_user_id)
        rows = list(
            _meta_api.graph_paged(
                f"/{ig_user_id}/media",
                access_token=page_token,
                params={"fields": IG_MEDIA_FIELDS, "limit": min(limit, 100)},
                page_limit=1,
                settings=self._settings,
            )
        )
        media = [
            media_body_to_instagram_media(r, ig_user_id=ig_user_id) for r in rows
        ]
        return media[:limit]

    def get_instagram_media_insights(
        self,
        media_id: str,
    ) -> PostInsights | None:
        # Caller hands us the IG media id; we resolve which IG account
        # owns it by checking each known account's media list. Cheap
        # because list_instagram_accounts is cached.
        for account in self.list_instagram_accounts():
            if account.linked_page_id is None:
                continue
            page_token = self._page_token_for(account.linked_page_id)
            try:
                body = _meta_api.graph_get(
                    f"/{media_id}/insights",
                    access_token=page_token,
                    params={"metric": ",".join(IG_MEDIA_INSIGHT_METRICS)},
                    settings=self._settings,
                )
            except MetaGraphError as exc:
                if exc.is_auth_error:
                    raise
                # 404 / "not found" on this page token — try the next.
                continue
            return insight_body_to_post_insights(body, object_id=media_id)
        return None

    def _page_token_for_ig(self, ig_user_id: str) -> str:
        for account in self.list_instagram_accounts():
            if account.ig_user_id == ig_user_id and account.linked_page_id:
                return self._page_token_for(account.linked_page_id)
        raise MetaGraphError(
            f"IG account {ig_user_id} not found in any managed Page",
            http_status=404,
        )
