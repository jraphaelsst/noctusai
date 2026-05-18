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

Write/ads surface: `publish_facebook_post`,
`publish_instagram_media` (the 2-step container → `media_publish`
flow), `list_ad_campaigns`, `ad_insights`. These were added
additively — the read methods above are unchanged. **Scope gating:**
Meta gates the write scopes (`pages_manage_posts`,
`instagram_content_publish`) and ads scopes (`ads_read`,
`ads_management`) behind App Review. When the active token lacks the
gated scope Graph returns a permission error (code `10` / `200`);
the adapter re-raises it as `MetaGraphError` with
`requires_app_review` true — **never** a silent or faked success
(no-silent-errors). Production activation is therefore an App-Review
deployment gate, not a reason to defer the code (exactly how
`youtube.upload_video` ships real code behind a credential gate).
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
    AdCampaign,
    AdInsights,
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    MetaConnectionStatus,
    PostInsights,
    PublishedMedia,
    PublishedPost,
)

# Default ad-insights metric set — the common spend/delivery KPIs.
# Graph rejects unknown fields, so this is a conservative core set.
_AD_INSIGHT_FIELDS = "impressions,reach,spend,clicks,cpc,cpm,ctr"
_AD_CAMPAIGN_FIELDS = "id,name,objective,status,effective_status"

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

    def me(self) -> dict[str, Any]:
        """The authenticated identity (`/me`): `id`, `name`, `email`.

        `email` is only populated when the `email` scope was granted —
        Graph silently omits it otherwise (not an error)."""

        return _meta_api.graph_get(
            "me",
            access_token=self._user_token(),
            params={"fields": "id,name,email"},
            version=self._version,
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

    def get_page(self, page_id: str) -> FacebookPage | None:
        """One Page by id, or `None` if this identity can't see it.

        Tries the cached `/me/accounts` set first (cheap); falls back to
        a direct `/{page_id}` lookup with the user token (succeeds only
        if the user manages the page but it landed beyond the paging cap)."""

        for page in self.list_facebook_pages():
            if page.id == page_id:
                return page
        try:
            body = _meta_api.graph_get(
                page_id,
                access_token=self._user_token(),
                params={"fields": PAGE_FIELDS},
                version=self._version,
            )
        except MetaGraphError:
            return None
        return page_from_body(body)

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

    # ─── Write / ads surface ──────────────────────────────────────────

    def publish_facebook_post(
        self,
        page_id: str,
        message: str,
        link: str | None = None,
        photo_url: str | None = None,
    ) -> PublishedPost:
        """Publish a post to a Facebook Page.

        Text / link posts go to `POST /{page-id}/feed`; a `photo_url`
        instead posts to `POST /{page-id}/photos` (Graph fetches the
        image by URL and attaches the caption as `message`).

        **Production gate:** the `pages_manage_posts` scope is gated
        behind Meta App Review. If the active Page token lacks it
        Graph returns a permission error and this method raises
        `MetaGraphError` with `requires_app_review` true — it never
        fakes a success. Until the scope is approved this surfaces the
        gate honestly; the code path is real and complete."""

        token = self._page_token(page_id)
        if photo_url:
            body = _meta_api.graph_post(
                f"{page_id}/photos",
                access_token=token,
                data={"url": photo_url, "caption": message},
                version=self._version,
            )
        else:
            data: dict[str, Any] = {"message": message}
            if link:
                data["link"] = link
            body = _meta_api.graph_post(
                f"{page_id}/feed",
                access_token=token,
                data=data,
                version=self._version,
            )
        post_id = str(body.get("post_id") or body.get("id") or "")
        if not post_id:
            raise MetaGraphError(
                f"Page post publish to {page_id} returned no id",
                code=200,
            )
        permalink: str | None = None
        try:
            detail = _meta_api.graph_get(
                post_id,
                access_token=token,
                params={"fields": "permalink_url"},
                version=self._version,
            )
            permalink = detail.get("permalink_url")
        except MetaGraphError as exc:
            # Publish already succeeded; the permalink read-back is
            # best-effort and must not mask the successful write.
            logger.warning(
                "FB post %s published; permalink read-back failed: %s",
                post_id,
                exc,
            )
        return PublishedPost(
            id=post_id,
            page_id=page_id,
            message=message,
            permalink_url=permalink,
        )

    def publish_instagram_media(
        self,
        ig_user_id: str,
        image_url: str,
        caption: str | None = None,
    ) -> PublishedMedia:
        """Publish an Instagram image — the 2-step Graph flow.

        Step 1 `POST /{ig-user}/media` (image_url + caption) → a media
        *container* creation id. Step 2 `POST
        /{ig-user}/media_publish` (creation_id) → the published media
        id.

        **Production gate:** `instagram_content_publish` is gated
        behind Meta App Review. Without it Graph returns a permission
        error and this raises `MetaGraphError` with
        `requires_app_review` true — never a faked success. The
        2-step flow is fully implemented and runs end-to-end the
        moment the scope is approved."""

        token = self._user_token()
        create_data: dict[str, Any] = {"image_url": image_url}
        if caption is not None:
            create_data["caption"] = caption
        created = _meta_api.graph_post(
            f"{ig_user_id}/media",
            access_token=token,
            data=create_data,
            version=self._version,
        )
        container_id = str(created.get("id") or "")
        if not container_id:
            raise MetaGraphError(
                f"IG media container creation for {ig_user_id} "
                "returned no creation id",
                code=200,
            )
        published = _meta_api.graph_post(
            f"{ig_user_id}/media_publish",
            access_token=token,
            data={"creation_id": container_id},
            version=self._version,
        )
        media_id = str(published.get("id") or "")
        if not media_id:
            raise MetaGraphError(
                f"IG media_publish for container {container_id} "
                "returned no media id",
                code=200,
            )
        permalink: str | None = None
        try:
            detail = _meta_api.graph_get(
                media_id,
                access_token=token,
                params={"fields": "permalink"},
                version=self._version,
            )
            permalink = detail.get("permalink")
        except MetaGraphError as exc:
            logger.warning(
                "IG media %s published; permalink read-back failed: %s",
                media_id,
                exc,
            )
        return PublishedMedia(
            id=media_id,
            ig_user_id=ig_user_id,
            container_id=container_id,
            caption=caption,
            permalink=permalink,
        )

    def list_ad_campaigns(self, ad_account_id: str) -> list[AdCampaign]:
        """List ad campaigns under an ad account (reads — `ads_read`).

        `ad_account_id` is the bare id; the `act_` prefix is added
        here (`act_{id}/campaigns`). **Production gate:** `ads_read`
        is App-Review-gated; absent it Graph returns a permission
        error and the underlying `graph_paged` raises `MetaGraphError`
        with `requires_app_review` true — never a faked empty list."""

        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        rows = _meta_api.graph_paged(
            f"{acct}/campaigns",
            access_token=self._user_token(),
            params={"fields": _AD_CAMPAIGN_FIELDS, "limit": 100},
            version=self._version,
        )
        return [
            AdCampaign(
                id=str(r.get("id")),
                name=r.get("name"),
                objective=r.get("objective"),
                status=r.get("status"),
                effective_status=r.get("effective_status"),
            )
            for r in rows
            if r.get("id")
        ]

    def ad_insights(
        self,
        object_id: str,
        level: str,
        date_preset: str | None = None,
    ) -> AdInsights:
        """Ad insights for an object (campaign / adset / ad / account).

        `level` is the Graph aggregation level
        (`account`/`campaign`/`adset`/`ad`). **Production gate:**
        `ads_read` is App-Review-gated; absent it the call raises
        `MetaGraphError` with `requires_app_review` true."""

        params: dict[str, Any] = {
            "fields": _AD_INSIGHT_FIELDS,
            "level": level,
        }
        if date_preset:
            params["date_preset"] = date_preset
        body = _meta_api.graph_get(
            f"{object_id}/insights",
            access_token=self._user_token(),
            params=params,
            version=self._version,
        )
        rows = body.get("data") or []
        metrics: dict[str, float] = {}
        if rows and isinstance(rows[0], dict):
            for key, val in rows[0].items():
                try:
                    metrics[key] = float(val)
                except (TypeError, ValueError):
                    continue
        return AdInsights(
            object_id=object_id,
            level=level,
            metrics=metrics,
            raw=list(rows),
        )


__all__ = ["MetaOAuthAdapter"]
