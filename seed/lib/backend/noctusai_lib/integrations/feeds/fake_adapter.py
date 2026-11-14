"""Deterministic Fakes for the four source ports (RSS, HN, GitHub, arXiv).

Same shapes and the same argument validation as the Reals; scripted items in, recorded calls out.
"""
from __future__ import annotations

from typing import Mapping, Optional

from .sources import HN_KINDS, _LANG, _REPO, _SINCE_DAYS
from .types import FeedError, FeedFetch, FeedItem, FetchValidators


class _Scripted:
    def __init__(self, items: Optional[Mapping[str, list[FeedItem]]] = None, *,
                 raises: Optional[FeedError] = None) -> None:
        self._items = {k: list(v) for k, v in (items or {}).items()}
        self._raises = raises
        self.calls: list[tuple[str, dict]] = []

    def _get(self, op: str, key: str, limit: int, **kw) -> list[FeedItem]:
        self.calls.append((op, {"key": key, **kw}))
        if self._raises is not None:
            raise self._raises
        return list(self._items.get(key, []))[: max(1, limit)]


class FakeRssSource(_Scripted):
    """Items keyed by feed url. Honours conditional GET: a matching etag -> `not_modified`."""

    def __init__(self, items=None, *, etag: Optional[str] = "fake-etag",
                 last_modified: Optional[str] = None, raises: Optional[FeedError] = None) -> None:
        super().__init__(items, raises=raises)
        self._validators = FetchValidators(etag=etag, last_modified=last_modified)

    def fetch(self, url: str, *, validators: Optional[FetchValidators] = None,
              max_items: int = 100) -> FeedFetch:
        if not url.startswith(("http://", "https://")):
            raise ValueError("feed url must be http(s)")
        if validators and validators.etag and validators.etag == self._validators.etag:
            self.calls.append(("rss", {"key": url, "not_modified": True}))
            return FeedFetch(items=[], not_modified=True, validators=validators)
        return FeedFetch(items=self._get("rss", url, max_items), validators=self._validators)


class FakeHackerNewsSource(_Scripted):
    """Items keyed by list kind (`top`, `new`, ...)."""

    def fetch(self, kind: str = "top", *, limit: int = 30) -> list[FeedItem]:
        if kind not in HN_KINDS:
            raise ValueError(f"unknown hacker news list {kind!r}")
        return self._get("hackernews", kind, limit)


class FakeGithubSource(_Scripted):
    """Releases keyed by repo; trending keyed `"trending"`."""

    def releases(self, repo: str, *, limit: int = 10) -> list[FeedItem]:
        if not _REPO.match(repo or ""):
            raise ValueError(f"invalid github repo {repo!r}")
        return self._get("releases", repo, limit)

    def trending(self, *, since: str = "daily", language: Optional[str] = None,
                 limit: int = 25) -> list[FeedItem]:
        if since not in _SINCE_DAYS:
            raise ValueError(f"since must be one of {sorted(_SINCE_DAYS)}")
        if language is not None and not _LANG.match(language):
            raise ValueError(f"invalid language {language!r}")
        return self._get("trending", "trending", limit, since=since, language=language)


class FakeArxivSource(_Scripted):
    """Items keyed by the exact query string."""

    def search(self, query: str, *, max_results: int = 25) -> list[FeedItem]:
        query = (query or "").strip()
        if not query or len(query) > 300:
            raise ValueError("arxiv query must be 1-300 chars")
        return self._get("arxiv", query, max_results)
