from datetime import datetime, timezone

import httpx
import pytest

from noctusai_lib.integrations.feeds import (
    FakeArxivSource, FakeGithubSource, FakeHackerNewsSource, FakeRssSource, FeedFetchError, FeedItem,
    FeedParseError, FeedRateLimited, FetchValidators, RealArxivSource, RealGithubSource,
    RealHackerNewsSource, RealRssSource, canonicalize_url, get_arxiv_source, get_github_source,
    get_hackernews_source, get_rss_source, parse_feed,
)
from noctusai_lib.integrations.feeds._http import USER_AGENT
from noctusai_lib.integrations.rate_limit import RetryLater, limiter

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Hello</title><link>https://ex.com/a/?utm_source=x&amp;id=2#frag</link>
<description>&lt;p&gt;Body &lt;b&gt;bold&lt;/b&gt;&lt;/p&gt;</description><pubDate>Fri, 13 Nov 2026 09:00:00 GMT</pubDate>
<dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Ana</dc:creator><guid>g1</guid></item>
<item><title>No link</title></item></channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>At</title>
<link rel="alternate" href="https://ex.com/at"/><id>urn:1</id><updated>2026-11-13T10:00:00Z</updated>
<author><name>Bo</name></author><summary>S</summary></entry></feed>"""


def test_parse_rss_and_atom():
    (a,) = parse_feed(RSS)  # entry without link skipped (warned), not fatal
    assert a.title == "Hello" and a.author == "Ana" and a.summary == "Body bold"
    assert a.canonical_url == "https://ex.com/a?id=2" and a.url.startswith("https://ex.com/a/")
    assert a.published_at == datetime(2026, 11, 13, 9, tzinfo=timezone.utc) and a.source == "rss"
    (b,) = parse_feed(ATOM)
    assert b.author == "Bo" and b.published_at.tzinfo is not None and b.url == "https://ex.com/at"


@pytest.mark.parametrize("body", [b"<rss><channel><item>", b"not xml", b"<html/>",
                                  b"<rss><channel><item><title>x</title></item></channel></rss>"])
def test_malformed_feed_is_typed_error(body):
    with pytest.raises(FeedParseError):
        parse_feed(body)


def test_xml_entity_bomb_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><rss><channel/></rss>'
    with pytest.raises(FeedParseError):
        parse_feed(bomb)


def test_canonicalize_url():
    assert canonicalize_url("HTTPS://Ex.com/p/?b=2&a=1&utm_x=1&fbclid=z#f") == "https://ex.com/p?a=1&b=2"


def _rss(handler):
    return RealRssSource(transport=httpx.MockTransport(handler))


def test_rss_conditional_get_roundtrip():
    seen = []

    def handler(req):
        seen.append(req)
        assert req.headers["user-agent"] == USER_AGENT
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=ATOM, headers={"etag": '"v1"', "last-modified": "Fri, 13 Nov 2026 10:00:00 GMT"})
    src = _rss(handler)
    first = src.fetch("https://ex.com/feed")
    assert len(first.items) == 1 and first.validators.etag == '"v1"' and not first.not_modified
    second = src.fetch("https://ex.com/feed", validators=first.validators)
    assert second.not_modified and second.items == [] and second.validators == first.validators
    assert seen[1].headers["if-modified-since"] == "Fri, 13 Nov 2026 10:00:00 GMT"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost/x", "http://127.0.0.1/x",
                                 "http://10.0.0.5/x", "ftp://ex.com/x", "http://metadata.internal/x"])
def test_rss_refuses_non_public_urls(url):
    def boom(req):
        raise AssertionError("must not call out")
    with pytest.raises(FeedFetchError):
        _rss(boom).fetch(url)


def test_429_retry_after_then_ok_and_retry_later():
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(429, headers={"retry-after": "3"}) if n["c"] == 1 else httpx.Response(200, content=ATOM)
    assert len(_rss(handler).fetch("https://ex.com/f").items) == 1 and n["c"] == 2

    def long(req):
        return httpx.Response(429, headers={"retry-after": "99999"})
    with pytest.raises(RetryLater):
        _rss(long).fetch("https://ex2.com/f")


def test_persistent_429_surfaces_rate_limited():
    with pytest.raises(FeedRateLimited):
        _rss(lambda r: httpx.Response(429)).fetch("https://ex3.com/f")


def test_non_200_oversize_and_transport_errors_typed():
    with pytest.raises(FeedFetchError, match="500") as e:
        _rss(lambda r: httpx.Response(500, text="secret-body")).fetch("https://ex4.com/f")
    assert "secret-body" not in str(e.value)

    def conn(req):
        raise httpx.ConnectError("x")
    with pytest.raises(FeedFetchError):
        _rss(conn).fetch("https://ex5.com/f")
    with pytest.raises(FeedFetchError, match="size"):
        _rss(lambda r: httpx.Response(200, content=b"x" * (5 * 1024 * 1024 + 1))).fetch("https://ex6.com/f")


# -- hacker news ---------------------------------------------------------------
def test_hackernews_maps_and_skips_removed():
    def handler(req):
        p = req.url.path
        if p.endswith("topstories.json"):
            return httpx.Response(200, json=[1, 2, 3])
        if p.endswith("/1.json"):
            return httpx.Response(200, json={"id": 1, "type": "story", "title": "T1", "url": "https://x.dev/p?utm_a=1",
                                             "by": "u", "time": 1794000000, "score": 10, "descendants": 4})
        if p.endswith("/2.json"):
            return httpx.Response(200, content=b"null")
        return httpx.Response(200, json={"id": 3, "title": "Ask HN: x", "by": "v", "time": 1794000100, "text": "q"})
    items = RealHackerNewsSource(transport=httpx.MockTransport(handler)).fetch("top", limit=3)
    assert [i.title for i in items] == ["T1", "Ask HN: x"]
    assert items[0].canonical_url == "https://x.dev/p" and items[0].raw["comments"] == 4
    assert items[1].url == "https://news.ycombinator.com/item?id=3" and items[0].published_at.tzinfo is not None


def test_hackernews_bad_shapes_typed():
    src = RealHackerNewsSource(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"not": "list"})))
    with pytest.raises(FeedParseError):
        src.fetch()
    with pytest.raises(ValueError):
        src.fetch("bogus")


# -- github --------------------------------------------------------------------
def test_github_releases_and_trending():
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.path.endswith("/releases"):
            return httpx.Response(200, json=[
                {"html_url": "https://github.com/o/r/releases/tag/v1", "tag_name": "v1", "name": "One",
                 "body": "notes", "author": {"login": "bot"}, "published_at": "2026-11-12T10:00:00Z", "prerelease": False},
                {"html_url": "https://github.com/o/r/releases/tag/v2", "tag_name": "v2", "draft": True}])
        return httpx.Response(200, json={"items": [
            {"html_url": "https://github.com/a/b", "full_name": "a/b", "description": "d", "owner": {"login": "a"},
             "created_at": "2026-11-12T00:00:00Z", "stargazers_count": 900, "language": "Python"}]})
    src = RealGithubSource(token="ghp_SECRET", transport=httpx.MockTransport(handler),
                           now=lambda: datetime(2026, 11, 13, tzinfo=timezone.utc))
    (rel,) = src.releases("o/r")
    assert rel.title == "o/r One" and rel.raw["tag"] == "v1" and rel.source == "github_release"
    (tr,) = src.trending(since="weekly", language="python")
    assert tr.title == "a/b" and tr.raw["stars"] == 900 and tr.raw["method"] == "search_created_window"
    assert seen[1].url.params["q"] == "created:>2026-11-06 language:python"
    assert seen[0].headers["authorization"] == "Bearer ghp_SECRET" and "ghp_SECRET" not in str(seen[0].url)


def test_github_validation_and_primary_ratelimit():
    src = RealGithubSource(transport=httpx.MockTransport(lambda r: httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "retry-after": "99999"})))
    with pytest.raises(ValueError):
        src.releases("not a repo")
    with pytest.raises(ValueError):
        src.trending(since="hourly")
    with pytest.raises(RetryLater):  # quota exhausted for hours: reschedule, never spin
        src.releases("o/r")


# -- arxiv ---------------------------------------------------------------------
ARXIV = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2611.00001v1</id>
<published>2026-11-12T18:00:00Z</published><title>A
 Paper</title><summary> Abstract
 text </summary><author><name>X</name></author><author><name>Y</name></author>
<link href="http://arxiv.org/abs/2611.00001v1" rel="alternate" type="text/html"/><category term="cs.LG"/></entry></feed>"""


def test_arxiv_search_maps_and_params():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, content=ARXIV)
    (it,) = RealArxivSource(transport=httpx.MockTransport(handler)).search("cat:cs.LG", max_results=5)
    assert it.title == "A Paper" and it.summary == "Abstract text" and it.author == "X, Y"
    assert it.raw["categories"] == ["cs.LG"] and it.published_at.year == 2026
    assert seen[0].url.params["max_results"] == "5" and seen[0].url.params["sortBy"] == "submittedDate"


def test_arxiv_malformed_and_validation():
    src = RealArxivSource(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<feed")))
    with pytest.raises(FeedParseError):
        src.search("x")
    with pytest.raises(ValueError):
        src.search("   ")


# -- limiter wiring + fakes ------------------------------------------------------
def test_each_source_has_its_own_bucket_in_the_shared_limiter():
    _rss(lambda r: httpx.Response(200, content=ATOM)).fetch("https://bucket.example/f")
    RealArxivSource(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=ARXIV))).search("q")
    RealHackerNewsSource(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))).fetch()
    RealGithubSource(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))).releases("o/r")
    used = set(limiter._buckets)
    assert {"feeds:rss:bucket.example", "feeds:arxiv", "feeds:hackernews", "feeds:github"} <= used
    assert limiter.config("feeds:arxiv").rate_per_sec == pytest.approx(1 / 3)


def _item(url="https://ex.com/1"):
    return FeedItem(source="rss", url=url, canonical_url=url, title="t")


def test_fake_parity_with_real_validation_and_shapes():
    rss = FakeRssSource({"https://ex.com/f": [_item(), _item("https://ex.com/2")]})
    first = rss.fetch("https://ex.com/f", max_items=1)
    assert len(first.items) == 1
    again = rss.fetch("https://ex.com/f", validators=first.validators)
    assert again.not_modified and again.items == []
    with pytest.raises(ValueError):
        rss.fetch("file:///x")
    hn = FakeHackerNewsSource({"top": [_item()]})
    assert len(hn.fetch("top")) == 1
    with pytest.raises(ValueError):
        hn.fetch("bogus")
    gh = FakeGithubSource({"o/r": [_item()], "trending": [_item()]})
    assert gh.releases("o/r") and gh.trending(since="daily", language="go")
    with pytest.raises(ValueError):
        gh.releases("bad repo")
    ax = FakeArxivSource({"q": [_item()]})
    assert ax.search("q") and ax.calls[0][0] == "arxiv"
    with pytest.raises(FeedRateLimited):
        FakeArxivSource({}, raises=FeedRateLimited()).search("q")


def test_factories():
    assert isinstance(get_rss_source(real=False), FakeRssSource)
    assert isinstance(get_rss_source(), RealRssSource)
    assert isinstance(get_hackernews_source(real=False), FakeHackerNewsSource)
    assert isinstance(get_github_source(token="t"), RealGithubSource)
    assert isinstance(get_arxiv_source(real=False), FakeArxivSource)
    assert FetchValidators().etag is None
