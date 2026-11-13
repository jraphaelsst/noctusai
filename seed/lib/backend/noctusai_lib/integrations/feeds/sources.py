"""Real sources for the official JSON/Atom APIs: Hacker News (Firebase), GitHub (REST), arXiv (export API).

Each owns its rate bucket. All outbound goes through `FeedHttp` (limiter + single retry layer).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from ._http import FeedHttp, canonicalize_url
from .rss import _child, _local, _text, parse_date
from .types import FeedError, FeedFetchError, FeedItem, FeedParseError

logger = logging.getLogger(__name__)

HN_BASE = "https://hacker-news.firebaseio.com/v0"
HN_KINDS = {"top": "topstories", "new": "newstories", "best": "beststories",
            "ask": "askstories", "show": "showstories", "job": "jobstories"}
GITHUB_API = "https://api.github.com"
ARXIV_API = "https://export.arxiv.org/api/query"
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_LANG = re.compile(r"^[A-Za-z0-9#+.-]{1,40}$")
_SINCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        raise FeedParseError("source returned a non-JSON body") from None


def _unix(value: Any) -> Optional[datetime]:
    return datetime.fromtimestamp(value, tz=timezone.utc) if isinstance(value, (int, float)) else None


class RealHackerNewsSource:
    """Official HN API. Items are read one by one, so the bucket is the courtesy limit (5/s)."""

    def __init__(self, *, transport: Optional[httpx.BaseTransport] = None) -> None:
        self._http = FeedHttp(bucket="feeds:hackernews", rate_per_sec=5, burst=10, transport=transport)

    def fetch(self, kind: str = "top", *, limit: int = 30) -> list[FeedItem]:
        if kind not in HN_KINDS:
            raise ValueError(f"unknown hacker news list {kind!r}")
        ids = _json(self._http.get(f"{HN_BASE}/{HN_KINDS[kind]}.json"))
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise FeedParseError("hacker news id list has an unexpected shape")
        items: list[FeedItem] = []
        for story_id in ids[: max(1, min(limit, 100))]:
            raw = _json(self._http.get(f"{HN_BASE}/item/{story_id}.json"))
            if raw is None:
                continue  # HN returns null for removed ids; a normal case, not an error
            if not isinstance(raw, dict):
                raise FeedParseError(f"hacker news item {story_id} has an unexpected shape")
            if raw.get("deleted") or raw.get("dead"):
                continue
            if not raw.get("title"):
                raise FeedParseError(f"hacker news item {story_id} has an unexpected shape")
            discussion = f"https://news.ycombinator.com/item?id={story_id}"
            url = raw.get("url") or discussion
            items.append(FeedItem(
                source="hackernews", url=url, canonical_url=canonicalize_url(url), title=raw["title"],
                summary=raw.get("text"), author=raw.get("by"), published_at=_unix(raw.get("time")),
                raw={"id": story_id, "score": raw.get("score"), "comments": raw.get("descendants"),
                     "discussion_url": discussion, "type": raw.get("type")},
            ))
        return items


class RealGithubSource:
    """GitHub REST. `trending` has NO official API: it is approximated by the Search API as the
    most-starred repositories CREATED within the window ("hot new repos"), which is official,
    documented and ToS-safe; scraping github.com/trending is deliberately not done."""

    def __init__(self, *, token: Optional[str] = None, transport: Optional[httpx.BaseTransport] = None,
                 now: Optional[Callable[[], datetime]] = None) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Unauthenticated core limit is 60/h and search 10/min: pace to the tighter reality per mode.
        rate, burst = (0.5, 5) if token else (1 / 60, 3)
        self._http = FeedHttp(bucket="feeds:github", rate_per_sec=rate, burst=burst,
                              transport=transport, extra_headers=headers)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def releases(self, repo: str, *, limit: int = 10) -> list[FeedItem]:
        if not _REPO.match(repo or ""):
            raise ValueError(f"invalid github repo {repo!r}")
        rows = _json(self._http.get(f"{GITHUB_API}/repos/{repo}/releases",
                                    params={"per_page": max(1, min(limit, 100))}))
        if not isinstance(rows, list):
            raise FeedParseError("github releases body has an unexpected shape")
        out: list[FeedItem] = []
        for r in rows:
            if not isinstance(r, dict) or not r.get("html_url") or not (r.get("name") or r.get("tag_name")):
                raise FeedParseError("github release has an unexpected shape")
            if r.get("draft"):
                continue
            title = f"{repo} {r.get('name') or r['tag_name']}"
            out.append(FeedItem(
                source="github_release", url=r["html_url"], canonical_url=canonicalize_url(r["html_url"]),
                title=title, summary=r.get("body"), author=(r.get("author") or {}).get("login"),
                published_at=parse_date(r.get("published_at")),
                raw={"repo": repo, "tag": r.get("tag_name"), "prerelease": bool(r.get("prerelease"))},
            ))
        return out

    def trending(self, *, since: str = "daily", language: Optional[str] = None,
                 limit: int = 25) -> list[FeedItem]:
        if since not in _SINCE_DAYS:
            raise ValueError(f"since must be one of {sorted(_SINCE_DAYS)}")
        if language is not None and not _LANG.match(language):
            raise ValueError(f"invalid language {language!r}")
        day = (self._now() - timedelta(days=_SINCE_DAYS[since])).date().isoformat()
        q = f"created:>{day}" + (f" language:{language}" if language else "")
        body = _json(self._http.get(f"{GITHUB_API}/search/repositories", params={
            "q": q, "sort": "stars", "order": "desc", "per_page": max(1, min(limit, 100))}))
        rows = body.get("items") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise FeedParseError("github search body has an unexpected shape")
        out = []
        for r in rows:
            if not isinstance(r, dict) or not r.get("html_url") or not r.get("full_name"):
                raise FeedParseError("github repository has an unexpected shape")
            out.append(FeedItem(
                source="github_trending", url=r["html_url"], canonical_url=canonicalize_url(r["html_url"]),
                title=r["full_name"], summary=r.get("description"), author=(r.get("owner") or {}).get("login"),
                published_at=parse_date(r.get("created_at")),
                raw={"stars": r.get("stargazers_count"), "language": r.get("language"), "window": since,
                     "method": "search_created_window"},
            ))
        return out


class RealArxivSource:
    """arXiv export API. Its terms ask for at most one request per 3 seconds: bucket 1/3 s, burst 1."""

    def __init__(self, *, transport: Optional[httpx.BaseTransport] = None) -> None:
        self._http = FeedHttp(bucket="feeds:arxiv", rate_per_sec=1 / 3, burst=1, transport=transport)

    def search(self, query: str, *, max_results: int = 25) -> list[FeedItem]:
        query = (query or "").strip()
        if not query or len(query) > 300:
            raise ValueError("arxiv query must be 1-300 chars")
        resp = self._http.get(ARXIV_API, params={
            "search_query": query, "start": 0, "max_results": max(1, min(max_results, 100)),
            "sortBy": "submittedDate", "sortOrder": "descending"})
        try:
            root = fromstring(resp.content, forbid_dtd=True)
        except (ParseError, DefusedXmlException, ValueError) as exc:
            raise FeedParseError(f"arxiv response is not well-formed XML ({type(exc).__name__})") from None
        if _local(root.tag) != "feed":
            raise FeedParseError("arxiv response is not an Atom feed")
        out: list[FeedItem] = []
        for e in root:
            if _local(e.tag) != "entry":
                continue
            title = " ".join((_text(_child(e, "title")) or "").split())
            url = next((c.attrib.get("href") for c in e
                        if _local(c.tag) == "link" and c.attrib.get("rel", "alternate") == "alternate"), None)
            if not title or not url:
                raise FeedParseError("arxiv entry without title or link")
            authors = [_text(_child(a, "name")) for a in e if _local(a.tag) == "author"]
            summary = " ".join((_text(_child(e, "summary")) or "").split()) or None
            cats = [c.attrib.get("term") for c in e if _local(c.tag) == "category" and c.attrib.get("term")]
            out.append(FeedItem(
                source="arxiv", url=url, canonical_url=canonicalize_url(url), title=title, summary=summary,
                author=", ".join(a for a in authors if a) or None,
                published_at=parse_date(_text(_child(e, "published"))),
                raw={"id": _text(_child(e, "id")), "categories": cats},
            ))
        return out


__all__ = ["RealArxivSource", "RealGithubSource", "RealHackerNewsSource", "FeedError", "FeedFetchError"]
