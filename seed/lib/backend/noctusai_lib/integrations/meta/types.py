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
from datetime import date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class TokenBundle:
    """The full Graph `oauth/access_token` response, metadata preserved.

    The string-returning `exchange_code_for_token` /
    `exchange_for_long_lived` helpers drop everything but the token —
    fine for callers that only need the string, but a caller that wants
    to compute an expiry timestamp (so it can pre-emptively refresh the
    long-lived token before it lapses) needs `expires_in`. The `_bundle`
    variants return this instead.

    Graph's long-lived response is `{"access_token", "token_type",
    "expires_in"}`; the short-lived code exchange may omit `expires_in`
    (and sometimes `token_type`), so both are optional. `access_token`
    is always present — the response is a Graph error envelope
    (raised before construction) otherwise."""

    access_token: str
    expires_in: int | None = None
    token_type: str | None = None


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
    depend on it).

    `processing_duration_ms` is populated only for the **video / Reel**
    publish path (the asynchronous resumable-upload flow that polls a
    processing-status container until `FINISHED`) — it records the
    wall-clock the Real adapter spent waiting on Graph to transcode, so
    a consumer can log / surface slow renders. It stays `None` for the
    synchronous text / link / photo path (no processing wait)."""

    id: str
    page_id: str
    message: str | None = None
    permalink_url: str | None = None
    processing_duration_ms: int | None = None


@dataclass(frozen=True)
class PublishedMedia:
    """The result of publishing an Instagram media item.

    IG publish is a 2-step Graph flow: `POST /{ig-user}/media` creates
    a media *container* (returns a creation id), then `POST
    /{ig-user}/media_publish` publishes it (returns the final media
    id). `container_id` is kept for debugging / retry; `id` is the
    published media id.

    `processing_duration_ms` is populated only for the **Reel** publish
    path (`media_type=REELS` — an asynchronous resumable-upload flow
    that polls the container's `status_code` until `FINISHED` before
    `media_publish`). It records the wall-clock the Real adapter spent
    waiting on Graph to transcode the video, so a consumer can log /
    surface slow renders. It stays `None` for the synchronous image /
    carousel path (no processing wait)."""

    id: str
    ig_user_id: str
    container_id: str | None = None
    caption: str | None = None
    permalink: str | None = None
    processing_duration_ms: int | None = None
@dataclass(frozen=True)
class MediaProcessingStatus:
    """One reading of a video / Reel media container's processing state.

    The video publish flow is asynchronous: ``POST .../media`` (or
    ``.../video_reels``) returns a container creation id whose
    ``status_code`` is ``IN_PROGRESS`` while Graph transcodes. The
    publisher polls ``GET /{creation-id}?fields=status_code`` until it
    flips to ``FINISHED`` (publish-ready), ``ERROR`` (transcode failed
    — raise), or ``EXPIRED``. ``is_finished`` / ``is_error`` let the
    poll loop branch deterministically; ``raw`` keeps the original
    ``status`` envelope (Graph sometimes returns a richer ``status``
    string alongside the coarse ``status_code``)."""

    creation_id: str
    status_code: str  # IN_PROGRESS | FINISHED | ERROR | EXPIRED | PUBLISHED
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_finished(self) -> bool:
        """Ready to publish — ``status_code`` is ``FINISHED`` (or already
        ``PUBLISHED``, a no-op-safe terminal state)."""

        return self.status_code in ("FINISHED", "PUBLISHED")

    @property
    def is_error(self) -> bool:
        """Transcode failed (``ERROR``) or the upload window lapsed
        (``EXPIRED``) — a terminal failure the poll loop raises on."""

        return self.status_code in ("ERROR", "EXPIRED")


@dataclass(frozen=True)
class AdCampaign:
    """A Marketing-API ad campaign under an ad account.

    `act_{ad_account_id}/campaigns` returns id / name / objective /
    status / effective_status plus the OPTIONAL campaign-level budget
    fields. Reading campaigns needs the `ads_read` scope
    (App-Review-gated for production).

    `daily_budget` / `lifetime_budget` are populated ONLY for campaigns
    that use Campaign-Budget-Optimization (CBO, a.k.a. Advantage
    campaign budget) — the budget lives on the campaign itself. For
    ad-set-budget-optimization campaigns (ABO) these are `None` and the
    budget lives on each child `AdSet.daily_budget` instead; a consumer
    computing an effective campaign budget must fall back to summing the
    active ad sets. Both are the account's MINOR currency unit (cents),
    the same convention as `AdSet.daily_budget` — coerced to `int` via
    `_safe_int` (never a silent 0 on a missing/unset budget)."""

    id: str
    name: str | None = None
    objective: str | None = None
    status: str | None = None
    effective_status: str | None = None
    daily_budget: int | None = None
    lifetime_budget: int | None = None


@dataclass(frozen=True)
class AdAccount:
    """A Marketing-API ad account the authenticated identity can
    access.

    `me/adaccounts` returns id / name / currency / timezone_name /
    amount_spent / balance / spend_cap / account_status. Reading
    accounts needs the `ads_read` scope (App-Review-gated for
    production) — the same gate `list_ad_campaigns` uses; there is no
    separate discovery-specific scope.

    `id` is the BARE account id, WITHOUT the `act_` prefix. Graph's
    `me/adaccounts` edge returns `id` already prefixed (`act_123456`);
    `list_ad_accounts` strips it so `AdAccount.id` matches the bare-id
    convention every other `ad_account_id`-consuming method in this
    module expects — each of them re-adds the `act_` prefix
    internally (see `list_ad_campaigns`, `list_ad_sets`, `list_ads`).
    `amount_spent` / `balance` / `spend_cap` are kept as Graph's raw
    decimal STRINGS (minor-currency-unit values) rather than coerced
    to float/int — an unconditional numeric coercion risks precision
    loss on large accounts and Graph does not document the value as a
    plain integer. `account_status` is Graph's numeric account-status
    enum, kept as the raw int rather than mapped to a name here (Meta
    has extended this enum over time; a stale local name-map would
    silently misreport a newly-added status) — consult Meta's Ad
    Account Status enum docs to interpret the value."""

    id: str
    name: str | None = None
    currency: str | None = None
    timezone_name: str | None = None
    amount_spent: str | None = None
    balance: str | None = None
    spend_cap: str | None = None
    account_status: int | None = None


@dataclass(frozen=True)
class AdInsights:
    """Flattened ad-insights metrics for an object (campaign / adset /
    ad / ad-account).

    Graph's `/{object-id}/insights` returns a `data` list of rows
    keyed by `level`; `metrics` flattens the first row's numeric
    fields (`impressions`, `reach`, `spend`, `clicks`, …) into a
    `{name: float}` map; `raw` keeps every row for consumers that need
    the breakdown / time-range detail.

    Kept AS-IS for back-compat — existing callers depend on the
    first-row-only shape. `ad_insights_series` / `AdInsightsSeries`
    below is the fixed multi-row / conversion-metrics-aware sibling;
    prefer it for anything beyond a single-row account-total peek."""

    object_id: str
    level: str
    metrics: dict[str, float] = field(default_factory=dict)
    raw: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AdInsightsRow:
    """One row of an ad-insights TIME SERIES (`AdInsightsSeries.rows`).

    Distinct from `AdInsights.metrics` (which flattens only the FIRST
    row of a `/insights` response — kept as-is there for back-compat).
    `date_start`/`date_stop` are Graph's per-row window bounds
    (present whenever `time_increment` splits the pull into daily /
    monthly slices). `breakdown` holds the requested `breakdowns`
    dimension values for THIS row (e.g.
    `{"publisher_platform": "instagram"}`) when the series was
    requested with `breakdowns=[...]`; empty otherwise. `metrics`
    flattens the plain numeric fields (excludes `actions` /
    `action_values`, parsed separately below, and excludes whatever
    keys `breakdown` already claimed).

    `actions`/`action_values` are Graph's conversion-metrics edges —
    each a list of `{"action_type": str, "value": str}` rows, folded
    here into `{action_type: float}` maps. This exists BECAUSE the
    old single-row flatten (`float(val)` inside a bare
    `except (TypeError, ValueError): continue`) silently dropped BOTH
    fields entirely — a list value never survives `float()`, so every
    conversion metric vanished with no error, no log, nothing. `raw`
    keeps the untouched row for anything this mapper doesn't model."""

    date_start: str | None = None
    date_stop: str | None = None
    breakdown: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    actions: dict[str, float] = field(default_factory=dict)
    action_values: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdInsightsSeries:
    """The full multi-row result of `ad_insights_series(...)` — EVERY
    row Graph returned, not just the first (see `AdInsightsRow` for
    why `AdInsights.metrics` alone is insufficient for a time-series
    pull). A 12-month `time_increment=1` daily pull returns up to
    ~365 `rows`; the adapter follows `paging.next` to collect all of
    them — a single Graph page is not guaranteed to hold that many."""

    object_id: str
    level: str
    rows: list[AdInsightsRow] = field(default_factory=list)


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
    `creative_id` it renders. Created/updated under `ads_management`.

    `creative_thumbnail_url` / `creative_object_story_spec` are
    populated by the READ surface (`list_ads`), which requests a
    nested `creative{id,thumbnail_url,object_story_spec}` expansion so
    a UI can render a thumbnail without a second round-trip per ad;
    the ads-*management* write surface (`create_ad`) leaves them at
    their `None` / `{}` defaults since Graph's ad-creation response
    doesn't expand the creative it just bound."""

    id: str
    name: str | None = None
    status: str | None = None
    effective_status: str | None = None
    adset_id: str | None = None
    creative_id: str | None = None
    creative_thumbnail_url: str | None = None
    creative_object_story_spec: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdActivity:
    """One row of an ad account's change log (`act_{id}/activities`)
    — the intra-day status-flip history a daily insights snapshot
    cannot see (an operator activating → pausing → reactivating a
    campaign within one calendar day is only visible here).

    Meta's Activities edge is an audit log, not a first-class Graph
    node — Graph does NOT return a stable per-row `id` on this edge
    (unlike campaigns/adsets/ads). `id` here is therefore a LOCALLY
    SYNTHESIZED composite key (`{object_id}:{event_time}:{event_type}`),
    useful only as a caller-side dict/dedup key — it is NOT a Graph
    object id and is not guaranteed stable across a Graph API version
    change. This is asserted from Meta's public Marketing API
    documentation, NOT confirmed against a live token (`ads_read` is
    not yet granted for this app — roadmap trigger T1); reconcile
    against a live pull once available.

    `object_level` mirrors Graph's `object_type` field (e.g.
    `"campaign"` / `"ad_set"` / `"ad"`). `event_type` is Graph's raw
    event-type string. `old_value`/`new_value` are populated only for
    event types whose `extra_data` payload carries a before/after pair
    (status flips, budget changes); many other event types carry a
    different `extra_data` shape, which is preserved verbatim on `raw`
    even when `old_value`/`new_value` are `None`. `occurred_at` is
    Graph's `event_time`, parsed into a tz-aware datetime — this is
    the field that carries the intra-day fidelity."""

    id: str
    object_id: str | None = None
    object_level: str | None = None
    event_type: str | None = None
    occurred_at: datetime | None = None
    actor_name: str | None = None
    actor_id: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LeadgenQuestion:
    """One question on a lead-gen (Instant Form) form — the FIELD SCHEMA
    a lead's `field_data` answers map onto.

    `key` is the stable answer key Graph echoes back in a lead's
    `field_data[].name` (e.g. `full_name`, `phone_number`, `email`, or
    the raw custom-question text). `type` is Graph's field type
    (`FULL_NAME` / `PHONE` / `EMAIL` / `CUSTOM` / `CITY` / …). `options`
    is populated only for choice-type CUSTOM questions (each a
    `{"key","value"}` pair). Reading the form + its questions needs only
    a Page token (`pages_show_list`/`pages_read_engagement`) — NOT the
    `leads_retrieval` scope the actual lead RECORDS require; so the
    schema is knowable even when the answers are still gated."""

    key: str | None = None
    label: str | None = None
    type: str | None = None
    options: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class LeadgenForm:
    """A Page's lead-gen (Instant Form) form (`{page_id}/leadgen_forms`).

    `leads_count` is Graph's cumulative submitted-lead counter for the
    form (accessible WITHOUT `leads_retrieval` — it is a form-level
    metric, not lead PII). `questions` is the field schema (see
    `LeadgenQuestion`). Reading forms needs a Page token; reading the
    per-form lead RECORDS additionally needs `leads_retrieval` (a
    distinct, separately-granted scope — a form list can succeed while
    `list_leads` raises a `(#200) Requires leads_retrieval` error)."""

    id: str
    name: str | None = None
    status: str | None = None
    locale: str | None = None
    leads_count: int | None = None
    created_time: datetime | None = None
    page_id: str | None = None
    questions: list[LeadgenQuestion] = field(default_factory=list)


@dataclass(frozen=True)
class PageSubscription:
    """One app's webhook subscription on a Page (`GET
    /{page_id}/subscribed_apps`). `subscribed_fields` is Graph's
    per-app list of field names (e.g. `"leadgen"`) the Page is
    currently subscribed to for that app — the introspection
    counterpart to `subscribe_page_to_leadgen` (confirm a subscription
    actually took, or discover what's already wired). `page_id` is
    injected by the mapper (Graph's row doesn't itself carry it) — the
    same seam `LeadgenForm.page_id` uses."""

    app_id: str
    app_name: str | None = None
    page_id: str | None = None
    subscribed_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LeadFieldEntry:
    """One answered field on a lead — a `{name, values}` pair from a
    lead's `field_data`. `name` matches a `LeadgenQuestion.key`;
    `values` is Graph's list (usually one element)."""

    name: str | None = None
    values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Lead:
    """One submitted lead record (`{form_id}/leads` or `{ad_id}/leads`).

    **Production gate:** reading leads needs the `leads_retrieval` scope
    (distinct from `ads_read`/`pages_*`); absent it Graph raises
    `MetaGraphError` `(#200) Requires leads_retrieval permission`. The
    ad/campaign attribution (`ad_id`/`campaign_id`/…) ties a lead back to
    the spend surfaced in the ads console. `field_data` carries the
    answers (PII: name/phone/email + the qualifying-question responses);
    `is_organic` is True for a lead that came through the form outside a
    paid ad. `created_time` is the submission timestamp."""

    id: str
    created_time: datetime | None = None
    form_id: str | None = None
    ad_id: str | None = None
    ad_name: str | None = None
    adset_id: str | None = None
    adset_name: str | None = None
    campaign_id: str | None = None
    campaign_name: str | None = None
    platform: str | None = None
    is_organic: bool | None = None
    field_data: list[LeadFieldEntry] = field(default_factory=list)


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


@dataclass(frozen=True)
class InstagramComment:
    """A comment (or reply) on an Instagram media item.

    Meta's IG Comments edge shape drifts by Graph version (fields
    like `hidden` / `parent_id` were added after the original
    `instagram_manage_comments` launch) — `raw` preserves the full
    response body so a consumer needing an unmodeled field reads it
    from there rather than the adapter silently dropping it."""

    id: str
    text: str | None = None
    username: str | None = None
    timestamp: datetime | None = None
    like_count: int = 0
    hidden: bool = False
    parent_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FacebookComment:
    """A comment (or reply) on a Facebook Page post.

    `from_id` / `from_name` are the commenter's identity (`from`
    nested object); `parent_id` is populated only for a reply. `raw`
    preserves the full response body — same defensive-mapping posture
    as `InstagramComment` (Graph's comment shape drifts by version)."""

    id: str
    message: str | None = None
    from_id: str | None = None
    from_name: str | None = None
    created_time: datetime | None = None
    like_count: int = 0
    is_hidden: bool = False
    parent_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Conversation:
    """An Instagram Direct conversation thread
    (`/{ig-user-id}/conversations?platform=instagram`).

    `participant_ids` flattens the `participants.data[].id` edge.
    `raw` keeps the full row — the conversations list edge's field
    surface is thin and version-sensitive, so a consumer needing more
    than the participant set reads it from `raw`."""

    id: str
    participant_ids: list[str] = field(default_factory=list)
    updated_time: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DirectMessage:
    """One message inside an Instagram Direct conversation.

    `conversation_id` is populated by the caller (the message body
    itself does not carry it back) when read via
    `list_instagram_messages`; `sender_id` / `recipient_id` come from
    the `from` / `to` nested objects. `raw` keeps the full body."""

    id: str
    conversation_id: str | None = None
    sender_id: str | None = None
    recipient_id: str | None = None
    text: str | None = None
    created_time: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


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
    `publish_instagram_carousel`, `publish_instagram_reel`,
    `publish_facebook_video`, `list_ad_campaigns`, `ad_insights`) — the
    write methods were added additively; pre-existing read callers are
    unaffected. The video / Reel methods use a different Graph contract
    than the image methods (asynchronous resumable upload + a
    processing-status poll until `FINISHED`) but the same typed error
    model. On the live adapter the write/ads methods raise
    `MetaGraphError` with `requires_app_review` set when the gated scope
    is absent (never a silent or faked success)."""

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

    def get_facebook_page_insights(
        self,
        page_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights: ...

    def list_instagram_accounts(self) -> list[InstagramAccount]: ...

    def list_instagram_media(
        self, ig_user_id: str, limit: int = 25
    ) -> list[InstagramMedia]: ...

    def get_instagram_media_insights(self, media_id: str) -> PostInsights: ...

    def get_instagram_account_insights(
        self,
        ig_user_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights: ...

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
    def publish_instagram_reel(
        self,
        ig_user_id: str,
        video_url: str,
        caption: str | None = None,
    ) -> PublishedMedia: ...

    def publish_facebook_video(
        self,
        page_id: str,
        video_url: str,
        description: str | None = None,
        *,
        as_reel: bool = False,
    ) -> PublishedPost: ...

    def list_ad_campaigns(
        self, ad_account_id: str
    ) -> list[AdCampaign]: ...

    def ad_insights(
        self,
        object_id: str,
        level: str,
        date_preset: str | None = None,
    ) -> AdInsights: ...

    # ─── Ads-read surface, W1 completion (additive — `list_ad_campaigns`
    #    / `ad_insights` above unchanged) ────────────────────────────

    def list_ad_accounts(self) -> list[AdAccount]: ...

    def list_ad_sets(
        self, ad_account_id: str, campaign_id: str | None = None
    ) -> list[AdSet]: ...

    def list_ads(
        self, ad_account_id: str, adset_id: str | None = None
    ) -> list[Ad]: ...

    def ad_insights_series(
        self,
        object_id: str,
        level: str,
        *,
        time_range: tuple[date, date] | None = None,
        date_preset: str | None = None,
        time_increment: int | str = 1,
        breakdowns: list[str] | None = None,
        action_attribution_windows: list[str] | None = None,
        fields: list[str] | None = None,
    ) -> AdInsightsSeries: ...

    def list_activities(
        self, ad_account_id: str, since: int, until: int
    ) -> list[AdActivity]: ...

    # ─── Lead-ads read surface (additive — Page-scoped; form list +
    #    schema need only a Page token, lead RECORDS need the distinct
    #    ``leads_retrieval`` scope) ──────────────────────────────────

    def list_leadgen_forms(
        self, page_id: str, *, with_questions: bool = False
    ) -> list[LeadgenForm]: ...

    def get_leadgen_form(
        self, form_id: str, *, page_id: str | None = None
    ) -> LeadgenForm: ...

    def list_leads(
        self, form_id: str, *, page_id: str | None = None, limit: int = 100
    ) -> list[Lead]: ...

    # ─── Lead-ads webhook surface (additive — Page-scoped subscription
    #    management; parsing the actual webhook DELIVERY is a pure
    #    function, `leadgen_webhook.parse_leadgen_webhook` — outside
    #    this IO Protocol by design) ───────────────────────────────────

    def get_lead(self, leadgen_id: str, *, page_id: str | None = None) -> Lead: ...

    def subscribe_page_to_leadgen(
        self, page_id: str, *, fields: tuple[str, ...] = ("leadgen",)
    ) -> bool: ...

    def list_page_subscribed_apps(
        self, page_id: str
    ) -> list[PageSubscription]: ...

    def unsubscribe_page_from_leadgen(self, page_id: str) -> bool: ...

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

    # ─── IG comments (additive — `instagram_manage_comments` scope) ────

    def list_instagram_comments(
        self, media_id: str, limit: int = 25
    ) -> list[InstagramComment]: ...

    def create_instagram_comment(
        self, media_id: str, message: str
    ) -> InstagramComment: ...

    def reply_instagram_comment(
        self, comment_id: str, message: str
    ) -> InstagramComment: ...

    def hide_instagram_comment(
        self, comment_id: str, hide: bool = True
    ) -> None: ...

    def delete_instagram_comment(self, comment_id: str) -> None: ...

    # ─── IG Direct messages (additive — `instagram_manage_messages`
    #    scope) ───────────────────────────────────────────────────────

    # Facebook-Login model: IG Direct is served through the linked
    # Facebook Page (page_id + Page token), NOT the IG-user node — the
    # IG-user shape is the Instagram-Login model and returns Graph (#3)
    # here. See MetaOAuthAdapter.list_instagram_conversations.
    def list_instagram_conversations(
        self, page_id: str, limit: int = 25
    ) -> list[Conversation]: ...

    def list_instagram_messages(
        self, conversation_id: str, page_id: str, limit: int = 25
    ) -> list[DirectMessage]: ...

    def send_instagram_message(
        self, page_id: str, recipient_id: str, text: str
    ) -> DirectMessage: ...

    # ─── IG Stories (additive — `instagram_content_publish` scope,
    #    same gate as the image/carousel/Reel publish surface) ───────

    def publish_instagram_story(
        self,
        ig_user_id: str,
        media_url: str,
        *,
        is_video: bool = False,
    ) -> PublishedMedia: ...

    # ─── FB comment moderation (additive — `pages_manage_engagement`
    #    scope) ───────────────────────────────────────────────────────

    def list_facebook_comments(
        self, post_id: str, limit: int = 25
    ) -> list[FacebookComment]: ...

    def create_facebook_comment(
        self, post_id: str, message: str
    ) -> FacebookComment: ...

    def reply_facebook_comment(
        self, comment_id: str, message: str
    ) -> FacebookComment: ...

    def hide_facebook_comment(
        self, comment_id: str, hide: bool = True
    ) -> None: ...

    def delete_facebook_comment(self, comment_id: str) -> None: ...


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
    "Conversation",
    "DirectMessage",
    "FacebookComment",
    "FacebookPage",
    "FacebookPost",
    "InstagramAccount",
    "InstagramComment",
    "InstagramMedia",
    "Lead",
    "LeadFieldEntry",
    "LeadgenForm",
    "LeadgenQuestion",
    "MediaProcessingStatus",
    "MetaAdapter",
    "MetaConnectionStatus",
    "PageSubscription",
    "PostInsights",
    "PublishedMedia",
    "PublishedPost",
    "TokenBundle",
]
