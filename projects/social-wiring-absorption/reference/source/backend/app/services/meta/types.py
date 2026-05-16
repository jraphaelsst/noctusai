"""Meta (Facebook + Instagram) read-only adapter contract.

Same Protocol-then-impls shape as the ``calendar/`` and ``drive_api/``
packages. The chatbot's Meta tools call these methods; the OAuth
adapter hits Graph API; the Fake adapter answers from memory.

v1 is **read-only**. Posting to FB Page or Instagram requires
``pages_manage_posts`` / ``instagram_content_publish`` permissions and
ships in a future iteration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class FacebookPage:
    """One Facebook Page the user manages.

    ``access_token`` here is a **page token** issued by ``/me/accounts``
    after the user consents. It inherits the user-token's lifetime but
    never expires on its own as long as the user token stays valid.
    Page tokens are what we use for every per-page Graph call (posts,
    insights, IG business account lookup).
    """

    page_id: str
    name: str
    category: str | None
    access_token: str
    fan_count: int | None = None
    followers_count: int | None = None
    link: str | None = None
    tasks: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InstagramAccount:
    """An Instagram Business / Creator account linked to a Facebook
    Page. We can only see IG accounts that have been **connected to a
    Page** the user manages — IG accounts not linked to any Page are
    invisible to the Graph API on the user's behalf.
    """

    ig_user_id: str
    username: str
    name: str | None
    profile_picture_url: str | None
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None
    biography: str | None = None
    website: str | None = None
    linked_page_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FacebookPost:
    """One post on a Facebook Page.

    ``permalink_url`` is the user-facing link (``facebook.com/...``).
    ``id`` is the Graph API id (``{page_id}_{post_id}``), which is what
    we use for ``get_facebook_post_insights``.
    """

    id: str
    page_id: str
    message: str | None
    created_at: datetime | None
    permalink_url: str | None
    full_picture: str | None = None
    attachments_summary: list[str] = field(default_factory=list)
    likes_count: int | None = None
    comments_count: int | None = None
    shares_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InstagramMedia:
    """One Instagram post / reel / story.

    ``media_type`` is one of ``IMAGE`` / ``VIDEO`` / ``CAROUSEL_ALBUM``.
    Stories require a separate endpoint (``/stories``) and are skipped
    in v1.
    """

    id: str
    ig_user_id: str
    caption: str | None
    media_type: str
    media_url: str | None
    permalink: str | None
    thumbnail_url: str | None
    timestamp: datetime | None
    like_count: int | None = None
    comments_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PostInsights:
    """Insight metrics for a single Facebook post or Instagram media.

    ``period`` is the rollup window the metric was computed over
    (``lifetime`` for most engagement counts, ``day`` / ``week`` for
    reach-style metrics). ``metrics`` is a dict ``{name: value}`` so
    callers don't have to know Graph's per-metric response shape.
    """

    object_id: str
    period: str
    metrics: dict[str, int | float]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetaConnectionStatus:
    """Summary of "is Meta wired up?" for the status router + chatbot
    self-check. Used to distinguish "needs consent" from "credentials
    not configured" from "fully connected"."""

    configured: bool       # env vars set
    consent_granted: bool  # CredentialStore has a row for this org
    user_name: str | None
    pages_count: int
    instagram_accounts_count: int
    error: str | None = None


class MetaAdapter(Protocol):
    """Read-only Meta surface the chatbot uses."""

    def list_pages(self) -> list[FacebookPage]: ...

    def get_page(self, page_id: str) -> FacebookPage | None: ...

    def list_facebook_posts(
        self,
        page_id: str,
        *,
        limit: int = 10,
    ) -> list[FacebookPost]: ...

    def get_facebook_post_insights(
        self,
        post_id: str,
        *,
        page_id: str | None = None,
    ) -> PostInsights | None: ...

    def list_instagram_accounts(self) -> list[InstagramAccount]: ...

    def list_instagram_media(
        self,
        ig_user_id: str,
        *,
        limit: int = 10,
    ) -> list[InstagramMedia]: ...

    def get_instagram_media_insights(
        self,
        media_id: str,
    ) -> PostInsights | None: ...

    def me(self) -> dict[str, Any]: ...
