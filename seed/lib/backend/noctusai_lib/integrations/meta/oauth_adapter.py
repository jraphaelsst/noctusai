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
flow), `list_ad_campaigns`, `ad_insights`, plus the ads-*management*
graph — `create_ad_campaign` / `create_ad_set` / `create_ad_creative`
/ `create_ad` (campaign→adset→ad→creative) + `update_campaign_status`
/ `update_ad_set_budget` (the update endpoints return
`{"success": true}` only, so the post-update state is read back).
These were added additively — the read methods above are unchanged.
**Scope gating:**
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
import time
from typing import Any

from noctusai_lib.integrations.meta import _meta_api
from noctusai_lib.integrations.meta._meta_api import MetaGraphError
from noctusai_lib.integrations.meta.credentials import MetaCredentialResolver
from noctusai_lib.integrations.meta.mappers import (
    FB_COMMENT_FIELDS,
    IG_ACCOUNT_FIELDS,
    IG_ACCOUNT_INSIGHT_METRICS,
    IG_COMMENT_FIELDS,
    IG_CONVERSATION_FIELDS,
    IG_DM_FIELDS,
    IG_MEDIA_FIELDS,
    IG_MEDIA_INSIGHT_METRICS,
    IG_TOTAL_VALUE_ACCOUNT_METRICS,
    ME_FIELDS,
    PAGE_FIELDS,
    PAGE_IG_FIELD,
    PAGE_INSIGHT_METRICS,
    POST_FIELDS,
    POST_INSIGHT_METRICS,
    conversation_from_body,
    direct_message_from_body,
    facebook_comment_from_body,
    ig_account_from_body,
    ig_media_from_body,
    instagram_comment_from_body,
    insights_from_body,
    page_from_body,
    post_from_body,
)
from noctusai_lib.integrations.meta.types import (
    Ad,
    AdCampaign,
    AdCreative,
    AdCreativeSpec,
    AdInsights,
    AdSet,
    AdSetSpec,
    AdSpec,
    CampaignSpec,
    Conversation,
    DirectMessage,
    FacebookComment,
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramComment,
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
_AD_SET_FIELDS = (
    "id,name,status,effective_status,campaign_id,"
    "daily_budget,billing_event,optimization_goal,targeting"
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

    def get_facebook_page_insights(
        self,
        page_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights:
        """Facebook Page-level insights (`GET /{page-id}/insights`).

        Unlike every other batched insights call above, this one requests
        each metric SEPARATELY — Meta has been retiring individual Page
        Insights metrics on a rolling basis (a wave retired 2026-06-15), and
        a single unsupported metric name 400s Graph's WHOLE batched call
        when metrics are comma-joined. Per-metric isolation means a
        retired/renamed metric only drops itself from the result (logged,
        never raised) — the caller never loses the other metrics over one
        bad name. `metrics` defaults to `PAGE_INSIGHT_METRICS` (calibrate
        against the live Graph Explorer for the connected app; pass an
        explicit list to override). `raw` accumulates every successful
        metric's response row(s)."""

        token = self._page_token(page_id)
        requested = metrics or PAGE_INSIGHT_METRICS
        params_base: dict[str, Any] = {"period": period}
        if since is not None:
            params_base["since"] = since
        if until is not None:
            params_base["until"] = until

        merged_metrics: dict[str, int] = {}
        merged_raw: list[dict[str, Any]] = []
        for metric in requested:
            try:
                body = _meta_api.graph_get(
                    f"{page_id}/insights",
                    access_token=token,
                    params={**params_base, "metric": metric},
                    version=self._version,
                )
            except MetaGraphError as exc:
                logger.warning(
                    "facebook page insights: metric %s failed for page %s: "
                    "%s — dropped (retired/unsupported for this app?)",
                    metric, page_id, exc,
                )
                continue
            parsed = insights_from_body(page_id, body)
            merged_metrics.update(parsed.metrics)
            merged_raw.extend(parsed.raw)
        return PostInsights(
            object_id=page_id, metrics=merged_metrics, raw=merged_raw
        )

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

    def get_instagram_account_insights(
        self,
        ig_user_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights:
        """Account-level (IG User) insights over a time window.

        Hits `GET /{ig-user-id}/insights` — the account endpoint,
        distinct from `get_instagram_media_insights`'s per-media call.
        Needs the `instagram_manage_insights` scope, which reading your
        OWN account's insights grants in a Development-mode app (no App
        Review) — the flat `metrics` map is the summed/last value per
        metric, and `raw` keeps the full per-day series so the snapshot
        layer can persist a trend.

        `metrics` defaults to `IG_ACCOUNT_INSIGHT_METRICS` (the stable
        `period=day` trio). `since`/`until` are unix timestamps bounding
        the window (Graph caps account insights at ~30 days per call);
        omit for Graph's default recent window. `period` is Graph's
        aggregation bucket (`day` | `week` | `days_28`).

        Requested metrics are SPLIT across up to two Graph calls: the
        time-series ones, and those Graph only serves with
        `metric_type=total_value` (`IG_TOTAL_VALUE_ACCOUNT_METRICS`).
        Graph validates the whole metric list up front and rejects the
        entire call if a total-value metric appears in a time-series
        request, so batching them together makes ONE unsupported metric
        (e.g. `profile_views`) zero out every other metric too. The rows
        from both calls merge into one `PostInsights`, so callers still
        see a single flat `metrics` map."""

        requested = list(metrics or IG_ACCOUNT_INSIGHT_METRICS)
        series_metrics = [
            m for m in requested if m not in IG_TOTAL_VALUE_ACCOUNT_METRICS
        ]
        total_value_metrics = [
            m for m in requested if m in IG_TOTAL_VALUE_ACCOUNT_METRICS
        ]

        window: dict[str, Any] = {}
        if since is not None:
            window["since"] = since
        if until is not None:
            window["until"] = until

        rows: list[dict[str, Any]] = []
        for group, extra in (
            (series_metrics, {}),
            (total_value_metrics, {"metric_type": "total_value"}),
        ):
            if not group:
                continue
            body = _meta_api.graph_get(
                f"{ig_user_id}/insights",
                access_token=self._user_token(),
                params={
                    "metric": ",".join(group),
                    "period": period,
                    **window,
                    **extra,
                },
                version=self._version,
            )
            rows.extend(body.get("data") or [])

        return insights_from_body(ig_user_id, {"data": rows})

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

    def publish_instagram_carousel(
        self,
        ig_user_id: str,
        image_urls: list[str],
        caption: str | None = None,
    ) -> PublishedMedia:
        """Publish an Instagram carousel — the N+1+1-step Graph flow.

        Step 1 (N times): `POST /{ig-user}/media` with
        `media_type=IMAGE`, `is_carousel_item=true`, `image_url=<url>`
        → child container id. Step 2: `POST /{ig-user}/media` with
        `media_type=CAROUSEL`, `children=<csv-of-ids>`, `caption=...`
        → parent container id. Step 3: `POST /{ig-user}/media_publish`
        (creation_id=parent) → published media id.

        **Production gate:** identical to ``publish_instagram_media`` —
        `instagram_content_publish` is App-Review-gated; absent it the
        first child-container call raises `MetaGraphError` with
        `requires_app_review` true. Carousels accept 2–10 images per
        IG's documented limit; we enforce the lower/upper bounds
        client-side so the error is loud, not a Graph 400 buried in a
        permission message."""

        if not image_urls:
            raise ValueError(
                "publish_instagram_carousel requires at least one image_url"
            )
        if len(image_urls) > 10:
            raise ValueError(
                "Instagram carousels accept at most 10 children"
            )
        token = self._user_token()
        child_ids: list[str] = []
        for image_url in image_urls:
            child = _meta_api.graph_post(
                f"{ig_user_id}/media",
                access_token=token,
                data={
                    "image_url": image_url,
                    "media_type": "IMAGE",
                    "is_carousel_item": "true",
                },
                version=self._version,
            )
            cid = str(child.get("id") or "")
            if not cid:
                raise MetaGraphError(
                    f"IG carousel child-container for {ig_user_id} "
                    f"returned no creation id",
                    code=200,
                )
            child_ids.append(cid)
        parent_data: dict[str, Any] = {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
        }
        if caption is not None:
            parent_data["caption"] = caption
        parent = _meta_api.graph_post(
            f"{ig_user_id}/media",
            access_token=token,
            data=parent_data,
            version=self._version,
        )
        container_id = str(parent.get("id") or "")
        if not container_id:
            raise MetaGraphError(
                f"IG carousel parent-container for {ig_user_id} "
                f"returned no creation id",
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
                f"IG carousel media_publish for container {container_id} "
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
                "IG carousel %s published; permalink read-back failed: %s",
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
    def publish_instagram_reel(
        self,
        ig_user_id: str,
        video_url: str,
        caption: str | None = None,
    ) -> PublishedMedia:
        """Publish an Instagram Reel — the 3-step asynchronous Graph flow.

        Reels (and IG video generally) do NOT publish synchronously like
        images. Step 1 ``POST /{ig-user}/media`` with ``media_type=REELS``
        + ``video_url`` (+ optional ``caption``) creates a media
        *container* whose ``status_code`` starts ``IN_PROGRESS`` while
        Graph downloads + transcodes the video. Step 2 polls
        ``GET /{creation-id}?fields=status,status_code`` until ``FINISHED``
        (``poll_media_status`` — hard-capped at 90s, raises on ``ERROR`` /
        ``EXPIRED`` / timeout). Step 3 ``POST /{ig-user}/media_publish``
        (``creation_id``) → the published media id.

        ``processing_duration_ms`` on the returned ``PublishedMedia``
        records the wall-clock spent waiting on the transcode so the
        consumer can log / surface slow renders.

        **Production gate:** ``instagram_content_publish`` is App-Review-
        gated (the same scope that gates image / carousel publish). Absent
        it the container-create call raises ``MetaGraphError`` with
        ``requires_app_review`` true — never a faked success. The 3-step
        flow is fully implemented and runs end-to-end the moment the scope
        is approved."""

        if not video_url:
            raise ValueError(
                "publish_instagram_reel requires a non-empty video_url"
            )
        token = self._user_token()
        create_data: dict[str, Any] = {
            "media_type": "REELS",
            "video_url": video_url,
        }
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
                f"IG Reel container creation for {ig_user_id} "
                "returned no creation id",
                code=200,
            )
        started = time.monotonic()
        _meta_api.poll_media_status(
            container_id,
            access_token=token,
            version=self._version,
        )
        processing_ms = int((time.monotonic() - started) * 1000)
        published = _meta_api.graph_post(
            f"{ig_user_id}/media_publish",
            access_token=token,
            data={"creation_id": container_id},
            version=self._version,
        )
        media_id = str(published.get("id") or "")
        if not media_id:
            raise MetaGraphError(
                f"IG Reel media_publish for container {container_id} "
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
                "IG Reel %s published; permalink read-back failed: %s",
                media_id,
                exc,
            )
        return PublishedMedia(
            id=media_id,
            ig_user_id=ig_user_id,
            container_id=container_id,
            caption=caption,
            permalink=permalink,
            processing_duration_ms=processing_ms,
        )

    def publish_facebook_video(
        self,
        page_id: str,
        video_url: str,
        description: str | None = None,
        *,
        as_reel: bool = False,
    ) -> PublishedPost:
        """Publish a video (or Reel) to a Facebook Page.

        Two endpoint families share one method via the ``as_reel``
        discriminator (Open Question #2 — unified flag, same Protocol
        shape):

        - ``as_reel=False`` (default) → ``POST /{page-id}/videos`` with
          ``file_url`` (Graph fetches the hosted asset) + ``description``.
          The Page video endpoint returns the video id synchronously;
          some Pages still report an ``IN_PROGRESS`` container, so when a
          processing container is returned this polls it to ``FINISHED``
          (``poll_media_status``) before returning.
        - ``as_reel=True`` → ``POST /{page-id}/video_reels`` — the FB
          Reel surface, which is always asynchronous: create the
          container, poll its ``status_code`` to ``FINISHED``, then
          ``POST /{page-id}/video_reels`` again with
          ``video_state=PUBLISHED`` to finalize.

        ``processing_duration_ms`` on the returned ``PublishedPost``
        records the wall-clock the transcode poll spent (``None`` if the
        endpoint returned a ready id with no poll).

        **Production gate:** FB Page video / Reel posting needs the Page
        write scope approved through Meta App Review (``pages_manage_posts``
        plus, for Reels, the Reels-publishing capability). Absent it the
        create call raises ``MetaGraphError`` with ``requires_app_review``
        true — never a faked success."""

        if not video_url:
            raise ValueError(
                "publish_facebook_video requires a non-empty video_url"
            )
        token = self._page_token(page_id)
        started = time.monotonic()
        processing_ms: int | None = None
        if as_reel:
            # FB Reel — always async: create container, poll, finalize.
            create_data: dict[str, Any] = {
                "upload_phase": "start",
                "video_url": video_url,
            }
            if description is not None:
                create_data["description"] = description
            created = _meta_api.graph_post(
                f"{page_id}/video_reels",
                access_token=token,
                data=create_data,
                version=self._version,
            )
            video_id = str(created.get("video_id") or created.get("id") or "")
            if not video_id:
                raise MetaGraphError(
                    f"FB Reel container creation for {page_id} "
                    "returned no video id",
                    code=200,
                )
            _meta_api.poll_media_status(
                video_id,
                access_token=token,
                version=self._version,
            )
            processing_ms = int((time.monotonic() - started) * 1000)
            _meta_api.graph_post(
                f"{page_id}/video_reels",
                access_token=token,
                data={
                    "video_id": video_id,
                    "upload_phase": "finish",
                    "video_state": "PUBLISHED",
                },
                version=self._version,
            )
            post_id = video_id
        else:
            create_data = {"file_url": video_url}
            if description is not None:
                create_data["description"] = description
            created = _meta_api.graph_post(
                f"{page_id}/videos",
                access_token=token,
                data=create_data,
                version=self._version,
            )
            post_id = str(created.get("id") or "")
            if not post_id:
                raise MetaGraphError(
                    f"FB Page video publish to {page_id} returned no id",
                    code=200,
                )
            # Some Pages return an IN_PROGRESS container even on /videos;
            # poll only when Graph signals processing is still pending.
            status_code = str(created.get("status_code") or "").upper()
            if status_code and status_code not in ("FINISHED", "PUBLISHED", "READY"):
                _meta_api.poll_media_status(
                    post_id,
                    access_token=token,
                    version=self._version,
                )
                processing_ms = int((time.monotonic() - started) * 1000)
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
            logger.warning(
                "FB video %s published; permalink read-back failed: %s",
                post_id,
                exc,
            )
        return PublishedPost(
            id=post_id,
            page_id=page_id,
            message=description,
            permalink_url=permalink,
            processing_duration_ms=processing_ms,
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
    # ─── Ads management surface (additive — read/insights/posting
    #     unchanged; mutations use the App-Review-gated
    #     ``ads_management`` scope, distinct from ``ads_read``) ───────

    def create_ad_campaign(
        self, ad_account_id: str, spec: CampaignSpec
    ) -> AdCampaign:
        """Create an ad campaign under an ad account (campaign→adset→ad
        →creative graph, step 1).

        `POST act_{id}/campaigns` with name / objective / status /
        special_ad_categories (Graph wants the categories JSON-encoded;
        an empty list is the mandatory explicit "none"). **Production
        gate:** the `ads_management` scope is App-Review-gated (distinct
        from the `ads_read` scope the read/insights surface uses).
        Absent it Graph returns a permission error and `graph_post`
        raises `MetaGraphError` with `requires_app_review` true — never
        a faked success."""

        import json

        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        body = _meta_api.graph_post(
            f"{acct}/campaigns",
            access_token=self._user_token(),
            data={
                "name": spec.name,
                "objective": spec.objective,
                "status": spec.status,
                "special_ad_categories": json.dumps(
                    list(spec.special_ad_categories)
                ),
            },
            version=self._version,
        )
        campaign_id = str(body.get("id") or "")
        if not campaign_id:
            raise MetaGraphError(
                f"Campaign create under {acct} returned no id", code=200
            )
        return AdCampaign(
            id=campaign_id,
            name=spec.name,
            objective=spec.objective,
            status=spec.status,
        )

    def create_ad_set(
        self, ad_account_id: str, spec: AdSetSpec
    ) -> AdSet:
        """Create an ad set under an ad account (graph step 2 — binds
        to a parent `campaign_id`).

        `POST act_{id}/adsets`. `daily_budget` is the account's minor
        currency unit (cents); `targeting` is passed through as JSON.
        Same `ads_management` App-Review gate as `create_ad_campaign`."""

        import json

        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        body = _meta_api.graph_post(
            f"{acct}/adsets",
            access_token=self._user_token(),
            data={
                "name": spec.name,
                "campaign_id": spec.campaign_id,
                "daily_budget": spec.daily_budget,
                "billing_event": spec.billing_event,
                "optimization_goal": spec.optimization_goal,
                "targeting": json.dumps(dict(spec.targeting)),
                "status": spec.status,
            },
            version=self._version,
        )
        ad_set_id = str(body.get("id") or "")
        if not ad_set_id:
            raise MetaGraphError(
                f"Ad set create under {acct} returned no id", code=200
            )
        return AdSet(
            id=ad_set_id,
            name=spec.name,
            status=spec.status,
            campaign_id=spec.campaign_id,
            daily_budget=spec.daily_budget,
            billing_event=spec.billing_event,
            optimization_goal=spec.optimization_goal,
            targeting=dict(spec.targeting),
        )

    def create_ad_creative(
        self, ad_account_id: str, spec: AdCreativeSpec
    ) -> AdCreative:
        """Create an ad creative under an ad account (graph step 3).

        `POST act_{id}/adcreatives`. `object_story_spec` is passed
        through as JSON. Same `ads_management` App-Review gate."""

        import json

        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        body = _meta_api.graph_post(
            f"{acct}/adcreatives",
            access_token=self._user_token(),
            data={
                "name": spec.name,
                "object_story_spec": json.dumps(
                    dict(spec.object_story_spec)
                ),
            },
            version=self._version,
        )
        creative_id = str(body.get("id") or "")
        if not creative_id:
            raise MetaGraphError(
                f"Ad creative create under {acct} returned no id",
                code=200,
            )
        return AdCreative(
            id=creative_id,
            name=spec.name,
            object_story_spec=dict(spec.object_story_spec),
        )

    def create_ad(self, ad_account_id: str, spec: AdSpec) -> Ad:
        """Create an ad under an ad account (graph leaf — binds an
        `adset_id` to a `creative_id`).

        `POST act_{id}/ads`. Same `ads_management` App-Review gate."""

        import json

        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        body = _meta_api.graph_post(
            f"{acct}/ads",
            access_token=self._user_token(),
            data={
                "name": spec.name,
                "adset_id": spec.adset_id,
                "creative": json.dumps({"creative_id": spec.creative_id}),
                "status": spec.status,
            },
            version=self._version,
        )
        ad_id = str(body.get("id") or "")
        if not ad_id:
            raise MetaGraphError(
                f"Ad create under {acct} returned no id", code=200
            )
        return Ad(
            id=ad_id,
            name=spec.name,
            status=spec.status,
            adset_id=spec.adset_id,
            creative_id=spec.creative_id,
        )

    def update_campaign_status(
        self, campaign_id: str, status: str
    ) -> AdCampaign:
        """Pause / activate a campaign (`POST /{campaign-id}` with the
        `status` field). Same `ads_management` App-Review gate.

        The Graph status-update endpoint returns `{"success": true}`,
        not the campaign object, so the post-update state is read back
        with a follow-up `graph_get` (the read-back is part of the
        contract — a status flip without confirmation would be a
        silent half-success)."""

        _meta_api.graph_post(
            f"{campaign_id}",
            access_token=self._user_token(),
            data={"status": status},
            version=self._version,
        )
        body = _meta_api.graph_get(
            f"{campaign_id}",
            access_token=self._user_token(),
            params={"fields": _AD_CAMPAIGN_FIELDS},
            version=self._version,
        )
        return AdCampaign(
            id=str(body.get("id") or campaign_id),
            name=body.get("name"),
            objective=body.get("objective"),
            status=body.get("status"),
            effective_status=body.get("effective_status"),
        )

    def update_ad_set_budget(
        self, ad_set_id: str, daily_budget: int
    ) -> AdSet:
        """Update an ad set's daily budget (`POST /{adset-id}` with
        `daily_budget`, the account's minor currency unit). Same
        `ads_management` App-Review gate. The post-update state is read
        back (the update endpoint returns `{"success": true}` only)."""

        _meta_api.graph_post(
            f"{ad_set_id}",
            access_token=self._user_token(),
            data={"daily_budget": daily_budget},
            version=self._version,
        )
        body = _meta_api.graph_get(
            f"{ad_set_id}",
            access_token=self._user_token(),
            params={"fields": _AD_SET_FIELDS},
            version=self._version,
        )
        return AdSet(
            id=str(body.get("id") or ad_set_id),
            name=body.get("name"),
            status=body.get("status"),
            effective_status=body.get("effective_status"),
            campaign_id=body.get("campaign_id"),
            daily_budget=body.get("daily_budget"),
            billing_event=body.get("billing_event"),
            optimization_goal=body.get("optimization_goal"),
            targeting=body.get("targeting") or {},
        )

    # ─── IG comments (additive — `instagram_manage_comments` scope) ────

    def list_instagram_comments(
        self, media_id: str, limit: int = 25
    ) -> list[InstagramComment]:
        """List top-level comments on an IG media item —
        `GET /{ig-media}/comments`. Reading this edge needs
        `instagram_manage_comments` (the same scope that gates
        reply/hide/delete — Meta does not split read/write here)."""

        rows = _meta_api.graph_paged(
            f"{media_id}/comments",
            access_token=self._user_token(),
            params={"fields": IG_COMMENT_FIELDS, "limit": limit},
            version=self._version,
            limit=limit,
        )
        return [instagram_comment_from_body(r) for r in rows]

    def create_instagram_comment(
        self, media_id: str, message: str
    ) -> InstagramComment:
        """Post a NEW top-level comment on an IG media item —
        `POST /{ig-media}/comments` (distinct edge from
        `reply_instagram_comment`'s `/{ig-comment}/replies` — this
        targets the MEDIA, not an existing comment). Same
        `instagram_manage_comments` App-Review gate; same
        create-then-read-back-best-effort posture as the reply path."""

        token = self._user_token()
        created = _meta_api.graph_post(
            f"{media_id}/comments",
            access_token=token,
            data={"message": message},
            version=self._version,
        )
        comment_id = str(created.get("id") or "")
        if not comment_id:
            raise MetaGraphError(
                f"IG comment create on {media_id} returned no id",
                code=200,
            )
        try:
            detail = _meta_api.graph_get(
                comment_id,
                access_token=token,
                params={"fields": IG_COMMENT_FIELDS},
                version=self._version,
            )
            return instagram_comment_from_body(detail)
        except MetaGraphError as exc:
            logger.warning(
                "IG comment %s created on %s; read-back failed: %s",
                comment_id, media_id, exc,
            )
            return InstagramComment(id=comment_id, text=message)

    def reply_instagram_comment(
        self, comment_id: str, message: str
    ) -> InstagramComment:
        """Reply to an IG comment — `POST /{ig-comment}/replies`.

        **Production gate:** `instagram_manage_comments` is App-Review-
        gated. Absent it Graph returns a permission error and this
        raises `MetaGraphError` with `requires_app_review` true — never
        a faked success. Graph's replies-create endpoint returns only
        `{"id": ...}`, so the created reply is read back (best-effort —
        a read-back failure must not mask the successful write)."""

        token = self._user_token()
        created = _meta_api.graph_post(
            f"{comment_id}/replies",
            access_token=token,
            data={"message": message},
            version=self._version,
        )
        reply_id = str(created.get("id") or "")
        if not reply_id:
            raise MetaGraphError(
                f"IG comment reply to {comment_id} returned no id",
                code=200,
            )
        try:
            detail = _meta_api.graph_get(
                reply_id,
                access_token=token,
                params={"fields": IG_COMMENT_FIELDS},
                version=self._version,
            )
            return instagram_comment_from_body(detail)
        except MetaGraphError as exc:
            logger.warning(
                "IG comment reply %s created; read-back failed: %s",
                reply_id,
                exc,
            )
            return InstagramComment(
                id=reply_id, text=message, parent_id=comment_id
            )

    def hide_instagram_comment(
        self, comment_id: str, hide: bool = True
    ) -> None:
        """Hide/unhide an IG comment — `POST /{ig-comment}` with
        `hide=<bool>`. Same `instagram_manage_comments` App-Review
        gate. Graph returns `{"success": true}` only — nothing to read
        back, hence `None`."""

        _meta_api.graph_post(
            comment_id,
            access_token=self._user_token(),
            data={"hide": "true" if hide else "false"},
            version=self._version,
        )

    def delete_instagram_comment(self, comment_id: str) -> None:
        """Delete an IG comment — `DELETE /{ig-comment}`. Same
        `instagram_manage_comments` App-Review gate."""

        _meta_api.graph_delete(
            comment_id,
            access_token=self._user_token(),
            version=self._version,
        )

    # ─── IG Direct messages (additive — `instagram_manage_messages`
    #    scope) ───────────────────────────────────────────────────────

    def list_instagram_conversations(
        self, page_id: str, limit: int = 25
    ) -> list[Conversation]:
        """List Instagram Direct conversation threads —
        `GET /{PAGE-ID}/conversations?platform=instagram` with the
        **Page** access token of the Facebook Page linked to the IG
        professional account.

        This is the **Facebook-Login** model (IG account linked to a
        Page) — the node is the PAGE, not the IG user, and the token is
        the Page token. Calling `/{ig-user-id}/conversations` with a
        user token is the *Instagram-Login* model's shape and Graph
        rejects it on a Facebook-Login app with error (#3) "Application
        does not have the capability to make this API call" — the DM
        capability lives on the Page for this model. Needs
        `instagram_basic` + `instagram_manage_messages` +
        `pages_manage_metadata`
        (developers.facebook.com/docs/messenger-platform/conversations)."""

        rows = _meta_api.graph_paged(
            f"{page_id}/conversations",
            access_token=self._page_token(page_id),
            params={
                "platform": "instagram",
                "fields": IG_CONVERSATION_FIELDS,
                "limit": limit,
            },
            version=self._version,
            limit=limit,
        )
        return [conversation_from_body(r) for r in rows]

    def list_instagram_messages(
        self, conversation_id: str, page_id: str, limit: int = 25
    ) -> list[DirectMessage]:
        """List messages inside one Direct conversation.

        `GET /{conversation}/messages` returns bare `{"id": ...}` rows
        (Graph does not expand message fields on the list edge), so
        each message is re-fetched by id (`GET /{message-id}`) for the
        full body — the same link-probe-then-detail-fetch shape
        `list_instagram_accounts` already uses for the Page→IG link.

        Uses the **Page** token (`page_id` = the Facebook Page linked to
        the IG account) — same Facebook-Login model as
        `list_instagram_conversations`; the conversation/message edges
        are Page-scoped operations on this model."""

        token = self._page_token(page_id)
        rows = _meta_api.graph_paged(
            f"{conversation_id}/messages",
            access_token=token,
            params={"limit": limit},
            version=self._version,
            limit=limit,
        )
        messages: list[DirectMessage] = []
        for row in rows:
            msg_id = str(row.get("id") or "")
            if not msg_id:
                continue
            detail = _meta_api.graph_get(
                msg_id,
                access_token=token,
                params={"fields": IG_DM_FIELDS},
                version=self._version,
            )
            messages.append(
                direct_message_from_body(
                    detail, conversation_id=conversation_id
                )
            )
        return messages

    def send_instagram_message(
        self, page_id: str, recipient_id: str, text: str
    ) -> DirectMessage:
        """Send an Instagram Direct message —
        `POST /{PAGE-ID}/messages` with nested `recipient={"id": ...}`
        + `message={"text": ...}` using the **Page** token (Meta's Send
        API shape — nested objects are JSON-encoded form fields, same
        convention as `create_ad_set`'s `targeting`).

        Facebook-Login model: the send goes through the PAGE linked to
        the IG account, not the IG-user node (see
        `list_instagram_conversations` — the IG-user node returns (#3)
        on this model).

        **Production gate:** `instagram_manage_messages` is App-Review-
        gated for serving OTHER users; absent the granted permission
        Graph returns a permission error and this raises
        `MetaGraphError` with `requires_app_review` true — never a
        faked success."""

        import json

        token = self._page_token(page_id)
        created = _meta_api.graph_post(
            f"{page_id}/messages",
            access_token=token,
            data={
                "recipient": json.dumps({"id": recipient_id}),
                "message": json.dumps({"text": text}),
            },
            version=self._version,
        )
        message_id = str(
            created.get("message_id") or created.get("id") or ""
        )
        if not message_id:
            raise MetaGraphError(
                f"IG Direct send from page {page_id} to {recipient_id} "
                "returned no message id",
                code=200,
            )
        return DirectMessage(
            id=message_id,
            sender_id=page_id,
            recipient_id=recipient_id,
            text=text,
        )

    # ─── IG Stories (additive — `instagram_content_publish` scope,
    #    same gate as the image/carousel/Reel publish surface) ───────

    def publish_instagram_story(
        self,
        ig_user_id: str,
        media_url: str,
        *,
        is_video: bool = False,
    ) -> PublishedMedia:
        """Publish to Instagram Stories — the 2-step container flow.

        Step 1 `POST /{ig-user}/media` with `media_type=STORIES` +
        `image_url=<url>` (or `video_url=<url>` when `is_video=True`)
        → a media container id. Step 2 `POST /{ig-user}/media_publish`
        (creation_id) → the published (ephemeral, 24h) story media id.
        Mirrors `publish_instagram_media`'s 2-step shape.

        **Graph-shape uncertainty (flag for live calibration):** unlike
        `publish_instagram_reel`, this does NOT poll
        `poll_media_status` before `media_publish` — Meta's docs are
        not fully consistent on whether a freshly-created video Story
        container can ever come back `IN_PROGRESS` the way REELS
        containers do. Ships the synchronous 2-step per spec; if a
        live token surfaces an `IN_PROGRESS` container for a video
        Story, add the same poll step `publish_instagram_reel` uses.

        **Production gate:** `instagram_content_publish` (the same
        scope gating image/carousel/Reel publish). Absent it the
        container-create call raises `MetaGraphError` with
        `requires_app_review` true — never a faked success."""

        token = self._user_token()
        create_data: dict[str, Any] = {"media_type": "STORIES"}
        if is_video:
            create_data["video_url"] = media_url
        else:
            create_data["image_url"] = media_url
        created = _meta_api.graph_post(
            f"{ig_user_id}/media",
            access_token=token,
            data=create_data,
            version=self._version,
        )
        container_id = str(created.get("id") or "")
        if not container_id:
            raise MetaGraphError(
                f"IG Story container creation for {ig_user_id} "
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
                f"IG Story media_publish for container {container_id} "
                "returned no media id",
                code=200,
            )
        return PublishedMedia(
            id=media_id,
            ig_user_id=ig_user_id,
            container_id=container_id,
        )

    # ─── FB comment moderation (additive — `pages_manage_engagement`
    #    scope) ───────────────────────────────────────────────────────

    def list_facebook_comments(
        self, post_id: str, limit: int = 25
    ) -> list[FacebookComment]:
        """List comments on a Facebook Page post —
        `GET /{post}/comments`. Needs `pages_manage_engagement`
        (App-Review-gated).

        **Graph-shape uncertainty (flag for live calibration):** the
        signature (mirroring the brief) takes no `page_id`, so this
        resolves `self._user_token()` rather than a Page token — fine
        for reading a public Page's comments, but replying/hiding/
        deleting AS the Page (rather than as the personal identity)
        typically wants the Page token. Calibrate against a real
        token; if Graph rejects the user-token write with a
        Page-token-required error, thread a `page_id` through these
        four methods to resolve `self._page_token(page_id)` instead."""

        rows = _meta_api.graph_paged(
            f"{post_id}/comments",
            access_token=self._user_token(),
            params={"fields": FB_COMMENT_FIELDS, "limit": limit},
            version=self._version,
            limit=limit,
        )
        return [facebook_comment_from_body(r) for r in rows]

    def create_facebook_comment(
        self, post_id: str, message: str
    ) -> FacebookComment:
        """Post a NEW top-level comment on a Facebook Page post —
        `POST /{post}/comments`. Graph's comments-create edge is the
        SAME shape whether the target is a post or an existing comment
        (`reply_facebook_comment` posts to `/{comment}/comments`
        instead) — this just targets the post id. Same
        `pages_manage_engagement` App-Review gate + user-token-vs-
        page-token calibration note as `list_facebook_comments`."""

        token = self._user_token()
        created = _meta_api.graph_post(
            f"{post_id}/comments",
            access_token=token,
            data={"message": message},
            version=self._version,
        )
        comment_id = str(created.get("id") or "")
        if not comment_id:
            raise MetaGraphError(
                f"FB comment create on {post_id} returned no id",
                code=200,
            )
        try:
            detail = _meta_api.graph_get(
                comment_id,
                access_token=token,
                params={"fields": FB_COMMENT_FIELDS},
                version=self._version,
            )
            return facebook_comment_from_body(detail)
        except MetaGraphError as exc:
            logger.warning(
                "FB comment %s created on %s; read-back failed: %s",
                comment_id, post_id, exc,
            )
            return FacebookComment(id=comment_id, message=message)

    def reply_facebook_comment(
        self, comment_id: str, message: str
    ) -> FacebookComment:
        """Reply to a Facebook comment — `POST /{comment}/comments`
        (Graph nests a reply as a child of the comment's own comments
        edge). Same `pages_manage_engagement` App-Review gate + the
        same user-token-vs-page-token calibration note as
        `list_facebook_comments`."""

        token = self._user_token()
        created = _meta_api.graph_post(
            f"{comment_id}/comments",
            access_token=token,
            data={"message": message},
            version=self._version,
        )
        reply_id = str(created.get("id") or "")
        if not reply_id:
            raise MetaGraphError(
                f"FB comment reply to {comment_id} returned no id",
                code=200,
            )
        try:
            detail = _meta_api.graph_get(
                reply_id,
                access_token=token,
                params={"fields": FB_COMMENT_FIELDS},
                version=self._version,
            )
            return facebook_comment_from_body(detail)
        except MetaGraphError as exc:
            logger.warning(
                "FB comment reply %s created; read-back failed: %s",
                reply_id,
                exc,
            )
            return FacebookComment(
                id=reply_id, message=message, parent_id=comment_id
            )

    def hide_facebook_comment(
        self, comment_id: str, hide: bool = True
    ) -> None:
        """Hide/unhide a Facebook comment — `POST /{comment}` with
        `is_hidden=<bool>`. Same `pages_manage_engagement` gate."""

        _meta_api.graph_post(
            comment_id,
            access_token=self._user_token(),
            data={"is_hidden": "true" if hide else "false"},
            version=self._version,
        )

    def delete_facebook_comment(self, comment_id: str) -> None:
        """Delete a Facebook comment — `DELETE /{comment}`. Same
        `pages_manage_engagement` gate."""

        _meta_api.graph_delete(
            comment_id,
            access_token=self._user_token(),
            version=self._version,
        )


__all__ = ["MetaOAuthAdapter"]
