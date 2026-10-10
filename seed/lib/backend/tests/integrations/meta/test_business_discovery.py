"""Business Discovery -- Protocol + Fake + Real (Facebook-Login connection)."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from noctusai_lib.integrations.meta import (
    BUSINESS_DISCOVERY_MEDIA_FIELDS,
    BusinessDiscoveryMedia,
    BusinessDiscoveryNotFound,
    BusinessDiscoveryPage,
    FakeMetaAdapter,
    MetaGraphError,
)
from noctusai_lib.integrations.meta.mappers import (
    business_discovery_fields_param,
    business_discovery_page_from_body,
)
from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter

FIXTURE = Path(__file__).parents[2] / "fixtures" / "meta" / "business_discovery_page.json"


def _body() -> dict:
    return json.loads(FIXTURE.read_text())


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


def _err(code, message="x", subcode=None, status=400):
    return _Resp({"error": {"message": message, "code": code, "error_subcode": subcode,
                            "type": "OAuthException", "fbtrace_id": "T"}}, status)


def _real() -> MetaOAuthAdapter:
    return MetaOAuthAdapter(system_user_token="TOK")


# ─── mapper / fixture ─────────────────────────────────────────────────────


class TestMapper:
    def test_fixture_maps_profile_media_and_cursor(self):
        page = business_discovery_page_from_body(_body(), requested_username="marca_exemplo")
        assert page.username == "marca_exemplo"
        assert page.ig_user_id == "17841400000000001"
        assert page.followers_count == 12345
        assert [m.id for m in page.media] == ["17900000000000011", "17900000000000012"]
        assert page.next_cursor == "QVFIUmFmdGVy"

    def test_views_are_never_served(self):
        page = business_discovery_page_from_body(_body(), requested_username="marca_exemplo")
        assert all(m.views is None for m in page.media)
        raw_keys = {k for m in _body()["business_discovery"]["media"]["data"] for k in m}
        assert not raw_keys & {"views", "play_count", "video_views", "plays", "reach", "impressions"}

    def test_hidden_like_count_is_none_not_zero(self):
        page = business_discovery_page_from_body(_body(), requested_username="marca_exemplo")
        assert page.media[0].like_count == 1500
        assert page.media[1].like_count is None
        assert page.media[1].comments_count == 3

    def test_last_page_has_no_cursor(self):
        body = _body()
        del body["business_discovery"]["media"]["paging"]["next"]
        page = business_discovery_page_from_body(body, requested_username="marca_exemplo")
        assert page.next_cursor is None

    def test_missing_business_discovery_object_is_an_error(self):
        with pytest.raises(ValueError):
            business_discovery_page_from_body({"id": "1"}, requested_username="x")


class TestFieldsParam:
    def test_builds_expression(self):
        p = business_discovery_fields_param("@marca.x", ["id", "like_count"], after="ABC", limit=10)
        assert p.startswith("business_discovery.username(marca.x){")
        assert "media.limit(10).after(ABC){id,like_count}" in p

    @pytest.mark.parametrize("bad", ["a b", "x)", "x{y", "../x", "", "a" * 31, "x,y"])
    def test_rejects_hostile_handle(self, bad):
        with pytest.raises(ValueError):
            business_discovery_fields_param(bad, ["id"])

    @pytest.mark.parametrize("bad", [["id,caption"], ["id}"], [], ["Id"], ["a{b}"]])
    def test_rejects_hostile_fields(self, bad):
        with pytest.raises(ValueError):
            business_discovery_fields_param("ok", bad)

    def test_rejects_hostile_cursor_and_limit(self):
        with pytest.raises(ValueError):
            business_discovery_fields_param("ok", ["id"], after="x){evil")
        with pytest.raises(ValueError):
            business_discovery_fields_param("ok", ["id"], limit=0)
        with pytest.raises(ValueError):
            business_discovery_fields_param("ok", ["id"], limit=101)


# ─── Real (network boundary patched, as the rest of the meta suite does) ───


class TestReal:
    def test_request_shape_and_result(self):
        seen = {}

        def _get(url, **kw):
            seen["url"], seen["params"] = url, kw["params"]
            return _Resp(_body())

        with patch.object(httpx, "get", side_effect=_get):
            page = _real().get_business_discovery(
                "17841400000000099", "@marca_exemplo",
                fields=BUSINESS_DISCOVERY_MEDIA_FIELDS, after="CUR",
            )
        assert "graph.facebook.com" in seen["url"] and seen["url"].endswith("/17841400000000099")
        assert seen["params"]["access_token"] == "TOK"
        assert "business_discovery.username(marca_exemplo)" in seen["params"]["fields"]
        assert "media.limit(25).after(CUR)" in seen["params"]["fields"]
        assert isinstance(page, BusinessDiscoveryPage)
        assert page.next_cursor == "QVFIUmFmdGVy"

    @pytest.mark.parametrize("code", [100, 110])
    def test_unknown_handle_maps_to_not_found(self, code):
        with patch.object(httpx, "get", return_value=_err(code, "Invalid user id")):
            with pytest.raises(BusinessDiscoveryNotFound) as ei:
                _real().get_business_discovery("1", "ghost", fields=["id"])
        assert isinstance(ei.value, MetaGraphError) and ei.value.code == code

    @pytest.mark.parametrize("code", [4, 17, 32, 613])
    def test_rate_limit_is_mapped_and_not_not_found(self, code):
        with patch.object(httpx, "get", return_value=_err(code, "slow down", status=429)):
            with pytest.raises(MetaGraphError) as ei:
                _real().get_business_discovery("1", "ok", fields=["id"])
        assert ei.value.is_rate_limited and not isinstance(ei.value, BusinessDiscoveryNotFound)

    @pytest.mark.parametrize("code,attr", [(190, "is_auth_error"), (10, "is_permission"), (200, "is_permission")])
    def test_auth_and_permission_pass_through(self, code, attr):
        with patch.object(httpx, "get", return_value=_err(code, "no")):
            with pytest.raises(MetaGraphError) as ei:
                _real().get_business_discovery("1", "ok", fields=["id"])
        assert getattr(ei.value, attr) and not isinstance(ei.value, BusinessDiscoveryNotFound)

    def test_200_without_business_discovery_is_an_error_not_an_empty_page(self):
        with patch.object(httpx, "get", return_value=_Resp({"id": "1"})):
            with pytest.raises(MetaGraphError):
                _real().get_business_discovery("1", "ok", fields=["id"])

    def test_bad_handle_never_reaches_the_network(self):
        with patch.object(httpx, "get") as g:
            with pytest.raises(ValueError):
                _real().get_business_discovery("1", "x){evil", fields=["id"])
        g.assert_not_called()


# ─── Fake ─────────────────────────────────────────────────────────────────


def _seeded(n_media=5) -> FakeMetaAdapter:
    base = business_discovery_page_from_body(_body(), requested_username="marca_exemplo")
    media = [BusinessDiscoveryMedia(id=str(i), like_count=i) for i in range(n_media)]
    return FakeMetaAdapter().seed(business_discovery={"Marca_Exemplo": replace(base, media=media)})


class TestFake:
    def test_pages_by_cursor_until_exhausted(self):
        f = _seeded(5)
        p1 = f.get_business_discovery("me", "marca_exemplo", fields=["id"], limit=2)
        assert [m.id for m in p1.media] == ["0", "1"] and p1.next_cursor == "2"
        p2 = f.get_business_discovery("me", "@MARCA_EXEMPLO", fields=["id"], limit=2, after=p1.next_cursor)
        assert [m.id for m in p2.media] == ["2", "3"]
        p3 = f.get_business_discovery("me", "marca_exemplo", fields=["id"], limit=2, after=p2.next_cursor)
        assert [m.id for m in p3.media] == ["4"] and p3.next_cursor is None
        assert len(f.business_discovery_calls) == 3

    def test_unseeded_handle_is_not_found(self):
        with pytest.raises(BusinessDiscoveryNotFound):
            FakeMetaAdapter().get_business_discovery("me", "ghost", fields=["id"])

    def test_seeded_error_is_raised(self):
        f = FakeMetaAdapter().seed(
            business_discovery_errors={"slow": MetaGraphError("limit", code=613, http_status=429)}
        )
        with pytest.raises(MetaGraphError) as ei:
            f.get_business_discovery("me", "slow", fields=["id"])
        assert ei.value.is_rate_limited

    def test_fake_validates_inputs_like_real(self):
        with pytest.raises(ValueError):
            _seeded().get_business_discovery("me", "bad handle", fields=["id"])
        with pytest.raises(ValueError):
            _seeded().get_business_discovery("me", "marca_exemplo", fields=["id,x"])
