"""Meta (Facebook + Instagram) Graph API adapter value objects + Protocol.

Lifted into seed 2026-05-16 by `projects/social-wiring-absorption/`
Wave 1.E4 from the live-validated `noctusai-youtube-crawler`
`feat/meta-integrations` + `integration/oauth-discovery` branches.
The originating workspace was a functions-development environment;
this is the canonical seed home — sibling to `google_calendar/`,
`google_maps/`, `google_drive/`, `vista/`.

Read-only v1 (Facebook Pages + posts + post-insights; Instagram
Business accounts + media + media-insights). Posting (FB Page post,
IG publish) is **out of scope** but the Protocol is shaped so write
methods are an additive extension (extend the Protocol, add methods to
the OAuth adapter only — the Fake gets no-ops). See the project doc
§4 Out-of-scope and the session-notes addendum for the rationale.

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


class MetaAdapter(Protocol):
    """Meta Graph read-only adapter contract. Concrete implementations:
    `FakeMetaAdapter` (deterministic in-memory; dev/test default),
    `MetaOAuthAdapter` (live Graph; dual auth — System User Token OR
    OAuth credential-store fallback).

    The factory `get_meta_adapter(...)` picks the concrete adapter:
    System User Token configured → OAuth adapter in `system_user`
    mode; OAuth credential row present → OAuth adapter in `user_oauth`
    mode; neither → `FakeMetaAdapter`.

    `auth_mode` mirrors `MetaConnectionStatus.auth_mode`. Posting is
    intentionally absent from the contract (read-only v1); a future
    write surface extends this Protocol additively."""

    auth_mode: str

    def status(self) -> MetaConnectionStatus: ...

    def list_facebook_pages(self) -> list[FacebookPage]: ...

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


__all__ = [
    "FacebookPage",
    "FacebookPost",
    "InstagramAccount",
    "InstagramMedia",
    "MetaAdapter",
    "MetaConnectionStatus",
    "PostInsights",
]
