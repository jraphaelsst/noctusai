"""Content-feed sources (RSS/Atom, Hacker News, GitHub releases + trending, arXiv) — Protocol + Fake + Real + factory.

Every source emits the normalised `FeedItem`; each has its own rate bucket and goes only through
the shared limiter-wrapped client. Built for the newsletters collector (Wave 0).
"""
from ._http import canonicalize_url
from .factory import get_arxiv_source, get_github_source, get_hackernews_source, get_rss_source
from .fake_adapter import FakeArxivSource, FakeGithubSource, FakeHackerNewsSource, FakeRssSource
from .rss import RealRssSource, parse_feed
from .sources import RealArxivSource, RealGithubSource, RealHackerNewsSource
from .types import (
    ArxivSource, FeedError, FeedFetch, FeedFetchError, FeedItem, FeedNotConfigured, FeedParseError,
    FeedRateLimited, FetchValidators, GithubSource, HackerNewsSource, RssFeedSource, SourceKind,
)

__all__ = [
    "ArxivSource", "FakeArxivSource", "FakeGithubSource", "FakeHackerNewsSource", "FakeRssSource",
    "FeedError", "FeedFetch", "FeedFetchError", "FeedItem", "FeedNotConfigured", "FeedParseError",
    "FeedRateLimited", "FetchValidators", "GithubSource", "HackerNewsSource", "RealArxivSource",
    "RealGithubSource", "RealHackerNewsSource", "RealRssSource", "RssFeedSource", "SourceKind",
    "canonicalize_url", "get_arxiv_source", "get_github_source", "get_hackernews_source",
    "get_rss_source", "parse_feed",
]
