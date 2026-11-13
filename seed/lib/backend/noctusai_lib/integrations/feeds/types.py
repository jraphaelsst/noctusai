"""Value objects, errors and ports for the content-feed source adapters.

Vendor payloads stop at each source's mapper: callers only ever see `FeedItem`.
Errors never carry a token or a raw response body.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

SourceKind = Literal["rss", "hackernews", "github_release", "github_trending", "arxiv"]


class FeedError(Exception):
    """Base for every feed adapter error."""


class FeedNotConfigured(FeedError, IntegrationNotConfigured):
    """A source that needs a credential was asked for without one."""


class FeedFetchError(FeedError):
    """Transport failure, non-2xx, oversize body, or a refused URL."""


class FeedParseError(FeedError):
    """The body was not the feed/JSON shape the source promises (malformed -> never silent)."""


class FeedRateLimited(FeedError):
    """429 (or an exhausted vendor quota). `retry_after_s` is the vendor's hint, if any."""

    def __init__(self, message: str = "feed source rate limited", *, retry_after_s: Optional[float] = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class FeedItem:
    source: SourceKind
    url: str
    canonical_url: str  # normalised for dedup (no tracking params / fragment / trailing slash)
    title: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None  # tz-aware UTC when known
    raw: dict[str, Any] = field(default_factory=dict)  # vendor fields kept for the raw item store


@dataclass(frozen=True)
class FetchValidators:
    """HTTP cache validators to persist per feed and send back next poll."""

    etag: Optional[str] = None
    last_modified: Optional[str] = None


@dataclass(frozen=True)
class FeedFetch:
    items: list[FeedItem] = field(default_factory=list)
    not_modified: bool = False  # 304: nothing new, `items` is empty by design
    validators: FetchValidators = field(default_factory=FetchValidators)


@runtime_checkable
class RssFeedSource(Protocol):
    def fetch(self, url: str, *, validators: Optional[FetchValidators] = None,
              max_items: int = 100) -> FeedFetch: ...


@runtime_checkable
class HackerNewsSource(Protocol):
    def fetch(self, kind: str = "top", *, limit: int = 30) -> list[FeedItem]: ...


@runtime_checkable
class GithubSource(Protocol):
    def releases(self, repo: str, *, limit: int = 10) -> list[FeedItem]: ...

    def trending(self, *, since: str = "daily", language: Optional[str] = None,
                 limit: int = 25) -> list[FeedItem]: ...


@runtime_checkable
class ArxivSource(Protocol):
    def search(self, query: str, *, max_results: int = 25) -> list[FeedItem]: ...
