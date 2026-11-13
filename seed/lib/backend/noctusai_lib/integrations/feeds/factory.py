"""Factories for the feed source ports.

These sources need no credential (GitHub's token only raises its quota), so there is no
refuse state: `real=False` -> Fake, otherwise Real. A Fake is never selected implicitly.
"""
from __future__ import annotations

from typing import Optional

import httpx

from .fake_adapter import FakeArxivSource, FakeGithubSource, FakeHackerNewsSource, FakeRssSource
from .rss import RealRssSource
from .sources import RealArxivSource, RealGithubSource, RealHackerNewsSource
from .types import ArxivSource, GithubSource, HackerNewsSource, RssFeedSource


def get_rss_source(*, real: Optional[bool] = None,
                   transport: Optional[httpx.BaseTransport] = None) -> RssFeedSource:
    return FakeRssSource() if real is False else RealRssSource(transport=transport)


def get_hackernews_source(*, real: Optional[bool] = None,
                          transport: Optional[httpx.BaseTransport] = None) -> HackerNewsSource:
    return FakeHackerNewsSource() if real is False else RealHackerNewsSource(transport=transport)


def get_github_source(*, token: Optional[str] = None, real: Optional[bool] = None,
                      transport: Optional[httpx.BaseTransport] = None) -> GithubSource:
    return FakeGithubSource() if real is False else RealGithubSource(token=token, transport=transport)


def get_arxiv_source(*, real: Optional[bool] = None,
                     transport: Optional[httpx.BaseTransport] = None) -> ArxivSource:
    return FakeArxivSource() if real is False else RealArxivSource(transport=transport)
