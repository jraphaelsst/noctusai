"""Mocked test suite for `noctusai_lib.integrations.meta`.

Mirrors the originating workspace's ~31-test mocked suite shape:
mappers / error-envelope / OAuth token chain / scope auto-discovery /
System-User dual-auth / factory selection / Fake adapter.

External boundary only is mocked: `httpx.get` is patched (a real
external Graph endpoint — sanctioned per CLAUDE.md "external
integrations OK"). No noctusai_lib code is monkey-patched; the
adapter, mappers, factory and router run for real against canned
Graph response bodies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from noctusai_lib.integrations.meta import (
    FacebookPage,
    FakeMetaAdapter,
    InstagramAccount,
    MetaGraphError,
    OAuthMetaCredentials,
    PostInsights,
    discover_app_permissions,
    exchange_code_for_token,
    exchange_for_long_lived,
    get_meta_adapter,
    make_meta_router,
    parse_graph_datetime,
    resolve_oauth_scopes,
)
from noctusai_lib.integrations.meta.mappers import (
    ig_account_from_body,
    ig_media_from_body,
    insights_from_body,
    page_from_body,
    post_from_body,
)
from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter


# ─── Test transport helper ────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200, *, is_text=False):
        self._payload = payload
        self.status_code = status_code
        self._is_text = is_text

    def json(self):
        if self._is_text:
            raise ValueError("not json")
        return self._payload

    @property
    def text(self):
        return self._payload if self._is_text else str(self._payload)


def _router(adapter, **kw):
    return make_meta_router(get_adapter=lambda _org: adapter, **kw)


# ─── TestMappers ──────────────────────────────────────────────────────────


class TestMappers:
    def test_parse_graph_datetime_offset_no_colon(self):
        dt = parse_graph_datetime("2026-05-13T18:30:00+0000")
        assert dt == datetime(2026, 5, 13, 18, 30, tzinfo=timezone.utc)

    def test_parse_graph_datetime_z_suffix(self):
        dt = parse_graph_datetime("2026-05-13T18:30:00Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.hour == 18

    def test_parse_graph_datetime_negative_offset(self):
        dt = parse_graph_datetime("2026-05-13T18:30:00-0530")
        assert dt is not None
        assert dt.utcoffset().total_seconds() == -(5 * 3600 + 30 * 60)

    def test_parse_graph_datetime_none(self):
        assert parse_graph_datetime(None) is None
        assert parse_graph_datetime("") is None

    def test_parse_graph_datetime_garbage(self):
        assert parse_graph_datetime("not-a-date") is None

    def test_page_from_body(self):
        p = page_from_body(
            {
                "id": "123",
                "name": "One Consultoria",
                "category": "Real Estate",
                "access_token": "EAAPAGE",
                "fan_count": 146,
                "followers_count": 150,
                "tasks": ["MANAGE", "ANALYZE"],
            }
        )
        assert p.id == "123"
        assert p.name == "One Consultoria"
        assert p.access_token == "EAAPAGE"
        assert p.fan_count == 146
        assert p.tasks == ["MANAGE", "ANALYZE"]

    def test_post_from_body_summary_counts(self):
        post = post_from_body(
            {
                "id": "p1",
                "message": "hello",
                "created_time": "2026-05-13T10:00:00+0000",
                "likes": {"summary": {"total_count": 5000}, "data": []},
                "comments": {"summary": {"total_count": 12}},
                "shares": {"count": 3},
            }
        )
        assert post.likes == 5000
        assert post.comments == 12
        assert post.shares == 3
        assert post.created_time.year == 2026

    def test_post_from_body_missing_edges_default_zero(self):
        post = post_from_body({"id": "p2"})
        assert post.likes == 0
        assert post.comments == 0
        assert post.shares == 0

    def test_ig_account_from_body(self):
        acct = ig_account_from_body(
            {
                "id": "17841",
                "username": "one_consultoria",
                "followers_count": 9056,
                "media_count": 1413,
            },
            page_id="123",
        )
        assert acct.username == "one_consultoria"
        assert acct.followers_count == 9056
        assert acct.page_id == "123"

    def test_ig_media_from_body(self):
        m = ig_media_from_body(
            {
                "id": "m1",
                "caption": "post",
                "media_type": "IMAGE",
                "timestamp": "2026-05-10T09:00:00+0000",
                "like_count": 112,
                "comments_count": 25,
            }
        )
        assert m.media_type == "IMAGE"
        assert m.like_count == 112
        assert m.comments_count == 25

    def test_insights_from_body_flattens_values(self):
        ins = insights_from_body(
            "p1",
            {
                "data": [
                    {"name": "post_impressions", "values": [{"value": 1234}]},
                    {"name": "post_clicks", "values": [{"value": 56}]},
                ]
            },
        )
        assert ins.metrics["post_impressions"] == 1234
        assert ins.metrics["post_clicks"] == 56
        assert ins.object_id == "p1"

    def test_insights_from_body_dict_valued_metric_summed(self):
        ins = insights_from_body(
            "p1",
            {
                "data": [
                    {
                        "name": "post_reactions_by_type_total",
                        "values": [{"value": {"like": 10, "love": 5, "wow": 2}}],
                    }
                ]
            },
        )
        assert ins.metrics["post_reactions_by_type_total"] == 17


# ─── TestGraphErrorParsing ────────────────────────────────────────────────


class TestGraphErrorParsing:
    def test_error_envelope_on_200_raises(self):
        from noctusai_lib.integrations.meta import _meta_api

        body = {
            "error": {
                "message": "Invalid OAuth access token.",
                "type": "OAuthException",
                "code": 190,
                "fbtrace_id": "AnAtKzKqMpqAJqf",
            }
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body, 200)):
            with pytest.raises(MetaGraphError) as exc:
                _meta_api.graph_get("me", access_token="x")
        assert exc.value.code == 190
        assert exc.value.is_auth_error
        assert not exc.value.is_rate_limited
        assert exc.value.fbtrace_id == "AnAtKzKqMpqAJqf"

    def test_rate_limit_classification(self):
        err = MetaGraphError("limit", code=4)
        assert err.is_rate_limited
        assert not err.is_auth_error

    def test_auth_codes_classification(self):
        for c in (102, 190, 467):
            assert MetaGraphError("x", code=c).is_auth_error
        for c in (4, 17, 32, 613):
            assert MetaGraphError("x", code=c).is_rate_limited

    def test_html_503_fallback_raises(self):
        from noctusai_lib.integrations.meta import _meta_api

        with patch.object(
            httpx,
            "get",
            return_value=_FakeResponse("<html>503</html>", 503, is_text=True),
        ):
            with pytest.raises(MetaGraphError) as exc:
                _meta_api.graph_get("me", access_token="x")
        assert exc.value.http_status == 503


# ─── TestOAuthExchange ────────────────────────────────────────────────────


class TestOAuthExchange:
    def test_code_for_token(self):
        with patch.object(
            httpx, "get", return_value=_FakeResponse({"access_token": "SHORT"})
        ):
            tok = exchange_code_for_token(
                code="c",
                app_id="a",
                app_secret="s",
                redirect_uri="http://cb",
            )
        assert tok == "SHORT"

    def test_short_to_long_lived(self):
        with patch.object(
            httpx, "get", return_value=_FakeResponse({"access_token": "LONG60D"})
        ):
            tok = exchange_for_long_lived(
                short_token="SHORT", app_id="a", app_secret="s"
            )
        assert tok == "LONG60D"

    def test_exchange_propagates_graph_error(self):
        body = {"error": {"message": "bad code", "code": 100}}
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            with pytest.raises(MetaGraphError):
                exchange_code_for_token(
                    code="c", app_id="a", app_secret="s", redirect_uri="x"
                )


# ─── TestScopeDiscovery ───────────────────────────────────────────────────


class TestScopeDiscovery:
    def test_explicit_list_verbatim(self):
        out = resolve_oauth_scopes(configured="pages_show_list, instagram_basic")
        assert out == ["pages_show_list", "instagram_basic"]

    def test_auto_falls_back_to_kitchen_sink_when_no_app_creds(self):
        out = resolve_oauth_scopes(configured="auto")
        assert "pages_show_list" in out
        assert "instagram_basic" in out

    def test_empty_falls_back_to_kitchen_sink(self):
        out = resolve_oauth_scopes(configured="")
        assert "pages_read_engagement" in out

    def test_auto_uses_discovered_when_present(self):
        body = {
            "data": [
                {"permission": "pages_show_list", "status": "live"},
                {"permission": "instagram_basic", "status": "live"},
            ]
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            out = resolve_oauth_scopes(
                configured="auto", app_id="a", app_secret="s"
            )
        assert out == ["pages_show_list", "instagram_basic"]

    def test_discover_app_permissions_empty_returns_none(self):
        with patch.object(
            httpx, "get", return_value=_FakeResponse({"data": []})
        ):
            assert discover_app_permissions(app_id="a", app_secret="s") is None

    def test_discover_app_permissions_network_error_returns_none(self):
        with patch.object(
            httpx, "get", side_effect=httpx.ConnectError("down")
        ):
            assert discover_app_permissions(app_id="a", app_secret="s") is None


# ─── TestSystemUserAuth ───────────────────────────────────────────────────


class TestSystemUserAuth:
    def test_system_user_mode(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        assert a.auth_mode == "system_user"
        assert a._user_token() == "SYSTOK"

    def test_user_oauth_mode_via_resolver(self):
        class R:
            def get_credentials(self, org_id=None):
                return OAuthMetaCredentials(access_token="LONG60D")

        a = MetaOAuthAdapter(resolver=R(), org_id="org1")
        assert a.auth_mode == "user_oauth"
        assert a._user_token() == "LONG60D"

    def test_system_user_wins_over_resolver(self):
        class R:
            def get_credentials(self, org_id=None):
                return OAuthMetaCredentials(access_token="OAUTHTOK")

        a = MetaOAuthAdapter(system_user_token="SYSTOK", resolver=R())
        assert a.auth_mode == "system_user"
        assert a._user_token() == "SYSTOK"

    def test_no_credentials_raises_on_token(self):
        a = MetaOAuthAdapter()
        assert a.auth_mode == "none"
        with pytest.raises(MetaGraphError):
            a._user_token()

    def test_status_probes_me_in_system_user_mode(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        # /me, then /me/accounts (pages -> empty), IG via pages -> empty
        responses = [
            _FakeResponse({"id": "999", "name": "Sys User"}),
            _FakeResponse({"data": [], "paging": {}}),
            _FakeResponse({"data": [], "paging": {}}),
        ]
        with patch.object(httpx, "get", side_effect=responses):
            st = a.status()
        assert st.configured is True
        assert st.auth_mode == "system_user"
        assert st.user_name == "Sys User"
        assert st.consent_required is False

    def test_status_auth_error_flags_needs_reconnection(self):
        a = MetaOAuthAdapter(system_user_token="REVOKED")
        body = {"error": {"message": "revoked", "code": 190}}
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            st = a.status()
        assert st.error == "needs_reconnection"
        assert st.consent_required is True

    def test_list_facebook_pages_caches_page_tokens(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {"id": "P1", "name": "Page1", "access_token": "PT1"},
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            pages = a.list_facebook_pages()
        assert pages[0].id == "P1"
        assert a._page_token_cache["P1"] == "PT1"


# ─── TestFactory ──────────────────────────────────────────────────────────


class TestFactory:
    def test_system_user_token_selects_oauth_adapter(self):
        a = get_meta_adapter(system_user_token="SYSTOK")
        assert isinstance(a, MetaOAuthAdapter)
        assert a.auth_mode == "system_user"

    def test_resolver_selects_oauth_adapter(self):
        class R:
            def get_credentials(self, org_id=None):
                return OAuthMetaCredentials(access_token="LONG")

        a = get_meta_adapter(resolver=R(), org_id="o")
        assert isinstance(a, MetaOAuthAdapter)
        assert a.auth_mode == "user_oauth"

    def test_no_creds_falls_back_to_fake(self):
        a = get_meta_adapter()
        assert isinstance(a, FakeMetaAdapter)
        assert a.auth_mode == "none"


# ─── TestFakeAdapter ──────────────────────────────────────────────────────


class TestFakeAdapter:
    def test_seeded_roundtrip(self):
        fake = FakeMetaAdapter().seed(
            pages=[FacebookPage(id="P1", name="Page1")],
            posts_by_page={
                "P1": [
                    post_from_body({"id": "x1"}),
                    post_from_body({"id": "x2"}),
                ]
            },
            ig_accounts=[InstagramAccount(id="IG1", username="acct")],
            post_insights={"x1": PostInsights(object_id="x1", metrics={"r": 1})},
            me={"id": "1", "name": "Tester"},
        )
        assert fake.list_facebook_pages()[0].name == "Page1"
        assert len(fake.list_facebook_posts("P1")) == 2
        assert fake.list_instagram_accounts()[0].username == "acct"
        assert fake.get_facebook_post_insights("x1").metrics["r"] == 1
        st = fake.status()
        assert st.adapter == "fake"
        assert st.user_name == "Tester"
        assert st.pages_count == 1

    def test_limit_truncation(self):
        fake = FakeMetaAdapter().seed(
            posts_by_page={
                "P1": [post_from_body({"id": str(i)}) for i in range(10)]
            }
        )
        assert len(fake.list_facebook_posts("P1", limit=3)) == 3

    def test_unseeded_insights_default_empty(self):
        fake = FakeMetaAdapter()
        ins = fake.get_instagram_media_insights("nope")
        assert ins.object_id == "nope"
        assert ins.metrics == {}

    def test_me_returns_seeded_identity(self):
        fake = FakeMetaAdapter().seed(me={"id": "9", "name": "Z", "email": "z@x"})
        assert fake.me() == {"id": "9", "name": "Z", "email": "z@x"}

    def test_me_unseeded_empty(self):
        assert FakeMetaAdapter().me() == {}

    def test_get_page_found_and_missing(self):
        fake = FakeMetaAdapter().seed(
            pages=[FacebookPage(id="P1", name="Page1")]
        )
        got = fake.get_page("P1")
        assert got is not None and got.name == "Page1"
        assert fake.get_page("NOPE") is None


# ─── TestRouter ───────────────────────────────────────────────────────────


class TestRouter:
    def test_status_endpoint_shape(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        fake = FakeMetaAdapter().seed(me={"id": "1", "name": "T"})
        app = FastAPI()
        app.include_router(_router(fake))
        client = TestClient(app)
        resp = client.get("/api/meta/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adapter"] == "fake"
        assert data["auth_mode"] == "none"
        assert data["configured"] is False

    def test_scopes_endpoint_kitchen_sink_layer(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_router(FakeMetaAdapter()))
        client = TestClient(app)
        resp = client.get("/api/meta/scopes")
        assert resp.status_code == 200
        data = resp.json()
        assert "pages_show_list" in data["kitchen_sink_fallback"]
        assert "pages_show_list" in data["configured"]
