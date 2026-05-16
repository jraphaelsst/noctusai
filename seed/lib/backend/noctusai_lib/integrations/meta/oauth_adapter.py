"""`MetaOAuthAdapter` — the live Graph adapter (dual auth backend).

Auth resolution priority (`_user_token`):
  1. System User Token (`system_user_token` ctor arg) — production
     path, workspace-global, never expires, **required** for any
     customer whose assets are owned by a Meta Business Portfolio
     (which is virtually every commercial customer; user-OAuth tokens
     silently can't see BM-owned Pages even with all scopes granted —
     session-notes §A.1 Blocker 2 / 3).
  2. OAuth credential store fallback (`resolver` + `org_id`) —
     end-user-facing path.

`auth_mode` (`"system_user"` / `"user_oauth"` / `"none"`) is surfaced
so operators can see which backend is active — the silent-empty-data
failure mode is invisible otherwise.

Page tokens are NEVER persisted — `list_facebook_pages` refetches them
from `/me/accounts` on every call (cheap; avoids token-rotation
drift). They're cached in-memory per adapter instance so repeated
calls in one request share the round trip.

Read-only v1. Posting is an additive future extension (new methods
here + Protocol extension; the Fake gets no-ops).
"""

from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.integrations.meta import _meta_api
from noctusai_lib.integrations.meta._meta_api import MetaGraphError
from noctusai_lib.integrations.meta.credentials import MetaCredentialResolver
from noctusai_lib.integrations.meta.mappers import (
    IG_ACCOUNT_FIELDS,
    IG_MEDIA_FIELDS,
    IG_MEDIA_INSIGHT_METRICS,
    ME_FIELDS,
    PAGE_FIELDS,
    PAGE_IG_FIELD,
    POST_FIELDS,
    POST_INSIGHT_METRICS,
    ig_account_from_body,
    ig_media_from_body,
    insights_from_body,
    page_from_body,
    post_from_body,
)
from noctusai_lib.integrations.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    MetaConnectionStatus,
    PostInsights,
)

logger = logging.getLogger(__name__)


class MetaOAuthAdapter:
    """Live Meta Graph adapter satisfying `MetaAdapter`.

    Construct via the factory `get_meta_adapter(...)` rather than
    directly — the factory does the system_user → user_oauth → Fake
    selection."""

    def __init__(
        self,
        *,
        system_user_token: str | None = None,
        resolver: MetaCredentialResolver | None = None,
        org_id: str | None = None,
        graph_version: str = _meta_api.DEFAULT_GRAPH_VERSION,
    ) -> None:
        self._system_user_token = system_user_token or None
        self._resolver = resolver
        self._org_id = org_id
        self._version = graph_version
        self._page_token_cache: dict[str, str] = {}

    # ─── Auth ─────────────────────────────────────────────────────────

    @property
    def auth_mode(self) -> str:
        if self._system_user_token:
            return "system_user"
        if self._resolver is not None:
            return "user_oauth"
        return "none"

    def _user_token(self) -> str:
        """Resolve the user-level token: System User Token first
        (production), OAuth credential store fallback."""

        if self._system_user_token:
            return self._system_user_token
        if self._resolver is not None:
            creds = self._resolver.get_credentials(self._org_id)
            if creds is not None and creds.access_token:
                return creds.access_token
        raise MetaGraphError(
            "No Meta credentials available (no System User Token, no "
            "stored OAuth credential)",
            code=190,
        )

    # ─── Status ───────────────────────────────────────────────────────

    def status(self) -> MetaConnectionStatus:
        mode = self.auth_mode
        if mode == "none":
            return MetaConnectionStatus(
                configured=False,
                adapter="oauth",
                auth_mode="none",
                consent_required=True,
                error="no_credentials",
            )
        try:
            me = _meta_api.graph_get(
                "me",
                access_token=self._user_token(),
                params={"fields": ME_FIELDS},
                version=self._version,
            )
        except MetaGraphError as exc:
            return MetaConnectionStatus(
                configured=True,
                adapter="oauth",
                auth_mode=mode,
                consent_required=exc.is_auth_error,
                error="needs_reconnection" if exc.is_auth_error else exc.message,
            )
        pages = self.list_facebook_pages()
        ig = self.list_instagram_accounts()
        return MetaConnectionStatus(
            configured=True,
            adapter="oauth",
            auth_mode=mode,
            consent_required=False,
            user_id=str(me.get("id")) if me.get("id") else None,
            user_name=me.get("name"),
            pages_count=len(pages),
            instagram_accounts_count=len(ig),
        )

    # ─── Facebook ─────────────────────────────────────────────────────

    def list_facebook_pages(self) -> list[FacebookPage]:
        rows = _meta_api.graph_paged(
            "me/accounts",
            access_token=self._user_token(),
            params={"fields": PAGE_FIELDS, "limit": 100},
            version=self._version,
        )
        pages = [page_from_body(r) for r in rows]
        for p in pages:
            if p.access_token:
                self._page_token_cache[p.id] = p.access_token
        return pages

    def _page_token(self, page_id: str) -> str:
        if page_id not in self._page_token_cache:
            # Refetch — Page tokens may have rotated.
            self.list_facebook_pages()
        token = self._page_token_cache.get(page_id)
        if not token:
            raise MetaGraphError(
                f"No access token resolvable for page {page_id} "
                "(not in /me/accounts for this identity)",
                code=200,
            )
        return token

    def list_facebook_posts(
        self, page_id: str, limit: int = 25
    ) -> list[FacebookPost]:
        rows = _meta_api.graph_paged(
            f"{page_id}/posts",
            access_token=self._page_token(page_id),
            params={"fields": POST_FIELDS, "limit": limit},
            version=self._version,
            limit=limit,
        )
        return [post_from_body(r) for r in rows]

    def get_facebook_post_insights(
        self, post_id: str, page_id: str | None = None
    ) -> PostInsights:
        token = self._page_token(page_id) if page_id else self._user_token()
        body = _meta_api.graph_get(
            f"{post_id}/insights",
            access_token=token,
            params={"metric": ",".join(POST_INSIGHT_METRICS)},
            version=self._version,
        )
        return insights_from_body(post_id, body)

    # ─── Instagram ────────────────────────────────────────────────────

    def list_instagram_accounts(self) -> list[InstagramAccount]:
        accounts: list[InstagramAccount] = []
        for page in self.list_facebook_pages():
            try:
                link = _meta_api.graph_get(
                    page.id,
                    access_token=self._page_token(page.id),
                    params={"fields": PAGE_IG_FIELD},
                    version=self._version,
                )
            except MetaGraphError as exc:
                logger.warning(
                    "IG link probe failed for page %s: %s", page.id, exc
                )
                continue
            ig_ref: Any = link.get(PAGE_IG_FIELD)
            if not isinstance(ig_ref, dict) or not ig_ref.get("id"):
                continue
            detail = _meta_api.graph_get(
                str(ig_ref["id"]),
                access_token=self._page_token(page.id),
                params={"fields": IG_ACCOUNT_FIELDS},
                version=self._version,
            )
            accounts.append(ig_account_from_body(detail, page_id=page.id))
        return accounts

    def list_instagram_media(
        self, ig_user_id: str, limit: int = 25
    ) -> list[InstagramMedia]:
        rows = _meta_api.graph_paged(
            f"{ig_user_id}/media",
            access_token=self._user_token(),
            params={"fields": IG_MEDIA_FIELDS, "limit": limit},
            version=self._version,
            limit=limit,
        )
        return [ig_media_from_body(r) for r in rows]

    def get_instagram_media_insights(self, media_id: str) -> PostInsights:
        body = _meta_api.graph_get(
            f"{media_id}/insights",
            access_token=self._user_token(),
            params={"metric": ",".join(IG_MEDIA_INSIGHT_METRICS)},
            version=self._version,
        )
        return insights_from_body(media_id, body)


__all__ = ["MetaOAuthAdapter"]
