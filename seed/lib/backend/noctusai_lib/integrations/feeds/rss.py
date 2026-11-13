"""RSS 2.0 / RSS 1.0 (RDF) / Atom parsing + the Real RSS source (conditional GET)."""
from __future__ import annotations

import email.utils
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from ._http import FeedHttp, assert_public_http_url, canonicalize_url
from .types import FeedFetch, FeedItem, FeedParseError, FetchValidators

logger = logging.getLogger(__name__)
_TAG = re.compile(r"<[^>]+>")


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(el) -> Optional[str]:
    if el is None:
        return None
    t = "".join(el.itertext()).strip()
    return t or None


def _child(el, *names: str):
    if el is None:
        return None
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """RFC 822 or ISO 8601 -> tz-aware UTC; unparseable -> None (the field is optional, the item is kept)."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _link(el) -> Optional[str]:
    for c in el:
        if _local(c.tag) != "link":
            continue
        href = c.attrib.get("href")
        if href and c.attrib.get("rel", "alternate") == "alternate":
            return href.strip()
        if not href and _text(c):  # RSS: <link>text</link>
            return _text(c)
    return None


def parse_feed(body: bytes) -> list[FeedItem]:
    """Parse a feed body. Malformed XML / unknown root / a feed whose entries are ALL unusable
    raise `FeedParseError`; an individual entry lacking link or title is skipped with a warning."""
    try:
        root = fromstring(body, forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise FeedParseError(f"feed is not well-formed XML ({type(exc).__name__})") from None
    kind = _local(root.tag)
    if kind == "rss":
        channel = _child(root, "channel")
        entries = [e for e in (channel if channel is not None else []) if _local(e.tag) == "item"]
    elif kind == "feed":
        entries = [e for e in root if _local(e.tag) == "entry"]
    elif kind == "RDF":
        entries = [e for e in root if _local(e.tag) == "item"]
    else:
        raise FeedParseError(f"unrecognised feed root <{kind}>")
    items: list[FeedItem] = []
    skipped = 0
    for e in entries:
        url, title = _link(e), _text(_child(e, "title"))
        if not url or not title:
            skipped += 1
            continue
        summary = _text(_child(e, "description", "summary", "content", "encoded"))
        author_el = _child(e, "author", "creator")
        name_el = _child(author_el, "name")
        author = _text(name_el if name_el is not None else author_el)
        items.append(FeedItem(
            source="rss", url=url, canonical_url=canonicalize_url(url), title=title,
            summary=_TAG.sub("", summary).strip() if summary else None, author=author,
            published_at=parse_date(_text(_child(e, "pubDate", "published", "updated", "date"))),
            raw={"guid": _text(_child(e, "guid", "id"))},
        ))
    if skipped:
        logger.warning("feed: skipped %d of %d entries without link/title", skipped, len(entries))
        if not items:
            raise FeedParseError("feed has entries but none with a link and title")
    return items


class RealRssSource:
    def __init__(self, *, transport: Optional[httpx.BaseTransport] = None) -> None:
        self._transport = transport
        self._clients: dict[str, FeedHttp] = {}

    def _http(self, host: str) -> FeedHttp:
        # One bucket per host: politeness is owed to each publisher separately.
        if host not in self._clients:
            self._clients[host] = FeedHttp(bucket=f"feeds:rss:{host}", rate_per_sec=0.5, burst=2,
                                           transport=self._transport)
        return self._clients[host]

    def fetch(self, url: str, *, validators: Optional[FetchValidators] = None,
              max_items: int = 100) -> FeedFetch:
        assert_public_http_url(url)
        cond = {}
        if validators and validators.etag:
            cond["If-None-Match"] = validators.etag
        if validators and validators.last_modified:
            cond["If-Modified-Since"] = validators.last_modified
        resp = self._http(urlsplit(url).hostname or "").get(url, headers=cond, allow_304=True)
        if resp.status_code == 304:
            return FeedFetch(items=[], not_modified=True, validators=validators or FetchValidators())
        new = FetchValidators(etag=resp.headers.get("etag"), last_modified=resp.headers.get("last-modified"))
        return FeedFetch(items=parse_feed(resp.content)[: max(1, max_items)], validators=new)
