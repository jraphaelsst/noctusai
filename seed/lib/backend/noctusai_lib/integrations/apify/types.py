"""Value objects + errors for the Apify Instagram public-profile scraper.

Errors never carry the token or a raw response body: messages are built from
status codes / actor status only (`KB § PATTERNS/backend/seed-fake-real-adapter.md`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional, Protocol, runtime_checkable

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

HANDLE_PATTERN = r"^@?[a-zA-Z0-9._]{1,30}$"
MAX_POSTS_HARD_CAP = 200

MediaType = Literal["IMAGE", "VIDEO", "CAROUSEL_ALBUM"]


class ApifyError(Exception):
    """Base for every Apify adapter error."""


class ApifyNotConfigured(ApifyError, IntegrationNotConfigured):
    """No Apify token resolved."""


class ApifyProfileNotFound(ApifyError):
    """Unknown / private / empty profile. `reason` is `nao_encontrado` or `privado`."""

    def __init__(self, message: str = "profile not found", *, reason: str = "nao_encontrado"):
        super().__init__(message)
        self.reason = reason


class ApifyRateLimited(ApifyError):
    """429 / actor concurrency limit."""

    def __init__(self, message: str = "apify rate limited", *, retry_after_s: Optional[float] = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ApifyRunFailed(ApifyError):
    """Actor FAILED/ABORTED/TIMED-OUT, non-2xx, or a malformed item."""


@dataclass(frozen=True)
class InstagramPublicProfile:
    username: str
    full_name: Optional[str] = None
    biography: Optional[str] = None
    followers_count: Optional[int] = None
    follows_count: Optional[int] = None
    posts_count: Optional[int] = None
    profile_pic_url: Optional[str] = None
    is_private: bool = False
    is_business: Optional[bool] = None
    verified: Optional[bool] = None
    external_id: Optional[str] = None


@dataclass(frozen=True)
class InstagramPublicPost:
    id: str
    shortcode: str
    permalink: str
    media_type: MediaType
    owner_username: str
    timestamp: datetime  # UTC, tz-aware
    product_type: Optional[str] = None  # "clips" = reel
    caption: Optional[str] = None
    likes: Optional[int] = None  # Apify -1 (hidden) -> None
    comments: Optional[int] = None
    views: Optional[int] = None  # videoPlayCount ?? videoViewCount ?? None
    duration_s: Optional[float] = None
    display_url: Optional[str] = None
    video_url: Optional[str] = None


@dataclass(frozen=True)
class ApifyRunCost:
    results: int = 0
    usd: Optional[Decimal] = None  # None = not exposed by the response; never invented
    run_id: Optional[str] = None


@dataclass(frozen=True)
class InstagramProfileScrape:
    profile: InstagramPublicProfile
    posts: list[InstagramPublicPost] = field(default_factory=list)
    cost: ApifyRunCost = field(default_factory=ApifyRunCost)


@runtime_checkable
class InstagramScraper(Protocol):
    def scrape_profile(
        self,
        handle: str,
        *,
        max_posts: int,
        newer_than: Optional[date] = None,
        timeout_s: float = 240,
    ) -> InstagramProfileScrape: ...
