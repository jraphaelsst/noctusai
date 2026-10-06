"""Instagram-Login insights surface — Real (httpx boundary mocked) + Fake +
factory parity.

Only the external boundary is patched (``httpx.get`` — Meta's Graph host);
the adapter, parsers and metric catalogs run for real against canned Graph
bodies shaped per the Instagram API with Instagram Login reference:
https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights
https://developers.facebook.com/docs/instagram-platform/api-reference/instagram-user/insights
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
import pytest
from unittest.mock import patch

from noctusai_lib.integrations.meta import (
    IG_MEDIA_METRICS_BY_PRODUCT_TYPE,
    FakeInstagramLoginAdapter,
    IgMediaItem,
    IgProfile,
    InstagramLoginAdapter,
    InstagramLoginOAuthAdapter,
    MetaGraphError,
    effective_product_type,
    get_instagram_login_adapter,
)
from noctusai_lib.integrations.meta.instagram_insights import (
    metric_series_from_body,
    metric_values_from_body,
)


class _Resp:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    @property
    def text(self):  # pragma: no cover - parity with httpx.Response
        return str(self._payload)


def _err(code: int, msg: str = "boom") -> dict:
    return {"error": {"message": msg, "code": code}}


class _Router:
    """Route ``httpx.get(url, params=...)`` to canned bodies by a predicate
    over (path, params) — records every call."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kw):
        params = dict(kw.get("params") or {})
        path = urlparse(url).path
        self.calls.append((path, params))
        return _Resp(self.handler(path, params))


# ─── Pure parsers ───────────────────────────────────────────────────────
class TestParsers:
    def test_values_from_values_and_total_value_shapes(self):
        body = {"data": [
            {"name": "reach", "period": "lifetime", "values": [{"value": 120}]},
            {"name": "views", "total_value": {"value": 300}},
            {"name": "ig_reels_avg_watch_time", "values": [{"value": 5321}]},
            {"name": "profile_activity", "values": [{"value": {"bio_link": 2, "call": 1}}]},
        ]}
        assert metric_values_from_body(body) == {
            "reach": 120, "views": 300, "ig_reels_avg_watch_time": 5321, "profile_activity": 3,
        }

    def test_series_keys_on_end_time_date(self):
        body = {"data": [{"name": "reach", "values": [
            {"value": 10, "end_time": "2026-10-01T07:00:00+0000"},
            {"value": 12, "end_time": "2026-10-02T07:00:00+0000"},
        ]}]}
        assert metric_series_from_body(body) == {"reach": [("2026-10-01", 10), ("2026-10-02", 12)]}

    @pytest.mark.parametrize("mpt,mt,expected", [
        ("REELS", "VIDEO", "REELS"),
        ("FEED", "CAROUSEL_ALBUM", "FEED"),
        ("STORY", "IMAGE", "STORY"),
        ("AD", "IMAGE", "FEED"),
        (None, "VIDEO", "REELS"),
        (None, "IMAGE", "FEED"),
        (None, None, "FEED"),
    ])
    def test_effective_product_type(self, mpt, mt, expected):
        assert effective_product_type(mpt, mt) == expected

    def test_catalog_excludes_deprecated_impressions(self):
        for metrics in IG_MEDIA_METRICS_BY_PRODUCT_TYPE.values():
            assert "impressions" not in metrics
            assert "plays" not in metrics


# ─── Real adapter ───────────────────────────────────────────────────────
class TestRealProfile:
    def test_profile_fields_on_ig_host(self):
        router = _Router(lambda p, q: {
            "id": "APP1", "user_id": "1784", "username": "acme", "followers_count": 1500,
            "follows_count": 20, "media_count": 99, "biography": "bio", "website": "https://x",
        })
        with patch.object(httpx, "get", side_effect=router):
            prof = InstagramLoginOAuthAdapter("TOK").get_profile()
        assert prof.ig_user_id == "1784" and prof.followers_count == 1500 and prof.website == "https://x"
        path, params = router.calls[0]
        assert path == "/v21.0/me"
        assert "followers_count" in params["fields"] and "biography" in params["fields"]

    def test_rejected_optional_fields_fall_back_to_core(self):
        def handler(p, q):
            if "biography" in q["fields"]:
                return _err(100, "Tried accessing nonexisting field (biography)")
            return {"id": "APP1", "user_id": "1784", "username": "acme"}
        router = _Router(handler)
        with patch.object(httpx, "get", side_effect=router):
            prof = InstagramLoginOAuthAdapter("TOK").get_profile()
        assert prof.username == "acme" and prof.biography is None
        assert len(router.calls) == 2

    def test_auth_error_is_not_swallowed(self):
        with patch.object(httpx, "get", side_effect=_Router(lambda p, q: _err(190, "expired"))):
            with pytest.raises(MetaGraphError) as ei:
                InstagramLoginOAuthAdapter("TOK").get_profile()
        assert ei.value.is_auth_error


class TestRealMediaList:
    def test_cursor_paging(self):
        def handler(p, q):
            if q.get("after") == "C2":
                return {"data": [{"id": "3", "media_type": "IMAGE"}]}
            return {
                "data": [
                    {"id": "1", "media_type": "VIDEO", "media_product_type": "REELS",
                     "timestamp": "2026-10-05T12:00:00+0000", "like_count": 4, "comments_count": 1},
                    {"id": "2", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED"},
                ],
                "paging": {"cursors": {"after": "C2"}, "next": "https://graph.instagram.com/v21.0/me/media?after=C2"},
            }
        router = _Router(handler)
        a = InstagramLoginOAuthAdapter("TOK")
        with patch.object(httpx, "get", side_effect=router):
            p1 = a.list_media(limit=2)
            p2 = a.list_media(cursor=p1.next_cursor, limit=2)
        assert [m.id for m in p1.items] == ["1", "2"] and p1.next_cursor == "C2"
        assert p1.items[0].like_count == 4 and p1.items[0].timestamp.year == 2026
        assert p1.items[1].like_count is None  # hidden/absent → None, never 0
        assert [m.id for m in p2.items] == ["3"] and p2.next_cursor is None
        assert router.calls[0][0] == "/v21.0/me/media"
        assert "media_product_type" in router.calls[0][1]["fields"]

    def test_time_based_paging_cursor(self):
        def handler(p, q):
            if q.get("until") == "1700000000":
                return {"data": []}
            return {"data": [{"id": "1"}], "paging": {"next": "https://graph.instagram.com/v21.0/me/media?until=1700000000"}}
        a = InstagramLoginOAuthAdapter("TOK")
        with patch.object(httpx, "get", side_effect=_Router(handler)):
            p1 = a.list_media()
            assert p1.next_cursor == "until:1700000000"
            assert a.list_media(cursor=p1.next_cursor).items == []

    def test_product_type_field_rejected_is_left_null_and_pinned(self):
        def handler(p, q):
            if "media_product_type" in q["fields"]:
                return _err(100, "nonexisting field media_product_type")
            return {"data": [{"id": "1", "media_type": "VIDEO"}],
                    "paging": {"cursors": {"after": "X"}, "next": "n"}} if not q.get("after") else {"data": []}
        router = _Router(handler)
        a = InstagramLoginOAuthAdapter("TOK")
        with patch.object(httpx, "get", side_effect=router):
            p1 = a.list_media()
            a.list_media(cursor=p1.next_cursor)
        assert p1.items[0].media_product_type is None
        # page 1: full (rejected) + core; page 2: core only (pinned)
        assert len(router.calls) == 3

    def test_stories_default_product_type(self):
        router = _Router(lambda p, q: {"data": [{"id": "S1", "media_type": "IMAGE"}]})
        with patch.object(httpx, "get", side_effect=router):
            stories = InstagramLoginOAuthAdapter("TOK").list_stories()
        assert stories[0].media_product_type == "STORY"
        assert router.calls[0][0] == "/v21.0/me/stories"


class TestRealMediaInsights:
    def test_reels_metric_set_requested_in_one_call(self):
        def handler(p, q):
            return {"data": [{"name": m, "values": [{"value": i + 1}]}
                             for i, m in enumerate(q["metric"].split(","))]}
        router = _Router(handler)
        with patch.object(httpx, "get", side_effect=router):
            res = InstagramLoginOAuthAdapter("TOK").get_media_insights("M1", "REELS")
        assert router.calls[0][0] == "/v21.0/M1/insights"
        assert router.calls[0][1]["metric"].split(",") == list(IG_MEDIA_METRICS_BY_PRODUCT_TYPE["REELS"])
        assert res.unsupported == () and res.values["views"] == 1

    def test_unsupported_metric_degrades_to_none_per_metric(self):
        def handler(p, q):
            metrics = q["metric"].split(",")
            if "reposts" in metrics:
                return _err(100, "(#100) metric[reposts] is not supported")
            return {"data": [{"name": m, "values": [{"value": 7}]} for m in metrics]}
        router = _Router(handler)
        with patch.object(httpx, "get", side_effect=router):
            res = InstagramLoginOAuthAdapter("TOK").get_media_insights("M1", "FEED")
        assert res.values["reposts"] is None and "reposts" in res.unsupported
        assert "not supported" in res.errors["reposts"]
        assert res.values["reach"] == 7
        # 1 batch + one per metric
        assert len(router.calls) == 1 + len(IG_MEDIA_METRICS_BY_PRODUCT_TYPE["FEED"])

    def test_metric_absent_from_body_is_none_not_zero(self):
        with patch.object(httpx, "get", side_effect=_Router(lambda p, q: {"data": [{"name": "reach", "values": [{"value": 0}]}]})):
            res = InstagramLoginOAuthAdapter("TOK").get_media_insights("M1", "STORY")
        assert res.values["reach"] == 0  # a real zero stays zero
        assert res.values["views"] is None and "views" in res.unsupported

    def test_permission_error_raises(self):
        with patch.object(httpx, "get", side_effect=_Router(lambda p, q: _err(10, "Not enough viewers"))):
            with pytest.raises(MetaGraphError) as ei:
                InstagramLoginOAuthAdapter("TOK").get_media_insights("S1", "STORY")
        assert ei.value.is_permission


class TestRealUserInsights:
    def test_total_value(self):
        def handler(p, q):
            return {"data": [{"name": m, "total_value": {"value": 5}} for m in q["metric"].split(",") if m != "replies"]}
        router = _Router(handler)
        with patch.object(httpx, "get", side_effect=router):
            res = InstagramLoginOAuthAdapter("TOK").get_user_insights(
                "1784", ["reach", "views", "replies"], since=1, until=2)
        path, params = router.calls[0]
        assert path == "/v21.0/1784/insights"
        assert params["metric_type"] == "total_value" and params["period"] == "day"
        assert params["since"] == 1 and params["until"] == 2
        assert res.totals == {"reach": 5, "views": 5, "replies": None}
        assert res.unsupported == ("replies",)

    def test_time_series(self):
        body = {"data": [{"name": "reach", "values": [{"value": 3, "end_time": "2026-10-01T07:00:00+0000"}]}]}
        with patch.object(httpx, "get", side_effect=_Router(lambda p, q: body)):
            res = InstagramLoginOAuthAdapter("TOK").get_user_insights("1784", ["reach"], metric_type="time_series")
        assert res.series == {"reach": [("2026-10-01", 3)]} and res.unsupported == ()


# ─── Fake ───────────────────────────────────────────────────────────────
class TestFake:
    def _fake(self):
        media = [IgMediaItem(id=str(i), media_type="IMAGE", media_product_type="FEED") for i in range(5)]
        return FakeInstagramLoginAdapter().seed(
            profile=IgProfile(id="A", user_id="U", username="acme", followers_count=10),
            media=media,
            stories=[IgMediaItem(id="S", media_product_type="STORY")],
            media_insights={"0": {"reach": 9, "views": 20}},
            media_errors={"4": MetaGraphError("expired", code=190)},
            user_insights={"reach": 100},
        )

    def test_profile_and_paging(self):
        f = self._fake()
        assert f.get_profile().username == "acme"
        p1 = f.list_media(limit=2)
        p2 = f.list_media(cursor=p1.next_cursor, limit=2)
        p3 = f.list_media(cursor=p2.next_cursor, limit=2)
        assert [m.id for m in p1.items + p2.items + p3.items] == ["0", "1", "2", "3", "4"]
        assert p3.next_cursor is None
        assert f.list_stories()[0].id == "S"

    def test_unseeded_metrics_are_unsupported_none(self):
        res = self._fake().get_media_insights("0", "FEED")
        assert res.values["reach"] == 9 and res.values["saved"] is None
        assert "saved" in res.unsupported and "reach" not in res.unsupported

    def test_seeded_error_raises(self):
        with pytest.raises(MetaGraphError):
            self._fake().get_media_insights("4", "FEED")

    def test_user_insights(self):
        res = self._fake().get_user_insights("U", ["reach", "views"])
        assert res.totals == {"reach": 100, "views": None} and res.unsupported == ("views",)

    def test_default_profile_is_valid(self):
        prof = FakeInstagramLoginAdapter().get_profile()
        assert prof.ig_user_id == "FAKE_IG_USER" and prof.username == "fake_ig_user"


# ─── Factory + protocol parity ──────────────────────────────────────────
class TestFactoryParity:
    def test_token_returns_real(self):
        a = get_instagram_login_adapter("TOK", version="v23.0")
        assert isinstance(a, InstagramLoginOAuthAdapter) and a._version == "v23.0"

    def test_no_token_refuses_without_opt_in(self):
        with pytest.raises(ValueError):
            get_instagram_login_adapter(None)

    def test_no_token_with_opt_in_is_fake(self):
        assert isinstance(get_instagram_login_adapter(None, allow_fake=True), FakeInstagramLoginAdapter)

    @pytest.mark.parametrize("cls", [InstagramLoginOAuthAdapter, FakeInstagramLoginAdapter])
    def test_real_and_fake_implement_full_protocol(self, cls):
        members = [
            n for n in dir(InstagramLoginAdapter)
            if not n.startswith("_") and callable(getattr(InstagramLoginAdapter, n))
        ]
        assert {"get_profile", "get_user_insights", "list_media", "list_stories",
                "get_media_insights", "me", "send_instagram_message"} <= set(members)
        for name in members:
            assert callable(getattr(cls, name, None)), f"{cls.__name__} lacks {name}"
