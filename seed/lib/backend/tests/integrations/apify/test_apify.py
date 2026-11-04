import json
import logging
from datetime import date

import httpx
import pytest

from noctusai_lib.integrations.apify import (
    ApifyNotConfigured, ApifyProfileNotFound, ApifyRateLimited, ApifyRunFailed,
    FakeInstagramScraper, RealInstagramScraper, get_instagram_scraper,
)
from noctusai_lib.integrations.apify.fake_adapter import FIXTURES_DIR

TOKEN = "apify_api_SECRET123"
PUB = json.loads((FIXTURES_DIR / "perfil.publico.json").read_text())
PRIV = json.loads((FIXTURES_DIR / "perfil.privado.json").read_text())


def _real(handler):
    return RealInstagramScraper(token=TOKEN, transport=httpx.MockTransport(handler))


def _resp(items, status=201, headers=None):
    return httpx.Response(status, json=items, headers=headers or {})


def test_mapping_all_fields_fake():
    s = FakeInstagramScraper.from_fixtures().scrape_profile("@perfil.publico", max_posts=10)
    p = s.profile
    assert (p.username, p.full_name, p.followers_count, p.follows_count, p.posts_count) == ("perfil.publico", "Perfil Público", 1200, 10, 50)
    assert p.is_business is True and p.verified is False and p.external_id == "111" and not p.is_private
    assert p.profile_pic_url.endswith("pic.jpg")
    reel, img, view_only, sidecar = s.posts
    assert reel.media_type == "VIDEO" and reel.product_type == "clips" and reel.views == 500  # play > view
    assert reel.duration_s == 20.5 and reel.video_url.endswith("v.mp4") and reel.timestamp.tzinfo is not None
    assert reel.shortcode == "AAA" and reel.permalink.endswith("/p/AAA/") and reel.owner_username == "perfil.publico"
    assert img.media_type == "IMAGE" and img.likes is None and img.comments == 0  # -1 hidden
    assert view_only.views == 90
    assert sidecar.media_type == "CAROUSEL_ALBUM" and sidecar.views is None  # reel without plays


def test_fake_private_and_unknown_and_newer_than():
    f = FakeInstagramScraper.from_fixtures()
    with pytest.raises(ApifyProfileNotFound) as e:
        f.scrape_profile("perfil.privado", max_posts=5)
    assert e.value.reason == "privado"
    with pytest.raises(ApifyProfileNotFound) as e:
        f.scrape_profile("nao.existe", max_posts=5)
    assert e.value.reason == "nao_encontrado"
    assert len(f.scrape_profile("perfil.publico", max_posts=5, newer_than=date(2026, 9, 15)).posts) == 2


def test_invalid_handle_rejected_before_call():
    calls = []
    r = _real(lambda req: calls.append(req) or _resp([]))
    with pytest.raises(ValueError):
        r.scrape_profile("bad handle!", max_posts=5)
    assert calls == []


def test_real_details_then_posts_fill_dedupes_and_token_in_header_only():
    seen = []

    def handler(req):
        seen.append(req)
        body = json.loads(req.content)
        if body["resultsType"] == "details":
            return _resp([PUB], headers={"x-apify-usage-total-usd": "0.0023", "x-apify-run-id": "r1"})
        extra = dict(PUB["latestPosts"][0])  # duplicate of p1
        extra2 = {**PUB["latestPosts"][1], "id": "p9", "shortCode": "ZZZ"}
        return _resp([extra, extra2], headers={"x-apify-usage-total-usd": "0.001"})

    s = _real(handler).scrape_profile("@perfil.publico", max_posts=10, newer_than=date(2026, 1, 1))
    assert len(seen) == 2
    assert {p.id for p in s.posts} == {"p1", "p2", "p3", "p4", "p9"}
    assert s.cost.results == 3 and str(s.cost.usd) == "0.0033"
    for req in seen:
        assert req.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(req.url)
    body = json.loads(seen[0].content)
    assert body["directUrls"] == ["https://www.instagram.com/perfil.publico/"]
    assert body["onlyPostsNewerThan"] == "2026-01-01" and body["addParentData"] is False


def test_real_no_second_call_when_enough_and_cap_200_and_usd_none():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return _resp([PUB])

    s = _real(handler).scrape_profile("perfil.publico", max_posts=2)
    assert len(seen) == 1 and s.cost.usd is None and len(s.posts) == 2
    seen.clear()
    _real(handler).scrape_profile("perfil.publico", max_posts=9999)
    assert seen[0]["resultsLimit"] == 200


def test_real_private_and_empty():
    with pytest.raises(ApifyProfileNotFound) as e:
        _real(lambda r: _resp([PRIV])).scrape_profile("perfil.privado", max_posts=5)
    assert e.value.reason == "privado"
    with pytest.raises(ApifyProfileNotFound):
        _real(lambda r: _resp([{"error": "no_items", "errorDescription": "x"}])).scrape_profile("x.y", max_posts=5)
    with pytest.raises(ApifyProfileNotFound):
        _real(lambda r: _resp([])).scrape_profile("x.y", max_posts=5)


def test_real_429_and_failures_do_not_leak_token(caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ApifyRateLimited) as e:
        _real(lambda r: httpx.Response(429, headers={"retry-after": "7"}, text=TOKEN)).scrape_profile("a.b", max_posts=5)
    assert e.value.retry_after_s == 7.0

    def boom(req):
        raise httpx.ReadTimeout("t " + TOKEN, request=req)

    cases = [boom, lambda r: httpx.Response(500, text=TOKEN), lambda r: httpx.Response(200, text="not json " + TOKEN),
             lambda r: _resp({"a": TOKEN}), lambda r: _resp([{**PUB, "latestPosts": [{"id": "x"}]}])]
    for h in cases:
        with pytest.raises(ApifyRunFailed) as ex:
            _real(h).scrape_profile("a.b", max_posts=5)
        assert TOKEN not in str(ex.value) and TOKEN not in repr(ex.value)
    assert TOKEN not in caplog.text


def test_factory_fake_or_refuse():
    with pytest.raises(ApifyNotConfigured):
        get_instagram_scraper(token=None)
    assert isinstance(get_instagram_scraper(token=None, allow_fake=True), FakeInstagramScraper)
    assert isinstance(get_instagram_scraper(token=None, real=False), FakeInstagramScraper)
    assert isinstance(get_instagram_scraper(token=TOKEN), RealInstagramScraper)
    with pytest.raises(ApifyNotConfigured):
        RealInstagramScraper(token="")
