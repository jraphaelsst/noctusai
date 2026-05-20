"""Meta (Facebook + Instagram) Graph API adapter value objects + Protocol.

Lifted into seed 2026-05-16 by `projects/social-wiring-absorption/`
Wave 1.E4 from the live-validated `noctusai-youtube-crawler`
`feat/meta-integrations` + `integration/oauth-discovery` branches.
The originating workspace was a functions-development environment;
this is the canonical seed home — sibling to `google_calendar/`,
`google_maps/`, `google_drive/`, `vista/`.

Read surface: Facebook Pages + posts + post-insights; Instagram
Business accounts + media + media-insights. Write surface (added as an
additive Protocol extension — read callers unchanged): Facebook Page
post publish, Instagram media publish (the 2-step container →
`media_publish` flow), ads campaign listing + ad insights. The write
methods raise a typed `MetaGraphError` with `requires_app_review` set
when the token lacks the gated scope — production activation needs the
write/ads scopes approved through Meta App Review; the code ships
regardless (the App Review is a deployment gate, not a reason to defer
the capability — mirrors `youtube.upload_video`'s credential gate).

There is **no service-account variant** — Meta's identity model
requires a real Facebook user (or System User) behind every call;
service accounts are not a Meta concept. Production-grade auth is the
System User Token (workspace-global, never expires); end-user OAuth is
the carve-out. The factory picks `system_user` → `user_oauth` → Fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class FacebookPage:
    """A Facebook Page the authenticated identity manages.

    `access_token` is the per-Page token returned by `/me/accounts`.
    It is **never persisted** — refetched fresh on every adapter
    construction (cheap one paged Graph call; avoids token-rotation
    drift, since Page tokens CAN rotate on admin/security triggers
    while the long-lived user token stays valid)."""

    id: str
    name: str
    category: str | None = None
    access_token: str | None = None
    fan_count: int | None = None
    followers_count: int | None = None
    link: str | None = None
    tasks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InstagramAccount:
    """An Instagram Business/Creator account linked to a Page via the
    Page's `instagram_business_account` field."""

    id: str
    username: str
    name: str | None = None
    profile_picture_url: str | None = None
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None
    biography: str | None = None
    website: str | None = None
    page_id: str | None = None


@dataclass(frozen=True)
class FacebookPost:
    """A post authored by a Page.

    `likes` / `comments` / `shares` are *counts* — the adapter requests
    `.summary(true).limit(0)` so Graph returns `summary.total_count`
    inline without expanding the edge body (bandwidth saver on posts
    with thousands of reactions). The consumer never sees the liker
    list, only the number."""

    id: str
    message: str | None = None
    created_time: datetime | None = None
    permalink_url: str | None = None
    full_picture: str | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class InstagramMedia:
    """An Instagram media item (image, video, or carousel album).

    Stories are excluded — they need `/{ig_user_id}/stories` and carry
    a 24h-validity caveat (out of v1)."""

    id: str
    caption: str | None = None
    media_type: str | None = None  # IMAGE | VIDEO | CAROUSEL_ALBUM
    media_url: str | None = None
    permalink: str | None = None
    thumbnail_url: str | None = None
    timestamp: datetime | None = None
    like_count: int = 0
    comments_count: int = 0


@dataclass(frozen=True)
class PostInsights:
    """Flattened per-post / per-media insight metrics.

    Graph returns each metric as `{name, period, values:[{value}]}`;
    some metrics (`post_reactions_by_type_total`) return a dict-valued
    `value` which the mapper sums into a flat int. `metrics` is the
    flattened `{metric_name: int}` map; `raw` keeps the original
    payload for consumers that need period/breakdown detail."""

    object_id: str
    metrics: dict[str, int] = field(default_factory=dict)
    raw: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PublishedPost:
    """The result of publishing a Facebook Page post.

    Graph's `POST /{page-id}/feed` returns `{"id": "{page}_{post}"}`
    (or `{"post_id": ...}` for some object kinds). `id` is the
    composite post id; `permalink_url` is populated only when the
    follow-up read succeeds (best-effort — publish success does not
    depend on it)."""

    id: str
    page_id: str
    message: str | None = None
    permalink_url: str | None = None


@dataclass(frozen=True)
class PublishedMedia:
    """The result of publishing an Instagram media item.

    IG publish is a 2-step Graph flow: `POST /{ig-user}/media` creates
    a media *container* (returns a creation id), then `POST
    /{ig-user}/media_publish` publishes it (returns the final media
    id). `container_id` is kept for debugging / retry; `id` is the
    published media id."""

    id: str
    ig_user_id: str
    container_id: str | None = None
    caption: str | None = None
    permalink: str | None = None


@dataclass(frozen=True)
class AdCampaign:
    """A Marketing-API ad campaign under an ad account.

    `act_{ad_account_id}/campaigns` returns id / name / objective /
    status / effective_status. Reading campaigns needs the `ads_read`
    scope (App-Review-gated for production)."""

    id: str
    name: str | None = None
    objective: str | None = None
    status: str | None = None
    effective_status: str | None = None


@dataclass(frozen=True)
class AdInsights:
    """Flattened ad-insights metrics for an object (campaign / adset /
    ad / ad-account).

    Graph's `/{object-id}/insights` returns a `data` list of rows
    keyed by `level`; `metrics` flattens the first row's numeric
    fields (`impressions`, `reach`, `spend`, `clicks`, …) into a
    `{name: float}` map; `raw` keeps every row for consumers that need
    the breakdown / time-range detail."""

    object_id: str
    level: str
    metrics: dict[str, float] = field(default_factory=dict)
    raw: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MetaConnectionStatus:
    """Adapter introspection surface for `/api/meta/status`.

    `auth_mode` is one of `"system_user"` / `"user_oauth"` / `"none"`
    — surfaced so the operator can immediately tell which auth backend
    is active (the silent-empty-data failure mode on BM-owned assets is
    invisible otherwise — see session-notes §A.1 Blocker 2). `error`
    distinguishes "consent given but no data" from "needs reconnection"
    from "fully operational"."""

    configured: bool
    adapter: str  # "oauth" | "fake"
    auth_mode: str  # "system_user" | "user_oauth" | "none"
    consent_required: bool = True
    user_id: str | None = None
    user_name: str | None = None
    pages_count: int = 0
    instagram_accounts_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class AdSet:
    """A Marketing-API ad set (the targeting + budget + schedule layer
    between a campaign and its ads).

    `act_{ad_account_id}/adsets` returns id / name / status /
    daily_budget / billing_event / optimization_goal plus the parent
    `campaign_id`. Mutating ad sets needs the `ads_management` scope
    (App-Review-gated for production — distinct from the `ads_read`
    scope the read/insights surface uses)."""

    id: str
    name: str | None = None
    status: str | None = None
    effective_status: str | None = None
    campaign_id: str | None = None
    daily_budget: int | None = None
    billing_event: str | None = None
    optimization_goal: str | None = None
    targeting: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdCreative:
    """A Marketing-API ad creative (the rendered content an ad shows).

    `act_{ad_account_id}/adcreatives` returns id / name plus the
    object-story spec. Created under `ads_management`."""

    id: str
    name: str | None = None
    object_story_spec: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Ad:
    """A Marketing-API ad — the leaf binding an ad set to a creative.

    `act_{ad_account_id}/ads` returns id / name / status /
    effective_status plus the parent `adset_id` and the
    `creative_id` it renders. Created/updated under `ads_management`."""

    id: str
    name: str | None = None
    status: str | None = None
    effective_status: str | None = None
    adset_id: str | None = None
    creative_id: str | None = None


@dataclass(frozen=True)
class CampaignSpec:
    """Input spec for `create_ad_campaign`.

    `objective` is the Marketing-API campaign objective (e.g.
    `OUTCOME_TRAFFIC`, `OUTCOME_AWARENESS`). `status` defaults to
    `PAUSED` — a deliberate safety default: campaigns must be
    explicitly activated so a programmatic create never spends money
    by accident. `special_ad_categories` is **mandatory on Graph**
    (an empty list is the explicit "no special category" answer — the
    Marketing API rejects the call when the field is absent), so it
    defaults to an empty list rather than being omitted."""

    name: str
    objective: str
    status: str = "PAUSED"
    special_ad_categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AdSetSpec:
    """Input spec for `create_ad_set`.

    Binds to a parent `campaign_id`. `daily_budget` is in the ad
    account's minor currency unit (cents). `targeting` is the raw
    Graph targeting spec dict (passed through verbatim — too
    open-ended to model). `status` defaults to `PAUSED` (same
    no-accidental-spend safety default as `CampaignSpec`)."""

    name: str
    campaign_id: str
    daily_budget: int
    billing_event: str
    optimization_goal: str
    targeting: dict[str, Any] = field(default_factory=dict)
    status: str = "PAUSED"


@dataclass(frozen=True)
class AdCreativeSpec:
    """Input spec for `create_ad_creative`.

    `object_story_spec` is the raw Graph creative spec dict (page-id +
    link-data / video-data — passed through verbatim)."""

    name: str
    object_story_spec: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdSpec:
    """Input spec for `create_ad`.

    Binds an `adset_id` to a `creative_id`. `status` defaults to
    `PAUSED` (no-accidental-delivery safety default)."""

    name: str
    adset_id: str
    creative_id: str
    status: str = "PAUSED"


class MetaAdapter(Protocol):
    """Meta Graph read-only adapter contract. Concrete implementations:
    `FakeMetaAdapter` (deterministic in-memory; dev/test default),
    `MetaOAuthAdapter` (live Graph; dual auth — System User Token OR
    OAuth credential-store fallback).

    The factory `get_meta_adapter(...)` picks the concrete adapter:
    System User Token configured → OAuth adapter in `system_user`
    mode; OAuth credential row present → OAuth adapter in `user_oauth`
    mode; neither → `FakeMetaAdapter`.

    `auth_mode` mirrors `MetaConnectionStatus.auth_mode`. The contract
    carries both the read surface and the write/ads surface
    (`publish_facebook_post`, `publish_instagram_media`,
    `list_ad_campaigns`, `ad_insights`) — the write methods were added
    additively; pre-existing read callers are unaffected. On the live
    adapter the write/ads methods raise `MetaGraphError` with
    `requires_app_review` set when the gated scope is absent (never a
    silent or faked success)."""

    auth_mode: str

    def status(self) -> MetaConnectionStatus: ...

    def me(self) -> dict[str, Any]: ...

    def list_facebook_pages(self) -> list[FacebookPage]: ...

    def get_page(self, page_id: str) -> FacebookPage | None: ...

    def list_facebook_posts(
        self, page_id: str, limit: int = 25
    ) -> list[FacebookPost]: ...

    def get_facebook_post_insights(
        self, post_id: str, page_id: str | None = None
    ) -> PostInsights: ...

    def list_instagram_accounts(self) -> list[InstagramAccount]: ...

    def list_instagram_media(
        self, ig_user_id: str, limit: int = 25
    ) -> list[InstagramMedia]: ...

    def get_instagram_media_insights(self, media_id: str) -> PostInsights: ...

    # ─── Write / ads surface (additive — read callers unaffected) ──────

    def publish_facebook_post(
        self,
        page_id: str,
        message: str,
        link: str | None = None,
        photo_url: str | None = None,
    ) -> PublishedPost: ...

    def publish_instagram_media(
        self,
        ig_user_id: str,
        image_url: str,
        caption: str | None = None,
    ) -> PublishedMedia: ...

    def publish_instagram_carousel(
        self,
        ig_user_id: str,
        image_urls: list[str],
        caption: str | None = None,
    ) -> PublishedMedia: ...

    def list_ad_campaigns(
        self, ad_account_id: str
    ) -> list[AdCampaign]: ...

    def ad_insights(
        self,
        object_id: str,
        level: str,
        date_preset: str | None = None,
    ) -> AdInsights: ...

    # ─── Ads management surface (additive — read/insights/posting
    #    callers unaffected; distinct ``ads_management`` scope) ──────

    def create_ad_campaign(
        self, ad_account_id: str, spec: CampaignSpec
    ) -> AdCampaign: ...

    def create_ad_set(
        self, ad_account_id: str, spec: AdSetSpec
    ) -> AdSet: ...

    def create_ad_creative(
        self, ad_account_id: str, spec: AdCreativeSpec
    ) -> AdCreative: ...

    def create_ad(self, ad_account_id: str, spec: AdSpec) -> Ad: ...

    def update_campaign_status(
        self, campaign_id: str, status: str
    ) -> AdCampaign: ...

    def update_ad_set_budget(
        self, ad_set_id: str, daily_budget: int
    ) -> AdSet: ...


__all__ = [
    "Ad",
    "AdCampaign",
    "AdCreative",
    "AdCreativeSpec",
    "AdInsights",
    "AdSet",
    "AdSetSpec",
    "AdSpec",
    "CampaignSpec",
    "FacebookPage",
    "FacebookPost",
    "InstagramAccount",
    "InstagramMedia",
    "MetaAdapter",
    "MetaConnectionStatus",
    "PostInsights",
    "PublishedMedia",
    "PublishedPost",
]
