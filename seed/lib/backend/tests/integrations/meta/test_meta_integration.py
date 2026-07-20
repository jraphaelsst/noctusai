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
    Conversation,
    DirectMessage,
    FacebookComment,
    FacebookPage,
    FakeMetaAdapter,
    InstagramAccount,
    InstagramComment,
    MetaGraphError,
    OAuthMetaCredentials,
    PostInsights,
    TokenBundle,
    discover_app_permissions,
    exchange_code_for_token,
    exchange_code_for_token_bundle,
    exchange_for_long_lived,
    exchange_for_long_lived_bundle,
    get_meta_adapter,
    make_meta_router,
    parse_graph_datetime,
    resolve_oauth_scopes,
)
from noctusai_lib.integrations.meta.mappers import (
    conversation_from_body,
    direct_message_from_body,
    facebook_comment_from_body,
    ig_account_from_body,
    ig_media_from_body,
    instagram_comment_from_body,
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

    def test_instagram_comment_from_body(self):
        c = instagram_comment_from_body(
            {
                "id": "c1",
                "text": "nice post!",
                "username": "fan1",
                "timestamp": "2026-05-13T18:30:00+0000",
                "like_count": 3,
                "hidden": True,
                "parent_id": "c0",
            }
        )
        assert c.id == "c1"
        assert c.text == "nice post!"
        assert c.hidden is True
        assert c.parent_id == "c0"
        assert c.raw["username"] == "fan1"

    def test_instagram_comment_from_body_defaults(self):
        c = instagram_comment_from_body({"id": "c2"})
        assert c.text is None
        assert c.like_count == 0
        assert c.hidden is False
        assert c.parent_id is None

    def test_facebook_comment_from_body(self):
        c = facebook_comment_from_body(
            {
                "id": "fc1",
                "message": "great!",
                "from": {"id": "u1", "name": "User One"},
                "created_time": "2026-05-13T18:30:00+0000",
                "like_count": 7,
                "is_hidden": False,
                "parent": {"id": "fc0"},
            }
        )
        assert c.id == "fc1"
        assert c.from_id == "u1"
        assert c.from_name == "User One"
        assert c.parent_id == "fc0"
        assert c.like_count == 7

    def test_facebook_comment_from_body_missing_from_and_parent(self):
        c = facebook_comment_from_body({"id": "fc2", "message": "hi"})
        assert c.from_id is None
        assert c.from_name is None
        assert c.parent_id is None
        assert c.is_hidden is False

    def test_conversation_from_body_flattens_participants(self):
        conv = conversation_from_body(
            {
                "id": "conv1",
                "participants": {
                    "data": [{"id": "IG1"}, {"id": "USER1"}]
                },
                "updated_time": "2026-05-13T18:30:00+0000",
            }
        )
        assert conv.id == "conv1"
        assert conv.participant_ids == ["IG1", "USER1"]
        assert conv.updated_time is not None

    def test_conversation_from_body_no_participants_edge(self):
        conv = conversation_from_body({"id": "conv2"})
        assert conv.participant_ids == []

    def test_direct_message_from_body(self):
        msg = direct_message_from_body(
            {
                "id": "m1",
                "from": {"id": "USER1"},
                "to": {"data": [{"id": "IG1"}]},
                "message": "hey there",
                "created_time": "2026-05-13T18:30:00+0000",
            },
            conversation_id="conv1",
        )
        assert msg.id == "m1"
        assert msg.conversation_id == "conv1"
        assert msg.sender_id == "USER1"
        assert msg.recipient_id == "IG1"
        assert msg.text == "hey there"

    def test_direct_message_from_body_missing_from_to(self):
        msg = direct_message_from_body({"id": "m2", "message": "x"})
        assert msg.sender_id is None
        assert msg.recipient_id is None
        assert msg.conversation_id is None


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


# ─── TestOAuthExchangeBundle ──────────────────────────────────────────────


class TestOAuthExchangeBundle:
    """The `_bundle` variants preserve the full Graph token metadata
    (`expires_in` / `token_type`) the string-returning fns discard;
    the legacy string fns still return just the token (back-compat)."""

    def test_code_for_token_bundle_captures_metadata(self):
        # Short-lived code exchange MAY include token_type but commonly
        # omits expires_in — assert both are captured when present.
        body = {
            "access_token": "SHORT",
            "token_type": "bearer",
            "expires_in": 5184000,
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            bundle = exchange_code_for_token_bundle(
                code="c",
                app_id="a",
                app_secret="s",
                redirect_uri="http://cb",
            )
        assert isinstance(bundle, TokenBundle)
        assert bundle.access_token == "SHORT"
        assert bundle.expires_in == 5184000
        assert bundle.token_type == "bearer"

    def test_code_for_token_bundle_none_safe_when_metadata_absent(self):
        # Short-lived exchange omitting expires_in / token_type → None,
        # never a KeyError (only access_token is required).
        body = {"access_token": "SHORT"}
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            bundle = exchange_code_for_token_bundle(
                code="c",
                app_id="a",
                app_secret="s",
                redirect_uri="http://cb",
            )
        assert bundle.access_token == "SHORT"
        assert bundle.expires_in is None
        assert bundle.token_type is None

    def test_long_lived_bundle_captures_metadata(self):
        # The long-lived response (the realistic Graph shape) carries
        # token_type + a ~60d expires_in.
        body = {
            "access_token": "LONG60D",
            "token_type": "bearer",
            "expires_in": 5183944,
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            bundle = exchange_for_long_lived_bundle(
                short_token="SHORT", app_id="a", app_secret="s"
            )
        assert bundle == TokenBundle(
            access_token="LONG60D", expires_in=5183944, token_type="bearer"
        )

    def test_expires_in_coerced_to_int(self):
        # Graph returns expires_in as a number; if it ever arrives as a
        # numeric string the bundle still yields an int.
        body = {"access_token": "LONG60D", "expires_in": "5183944"}
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            bundle = exchange_for_long_lived_bundle(
                short_token="SHORT", app_id="a", app_secret="s"
            )
        assert bundle.expires_in == 5183944
        assert isinstance(bundle.expires_in, int)

    def test_bundle_propagates_graph_error(self):
        body = {"error": {"message": "bad code", "code": 100}}
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            with pytest.raises(MetaGraphError):
                exchange_code_for_token_bundle(
                    code="c", app_id="a", app_secret="s", redirect_uri="x"
                )

    def test_legacy_string_fns_still_return_just_token(self):
        # Back-compat: the string-returning fns delegate to the bundle
        # variants but unwrap to `.access_token` — metadata invisible.
        code_body = {
            "access_token": "SHORT",
            "token_type": "bearer",
            "expires_in": 7200,
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(code_body)):
            tok = exchange_code_for_token(
                code="c", app_id="a", app_secret="s", redirect_uri="http://cb"
            )
        assert tok == "SHORT"
        assert isinstance(tok, str)

        long_body = {
            "access_token": "LONG60D",
            "token_type": "bearer",
            "expires_in": 5183944,
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(long_body)):
            tok = exchange_for_long_lived(
                short_token="SHORT", app_id="a", app_secret="s"
            )
        assert tok == "LONG60D"
        assert isinstance(tok, str)


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

    def test_get_facebook_page_insights_seeded_and_unseeded(self):
        fake = FakeMetaAdapter().seed(
            page_insights={
                "P1": PostInsights(object_id="P1", metrics={"page_fans": 10})
            }
        )
        assert fake.get_facebook_page_insights("P1").metrics["page_fans"] == 10
        # Unseeded → empty, not an error; window/period/metrics args
        # accepted for Protocol parity but ignored (same posture as
        # get_instagram_account_insights).
        empty = fake.get_facebook_page_insights(
            "NOPE", metrics=["page_fans"], period="week", since=1, until=2
        )
        assert empty.object_id == "NOPE"
        assert empty.metrics == {}


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


# ─── TestMetaGraphErrorPermission ─────────────────────────────────────────


class TestMetaGraphErrorPermission:
    """The write/ads scope-gate honesty classifier."""

    def test_permission_codes_set_requires_app_review(self):
        for c in (10, 200):
            e = MetaGraphError("perm", code=c)
            assert e.is_permission is True
            assert e.requires_app_review is True
            # Distinct from the token-expired classifier.
            assert e.is_auth_error is False

    def test_non_permission_code_not_app_review(self):
        e = MetaGraphError("expired", code=190)
        assert e.is_permission is False
        assert e.requires_app_review is False
        assert e.is_auth_error is True

    def test_capability_code_3_is_distinct_from_permission_and_auth(self):
        # Code 3 = "Application does not have the capability to make this
        # API call" — a Meta-side SETUP gate (product not wired up), NOT a
        # scope-not-granted (10/200) and NOT a token expiry (190). Must be
        # its own classifier so consumers render a "needs setup" state
        # instead of a raw 502.
        e = MetaGraphError("no capability", code=3)
        assert e.is_capability_missing is True
        assert e.is_permission is False
        assert e.requires_app_review is False
        assert e.is_auth_error is False
        assert e.is_rate_limited is False

    def test_permission_codes_are_not_capability_missing(self):
        for c in (10, 200):
            assert MetaGraphError("perm", code=c).is_capability_missing is False


# ─── TestFakeWriteSurface ─────────────────────────────────────────────────


class TestFakeWriteSurface:
    """Deterministic in-memory write simulation — the 'scope approved'
    path that lets MCP/consumer tests exercise the real handler with
    no network."""

    def test_publish_facebook_post_records(self):
        fake = FakeMetaAdapter()
        p1 = fake.publish_facebook_post("P1", "hello")
        p2 = fake.publish_facebook_post("P1", "world", link="https://x.io")
        assert p1.id == "P1_1" and p2.id == "P1_2"
        assert p1.page_id == "P1"
        assert [p.message for p in fake.published_posts] == ["hello", "world"]
        assert p1.permalink_url and p1.permalink_url.endswith("P1_1")

    def test_publish_facebook_post_with_photo(self):
        fake = FakeMetaAdapter()
        p = fake.publish_facebook_post(
            "P9", "caption", photo_url="https://img/x.jpg"
        )
        assert p.message == "caption"
        assert fake.published_posts == [p]

    def test_publish_instagram_media_two_step_recorded(self):
        fake = FakeMetaAdapter()
        m = fake.publish_instagram_media("IG1", "https://img/a.jpg", "cap")
        assert m.id == "IG1_media_1"
        assert m.container_id == "IG1_container_1"
        assert m.caption == "cap"
        assert fake.published_media == [m]

    def test_publish_instagram_carousel_records(self):
        fake = FakeMetaAdapter()
        urls = [
            "https://img/a.jpg",
            "https://img/b.jpg",
            "https://img/c.jpg",
        ]
        m = fake.publish_instagram_carousel("IG1", urls, caption="three-slide")
        assert m.id == "IG1_carousel_1"
        assert m.container_id == "IG1_carousel_container_1"
        assert m.caption == "three-slide"
        assert fake.published_media == [m]

    def test_publish_instagram_carousel_rejects_empty_and_overlong(self):
        import pytest as _pt

        fake = FakeMetaAdapter()
        with _pt.raises(ValueError, match="at least one"):
            fake.publish_instagram_carousel("IG1", [], caption="x")
        with _pt.raises(ValueError, match="at most 10"):
            fake.publish_instagram_carousel(
                "IG1", [f"https://img/{i}.jpg" for i in range(11)]
            )

    def test_list_ad_campaigns_seeded_and_prefix_norm(self):
        from noctusai_lib.integrations.meta import AdCampaign

        fake = FakeMetaAdapter().seed(
            ad_campaigns_by_account={
                "act_123": [AdCampaign(id="c1", name="Camp1")]
            }
        )
        # Bare id is normalised to act_ before lookup.
        camps = fake.list_ad_campaigns("123")
        assert len(camps) == 1 and camps[0].name == "Camp1"
        assert fake.list_ad_campaigns("act_123")[0].id == "c1"

    def test_ad_insights_seeded_and_default(self):
        from noctusai_lib.integrations.meta import AdInsights

        fake = FakeMetaAdapter().seed(
            ad_insights={
                "c1": AdInsights(
                    object_id="c1", level="campaign", metrics={"spend": 5.0}
                )
            }
        )
        got = fake.ad_insights("c1", "campaign")
        assert got.metrics["spend"] == 5.0
        # Unseeded → deterministic empty, never an error.
        empty = fake.ad_insights("missing", "ad")
        assert empty.object_id == "missing" and empty.metrics == {}


# ─── TestFakeCommentsMessagesStories ──────────────────────────────────────


class TestFakeCommentsMessagesStories:
    """Deterministic in-memory simulation of the comments/DMs/Stories
    surface — the Fake never raises the App-Review gate."""

    def test_list_instagram_comments_seeded(self):
        fake = FakeMetaAdapter().seed(
            ig_comments_by_media={
                "m1": [InstagramComment(id="c1", text="hi")]
            }
        )
        assert [c.id for c in fake.list_instagram_comments("m1")] == ["c1"]
        assert fake.list_instagram_comments("missing") == []

    def test_create_instagram_comment_records(self):
        fake = FakeMetaAdapter()
        c1 = fake.create_instagram_comment("m1", "first!")
        c2 = fake.create_instagram_comment("m1", "second!")
        assert c1.id == "m1_comment_1" and c2.id == "m1_comment_2"
        assert c1.text == "first!" and c1.parent_id is None
        assert fake.created_instagram_comments == [c1, c2]

    def test_reply_instagram_comment_records(self):
        fake = FakeMetaAdapter()
        r1 = fake.reply_instagram_comment("c1", "thanks!")
        r2 = fake.reply_instagram_comment("c1", "again")
        assert r1.id == "c1_reply_1" and r2.id == "c1_reply_2"
        assert r1.parent_id == "c1" and r1.text == "thanks!"
        assert fake.replied_instagram_comments == [r1, r2]

    def test_hide_and_delete_instagram_comment_recorded(self):
        fake = FakeMetaAdapter()
        assert fake.hide_instagram_comment("c1") is None
        assert fake.hide_instagram_comment("c2", hide=False) is None
        assert fake.hidden_instagram_comments == [("c1", True), ("c2", False)]
        assert fake.delete_instagram_comment("c1") is None
        assert fake.deleted_instagram_comment_ids == ["c1"]

    def test_list_instagram_conversations_and_messages_seeded(self):
        fake = FakeMetaAdapter().seed(
            conversations_by_ig_user={
                "IG1": [Conversation(id="conv1", participant_ids=["IG1", "U1"])]
            },
            messages_by_conversation={
                "conv1": [DirectMessage(id="m1", text="hey")]
            },
        )
        convs = fake.list_instagram_conversations("IG1")
        assert len(convs) == 1 and convs[0].id == "conv1"
        msgs = fake.list_instagram_messages("conv1")
        assert len(msgs) == 1 and msgs[0].text == "hey"
        assert fake.list_instagram_conversations("nope") == []

    def test_send_instagram_message_records(self):
        fake = FakeMetaAdapter()
        msg = fake.send_instagram_message("IG1", "U1", "hello there")
        assert msg.id == "IG1_dm_1"
        assert msg.sender_id == "IG1"
        assert msg.recipient_id == "U1"
        assert msg.text == "hello there"
        assert fake.sent_instagram_messages == [msg]

    def test_publish_instagram_story_image_and_video(self):
        fake = FakeMetaAdapter()
        img = fake.publish_instagram_story("IG1", "https://img/a.jpg")
        vid = fake.publish_instagram_story(
            "IG1", "https://vid/a.mp4", is_video=True
        )
        assert "image" in img.id and "video" in vid.id
        assert img.ig_user_id == "IG1"
        assert fake.published_stories == [img, vid]

    def test_list_facebook_comments_seeded(self):
        fake = FakeMetaAdapter().seed(
            fb_comments_by_post={
                "p1": [FacebookComment(id="fc1", message="nice")]
            }
        )
        assert [c.id for c in fake.list_facebook_comments("p1")] == ["fc1"]
        assert fake.list_facebook_comments("missing") == []

    def test_create_facebook_comment_records(self):
        fake = FakeMetaAdapter()
        comment = fake.create_facebook_comment("p1", "great post!")
        assert comment.id == "p1_comment_1"
        assert comment.message == "great post!"
        assert comment.parent_id is None
        assert fake.created_facebook_comments == [comment]

    def test_reply_facebook_comment_records(self):
        fake = FakeMetaAdapter()
        reply = fake.reply_facebook_comment("fc1", "thanks!")
        assert reply.id == "fc1_reply_1"
        assert reply.parent_id == "fc1"
        assert fake.replied_facebook_comments == [reply]

    def test_hide_and_delete_facebook_comment_recorded(self):
        fake = FakeMetaAdapter()
        assert fake.hide_facebook_comment("fc1") is None
        assert fake.hidden_facebook_comments == [("fc1", True)]
        assert fake.delete_facebook_comment("fc1") is None
        assert fake.deleted_facebook_comment_ids == ["fc1"]


# ─── TestRealWriteSurface ─────────────────────────────────────────────────


class TestRealWriteSurface:
    """The live adapter write/ads paths — external Graph boundary
    mocked (httpx.get / httpx.post patched; no noctusai_lib code
    monkey-patched)."""

    def _pages_body(self):
        return {
            "data": [{"id": "P1", "name": "Page1", "access_token": "PT1"}],
            "paging": {},
        }

    def test_publish_facebook_post_feed(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "get", return_value=_FakeResponse(self._pages_body())
        ):
            a.list_facebook_pages()  # warm the page-token cache
        get_resps = [_FakeResponse({"permalink_url": "https://fb/P1_55"})]
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "P1_55"})
        ), patch.object(httpx, "get", side_effect=get_resps):
            out = a.publish_facebook_post("P1", "hello world")
        assert out.id == "P1_55"
        assert out.page_id == "P1"
        assert out.permalink_url == "https://fb/P1_55"

    def test_publish_facebook_post_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "get", return_value=_FakeResponse(self._pages_body())
        ):
            a.list_facebook_pages()
        perm_err = {
            "error": {
                "message": "(#200) Requires pages_manage_posts permission",
                "code": 200,
                "type": "OAuthException",
            }
        }
        with patch.object(
            httpx, "post", return_value=_FakeResponse(perm_err)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_facebook_post("P1", "blocked")
        assert exc.value.requires_app_review is True
        assert exc.value.is_permission is True

    def test_publish_instagram_media_two_step_flow(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        post_resps = [
            _FakeResponse({"id": "CONT1"}),  # /media -> container
            _FakeResponse({"id": "MED1"}),  # /media_publish -> media id
        ]
        get_resps = [_FakeResponse({"permalink": "https://ig/p/MED1"})]
        with patch.object(
            httpx, "post", side_effect=post_resps
        ), patch.object(httpx, "get", side_effect=get_resps):
            out = a.publish_instagram_media("IG1", "https://img/a.jpg", "cap")
        assert out.id == "MED1"
        assert out.container_id == "CONT1"
        assert out.permalink == "https://ig/p/MED1"

    def test_publish_instagram_media_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        perm_err = {
            "error": {
                "message": "(#10) instagram_content_publish not granted",
                "code": 10,
                "type": "OAuthException",
            }
        }
        with patch.object(
            httpx, "post", return_value=_FakeResponse(perm_err)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_instagram_media("IG1", "https://img/a.jpg")
        assert exc.value.requires_app_review is True

    def test_publish_instagram_carousel_n_plus_two_step_flow(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        # 3 children → 3 child-container creates + 1 parent-container + 1 publish
        post_resps = [
            _FakeResponse({"id": "CHILD1"}),
            _FakeResponse({"id": "CHILD2"}),
            _FakeResponse({"id": "CHILD3"}),
            _FakeResponse({"id": "PARENT"}),
            _FakeResponse({"id": "MEDIA"}),
        ]
        get_resps = [_FakeResponse({"permalink": "https://ig/p/MEDIA"})]
        with patch.object(
            httpx, "post", side_effect=post_resps
        ), patch.object(httpx, "get", side_effect=get_resps):
            out = a.publish_instagram_carousel(
                "IG1",
                ["https://img/a.jpg", "https://img/b.jpg", "https://img/c.jpg"],
                caption="three",
            )
        assert out.id == "MEDIA"
        assert out.container_id == "PARENT"
        assert out.permalink == "https://ig/p/MEDIA"

    def test_publish_instagram_carousel_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        perm_err = {
            "error": {
                "message": "(#10) instagram_content_publish not granted",
                "code": 10,
                "type": "OAuthException",
            }
        }
        with patch.object(
            httpx, "post", return_value=_FakeResponse(perm_err)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_instagram_carousel(
                    "IG1", ["https://img/a.jpg", "https://img/b.jpg"]
                )
        assert exc.value.requires_app_review is True

    def test_publish_instagram_carousel_validates_bounds(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with pytest.raises(ValueError, match="at least one"):
            a.publish_instagram_carousel("IG1", [])
        with pytest.raises(ValueError, match="at most 10"):
            a.publish_instagram_carousel(
                "IG1", [f"https://img/{i}.jpg" for i in range(11)]
            )

    def test_list_ad_campaigns_reads_and_normalises_prefix(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {"id": "c1", "name": "Camp1", "status": "ACTIVE"},
                {"id": "c2", "name": "Camp2", "status": "PAUSED"},
            ],
            "paging": {},
        }
        with patch.object(
            httpx, "get", return_value=_FakeResponse(body)
        ):
            camps = a.list_ad_campaigns("123")
        assert [c.id for c in camps] == ["c1", "c2"]
        assert camps[0].status == "ACTIVE"

    def test_ad_insights_flattens_numeric_fields(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {"impressions": "1000", "spend": "12.50", "campaign": "skip"}
            ]
        }
        with patch.object(
            httpx, "get", return_value=_FakeResponse(body)
        ):
            ins = a.ad_insights("c1", "campaign", date_preset="last_7d")
        assert ins.metrics["impressions"] == 1000.0
        assert ins.metrics["spend"] == 12.5
        # Non-numeric field skipped, raw kept whole.
        assert "campaign" not in ins.metrics
        assert ins.raw[0]["campaign"] == "skip"

    def test_ad_insights_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        perm_err = {
            "error": {
                "message": "(#200) ads_read permission required",
                "code": 200,
            }
        }
        with patch.object(
            httpx, "get", return_value=_FakeResponse(perm_err)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.ad_insights("c1", "campaign")
        assert exc.value.requires_app_review is True


# ─── TestRealCommentsMessagesStories ──────────────────────────────────────


class TestRealCommentsMessagesStories:
    """The live adapter's comments/DMs/Stories surface — external Graph
    boundary mocked (httpx.get/post/delete patched; no noctusai_lib
    code monkey-patched). One `*_scope_absent_raises_app_review` test
    per gated write, mirroring `TestRealWriteSurface`."""

    _PERM_ERR = {
        "error": {
            "message": "(#10) permission not granted",
            "code": 10,
            "type": "OAuthException",
        }
    }

    # ── IG comments ─────────────────────────────────────────────────

    def test_list_instagram_comments_reads(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {"id": "c1", "text": "nice!", "username": "fan1"},
                {"id": "c2", "text": "cool", "username": "fan2"},
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            comments = a.list_instagram_comments("m1")
        assert [c.id for c in comments] == ["c1", "c2"]
        assert comments[0].username == "fan1"

    def test_create_instagram_comment_creates_and_reads_back(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        detail = {"id": "C1", "text": "first!"}
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "C1"})
        ), patch.object(httpx, "get", return_value=_FakeResponse(detail)):
            out = a.create_instagram_comment("m1", "first!")
        assert out.id == "C1"
        assert out.text == "first!"
        assert out.parent_id is None

    def test_create_instagram_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.create_instagram_comment("m1", "blocked")
        assert exc.value.requires_app_review is True

    def test_reply_instagram_comment_creates_and_reads_back(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        detail = {"id": "REPLY1", "text": "thanks!", "parent_id": "c1"}
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "REPLY1"})
        ), patch.object(httpx, "get", return_value=_FakeResponse(detail)):
            out = a.reply_instagram_comment("c1", "thanks!")
        assert out.id == "REPLY1"
        assert out.text == "thanks!"

    def test_reply_instagram_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.reply_instagram_comment("c1", "blocked")
        assert exc.value.requires_app_review is True

    def test_hide_instagram_comment_posts_hide_field(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"success": True})
        ):
            assert a.hide_instagram_comment("c1") is None
            assert a.hide_instagram_comment("c1", hide=False) is None

    def test_hide_instagram_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.hide_instagram_comment("c1")
        assert exc.value.requires_app_review is True

    def test_delete_instagram_comment_calls_graph_delete(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "delete", return_value=_FakeResponse({"success": True})
        ):
            assert a.delete_instagram_comment("c1") is None

    def test_delete_instagram_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "delete", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.delete_instagram_comment("c1")
        assert exc.value.requires_app_review is True

    # ── IG Direct messages ──────────────────────────────────────────

    def test_list_instagram_conversations_reads(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {
                    "id": "conv1",
                    "participants": {"data": [{"id": "IG1"}, {"id": "U1"}]},
                }
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            convs = a.list_instagram_conversations("IG1")
        assert convs[0].id == "conv1"
        assert convs[0].participant_ids == ["IG1", "U1"]

    def test_list_instagram_messages_two_step_flow(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        list_body = {"data": [{"id": "m1"}, {"id": "m2"}], "paging": {}}
        detail1 = {
            "id": "m1",
            "from": {"id": "U1"},
            "to": {"data": [{"id": "IG1"}]},
            "message": "hi",
        }
        detail2 = {
            "id": "m2",
            "from": {"id": "IG1"},
            "to": {"data": [{"id": "U1"}]},
            "message": "yo",
        }
        get_resps = [
            _FakeResponse(list_body),
            _FakeResponse(detail1),
            _FakeResponse(detail2),
        ]
        with patch.object(httpx, "get", side_effect=get_resps):
            msgs = a.list_instagram_messages("conv1")
        assert [m.id for m in msgs] == ["m1", "m2"]
        assert msgs[0].sender_id == "U1"
        assert msgs[0].recipient_id == "IG1"
        assert msgs[0].conversation_id == "conv1"

    def test_send_instagram_message_creates(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"message_id": "MID1"})
        ):
            out = a.send_instagram_message("IG1", "U1", "hello there")
        assert out.id == "MID1"
        assert out.sender_id == "IG1"
        assert out.recipient_id == "U1"
        assert out.text == "hello there"

    def test_send_instagram_message_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.send_instagram_message("IG1", "U1", "blocked")
        assert exc.value.requires_app_review is True

    # ── IG Stories ───────────────────────────────────────────────────

    def test_publish_instagram_story_image_two_step_flow(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        post_resps = [
            _FakeResponse({"id": "CONT1"}),
            _FakeResponse({"id": "STORY1"}),
        ]
        with patch.object(httpx, "post", side_effect=post_resps):
            out = a.publish_instagram_story("IG1", "https://img/a.jpg")
        assert out.id == "STORY1"
        assert out.container_id == "CONT1"
        assert out.ig_user_id == "IG1"

    def test_publish_instagram_story_video_flag(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        post_resps = [
            _FakeResponse({"id": "CONT2"}),
            _FakeResponse({"id": "STORY2"}),
        ]
        with patch.object(httpx, "post", side_effect=post_resps) as mock_post:
            out = a.publish_instagram_story(
                "IG1", "https://vid/a.mp4", is_video=True
            )
        assert out.id == "STORY2"
        first_call_data = mock_post.call_args_list[0].kwargs["data"]
        assert first_call_data["video_url"] == "https://vid/a.mp4"
        assert first_call_data["media_type"] == "STORIES"

    def test_publish_instagram_story_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_instagram_story("IG1", "https://img/blocked.jpg")
        assert exc.value.requires_app_review is True

    # ── FB comment moderation ───────────────────────────────────────

    def test_list_facebook_comments_reads(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {
                    "id": "fc1",
                    "message": "great",
                    "from": {"id": "u1", "name": "User One"},
                }
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            comments = a.list_facebook_comments("p1")
        assert comments[0].id == "fc1"
        assert comments[0].from_name == "User One"

    def test_create_facebook_comment_creates_and_reads_back(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        detail = {"id": "FC1", "message": "great post!"}
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "FC1"})
        ), patch.object(httpx, "get", return_value=_FakeResponse(detail)):
            out = a.create_facebook_comment("p1", "great post!")
        assert out.id == "FC1"
        assert out.message == "great post!"
        assert out.parent_id is None

    def test_create_facebook_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.create_facebook_comment("p1", "blocked")
        assert exc.value.requires_app_review is True

    def test_reply_facebook_comment_creates_and_reads_back(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        detail = {"id": "FCREPLY1", "message": "thanks!", "parent": {"id": "fc1"}}
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "FCREPLY1"})
        ), patch.object(httpx, "get", return_value=_FakeResponse(detail)):
            out = a.reply_facebook_comment("fc1", "thanks!")
        assert out.id == "FCREPLY1"
        assert out.parent_id == "fc1"

    def test_reply_facebook_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.reply_facebook_comment("fc1", "blocked")
        assert exc.value.requires_app_review is True

    def test_hide_facebook_comment_posts_is_hidden_field(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"success": True})
        ):
            assert a.hide_facebook_comment("fc1") is None

    def test_hide_facebook_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.hide_facebook_comment("fc1")
        assert exc.value.requires_app_review is True

    def test_delete_facebook_comment_calls_graph_delete(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "delete", return_value=_FakeResponse({"success": True})
        ):
            assert a.delete_facebook_comment("fc1") is None

    def test_delete_facebook_comment_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "delete", return_value=_FakeResponse(self._PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.delete_facebook_comment("fc1")
        assert exc.value.requires_app_review is True


# ─── TestReadPathRegression ───────────────────────────────────────────────


class TestReadPathRegression:
    """Sentinel: the additive write/ads extension must NOT alter any
    pre-existing read-only behaviour. Re-exercises the read surface
    end-to-end through the (now extended) Fake + Real adapters."""

    def test_fake_read_surface_unchanged(self):
        fake = FakeMetaAdapter().seed(
            pages=[FacebookPage(id="P1", name="Page1")],
            posts_by_page={"P1": [post_from_body({"id": "x1"})]},
            ig_accounts=[InstagramAccount(id="IG1", username="acct")],
            post_insights={"x1": PostInsights(object_id="x1", metrics={"r": 1})},
            me={"id": "1", "name": "T"},
        )
        assert fake.list_facebook_pages()[0].name == "Page1"
        assert len(fake.list_facebook_posts("P1")) == 1
        assert fake.list_instagram_accounts()[0].username == "acct"
        assert fake.get_facebook_post_insights("x1").metrics["r"] == 1
        assert fake.status().adapter == "fake"
        # Write recorders start empty — no read-path side effects.
        assert fake.published_posts == []
        assert fake.published_media == []

    def test_real_read_surface_unchanged(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [{"id": "P1", "name": "Page1", "access_token": "PT1"}],
            "paging": {},
        }
        with patch.object(
            httpx, "get", return_value=_FakeResponse(body)
        ):
            pages = a.list_facebook_pages()
        assert pages[0].id == "P1"
        assert a._page_token_cache["P1"] == "PT1"

    def test_both_adapters_carry_extended_contract(self):
        # MetaAdapter is a non-runtime_checkable Protocol; assert the
        # read + write/ads surface structurally (every method present
        # and callable) on both concrete adapters.
        surface = (
            "status",
            "me",
            "list_facebook_pages",
            "get_page",
            "list_facebook_posts",
            "get_facebook_post_insights",
            "list_instagram_accounts",
            "list_instagram_media",
            "get_instagram_media_insights",
            "get_instagram_account_insights",
            "publish_facebook_post",
            "publish_instagram_media",
            "publish_instagram_carousel",
            "publish_instagram_reel",
            "publish_facebook_video",
            "list_ad_campaigns",
            "ad_insights",
            "list_instagram_comments",
            "reply_instagram_comment",
            "hide_instagram_comment",
            "delete_instagram_comment",
            "list_instagram_conversations",
            "list_instagram_messages",
            "send_instagram_message",
            "publish_instagram_story",
            "list_facebook_comments",
            "reply_facebook_comment",
            "hide_facebook_comment",
            "delete_facebook_comment",
        )
        for impl in (FakeMetaAdapter(), MetaOAuthAdapter(system_user_token="X")):
            for name in surface:
                assert callable(getattr(impl, name)), (
                    f"{type(impl).__name__} missing {name}"
                )


# ─── TestMediaInsights ────────────────────────────────────────────────────


class TestMediaInsights:
    """`get_instagram_media_insights` — the per-media call.

    Graph validates the metric list BEFORE serving any of it, so one
    retired name zeroes every metric on the item. The router degrades a
    failed per-media call to `insights: null` per item, which means a
    rotted name here fails SILENTLY (no toast, just an empty posts
    table) — hence pinning the requested list explicitly."""

    def test_real_requests_only_live_metric_names(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        captured = {}

        def _get(url, **kw):
            captured["url"] = url
            captured["params"] = kw.get("params")
            return _FakeResponse(
                {"data": [
                    {"name": "reach", "period": "lifetime",
                     "values": [{"value": 88}]},
                ]}
            )

        with patch.object(httpx, "get", side_effect=_get):
            ins = a.get_instagram_media_insights("M1")

        assert ins.object_id == "M1"
        assert ins.metrics == {"reach": 88}
        assert captured["url"].endswith("M1/insights")

        requested = captured["params"]["metric"].split(",")
        # `engagement` → `total_interactions` and `video_views` → `views`:
        # both retired names 400'd the whole call against a live token
        # (2026-07-16, Graph v21), nulling every post's metrics in prod.
        assert "engagement" not in requested
        assert "video_views" not in requested
        assert "total_interactions" in requested
        assert "views" in requested


# ─── TestAccountInsights ──────────────────────────────────────────────────


class TestAccountInsights:
    """`get_instagram_account_insights` — the account-level (IG User)
    insights read, distinct from the per-media call. Reuses the shared
    `insights_from_body` mapper (same Graph `/{id}/insights` shape)."""

    def test_fake_seeded_roundtrip(self):
        fake = FakeMetaAdapter().seed(
            account_insights={
                "IG1": PostInsights(
                    object_id="IG1",
                    metrics={"reach": 1200, "profile_views": 40,
                             "follower_count": 5},
                )
            }
        )
        ins = fake.get_instagram_account_insights("IG1")
        assert ins.object_id == "IG1"
        assert ins.metrics["reach"] == 1200
        assert ins.metrics["follower_count"] == 5

    def test_fake_unseeded_default_empty(self):
        fake = FakeMetaAdapter()
        ins = fake.get_instagram_account_insights("nope")
        assert ins.object_id == "nope"
        assert ins.metrics == {}

    def test_fake_ignores_window_args_for_parity(self):
        # The window/period/metric args exist for Protocol parity — the
        # Fake accepts them without error and serves the seeded data.
        fake = FakeMetaAdapter().seed(
            account_insights={"IG1": PostInsights(object_id="IG1",
                                                  metrics={"reach": 9})}
        )
        ins = fake.get_instagram_account_insights(
            "IG1", metrics=["reach"], period="week", since=1, until=2
        )
        assert ins.metrics["reach"] == 9

    def test_real_default_metrics_split_time_series_from_total_value(self):
        """The default trio is served by TWO calls, not one batched call.

        `profile_views` is total-value-only: batching it with the
        time-series metrics makes Graph reject the ENTIRE request
        (`(#100) The following metrics (profile_views) should be
        specified with parameter metric_type=total_value`), zeroing
        `reach` and `follower_count` too. That shipped to prod and 502'd
        the Meta overview — this test pins the split so it can't
        regress."""
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        calls = []

        def _get(url, **kw):
            params = kw.get("params")
            calls.append({"url": url, "params": params})
            if params.get("metric_type") == "total_value":
                # Total-value rows carry `total_value`, never `values`.
                return _FakeResponse(
                    {"data": [
                        {"name": "profile_views", "period": "day",
                         "total_value": {"value": 12}},
                    ]}
                )
            return _FakeResponse(
                {"data": [
                    {"name": "reach", "period": "day",
                     "values": [{"value": 300}]},
                    {"name": "follower_count", "period": "day",
                     "values": [{"value": 5}]},
                ]}
            )

        with patch.object(httpx, "get", side_effect=_get):
            ins = a.get_instagram_account_insights("IG1")

        # Both calls' rows merge into one flat map — the total-value row
        # included (reading it via `values` would silently yield 0).
        assert ins.object_id == "IG1"
        assert ins.metrics == {"reach": 300, "follower_count": 5,
                               "profile_views": 12}

        assert len(calls) == 2
        series, total = calls
        assert series["url"].endswith("IG1/insights")
        assert total["url"].endswith("IG1/insights")

        # Time-series call: no total-value metric rides along.
        assert series["params"]["metric"] == "reach,follower_count"
        assert series["params"]["period"] == "day"
        assert "metric_type" not in series["params"]
        # `impressions` deliberately absent (retired at account level in v22).
        assert "impressions" not in series["params"]["metric"]

        # Total-value call: carries ONLY the total-value metric.
        assert total["params"]["metric"] == "profile_views"
        assert total["params"]["metric_type"] == "total_value"

    def test_real_custom_metrics_and_window_passthrough(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        captured = {}

        def _get(url, **kw):
            captured["params"] = kw.get("params")
            return _FakeResponse({"data": []})

        with patch.object(httpx, "get", side_effect=_get):
            a.get_instagram_account_insights(
                "IG1", metrics=["reach"], period="days_28",
                since=1000, until=2000,
            )
        assert captured["params"]["metric"] == "reach"
        assert captured["params"]["period"] == "days_28"
        assert captured["params"]["since"] == 1000
        assert captured["params"]["until"] == 2000


# ─── TestFacebookPageInsights ─────────────────────────────────────────────


class TestFacebookPageInsights:
    """`get_facebook_page_insights` — Page-level insights, distinct from
    every other insights call above: it requests each metric SEPARATELY
    and drops (logs, never raises) any metric Graph rejects, because
    Meta has been retiring individual Page Insights metrics on a
    rolling basis and a single unsupported name 400s Graph's WHOLE
    batched call when metrics are comma-joined."""

    def _pages_body(self):
        return {
            "data": [{"id": "P1", "name": "Page1", "access_token": "PT1"}],
            "paging": {},
        }

    def test_real_drops_a_retired_metric_keeps_the_others(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        calls: list[dict] = []

        def _get(url, **kw):
            params = kw.get("params") or {}
            calls.append({"url": url, "params": params})
            if url.endswith("me/accounts"):
                return _FakeResponse(self._pages_body())
            metric = params.get("metric")
            if metric == "page_impressions_unique":
                # Simulate a retired/unsupported metric — Graph error
                # envelope on a 200 (the shape `_raise_for_graph_error`
                # parses).
                return _FakeResponse(
                    {
                        "error": {
                            "message": "(#100) metric[0] must be one of...",
                            "code": 100,
                        }
                    }
                )
            return _FakeResponse(
                {
                    "data": [
                        {
                            "name": metric,
                            "period": "day",
                            "values": [{"value": 42}],
                        }
                    ]
                }
            )

        with patch.object(httpx, "get", side_effect=_get):
            ins = a.get_facebook_page_insights(
                "P1", metrics=["page_impressions_unique", "page_fans"]
            )

        assert ins.object_id == "P1"
        # The retired metric dropped itself — never raised, never
        # failed the other metric.
        assert "page_impressions_unique" not in ins.metrics
        assert ins.metrics["page_fans"] == 42

    def test_real_default_metrics_requested_separately(self):
        from noctusai_lib.integrations.meta.mappers import PAGE_INSIGHT_METRICS

        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        requested_metrics: list[str] = []

        def _get(url, **kw):
            params = kw.get("params") or {}
            if url.endswith("me/accounts"):
                return _FakeResponse(self._pages_body())
            requested_metrics.append(params["metric"])
            return _FakeResponse(
                {"data": [{"name": params["metric"], "period": "day",
                           "values": [{"value": 1}]}]}
            )

        with patch.object(httpx, "get", side_effect=_get):
            a.get_facebook_page_insights("P1")

        # Every metric requested as its OWN call (never comma-joined).
        assert requested_metrics == list(PAGE_INSIGHT_METRICS)


# ─── TestPollMediaStatus ──────────────────────────────────────────────────


class TestPollMediaStatus:
    """The resumable-upload processing-status poll helper — the new
    contract shape video / Reel publish needs. External Graph boundary
    mocked (httpx.get patched); `sleep` injected so the loop runs with
    zero wall-clock wait."""

    def test_polls_until_finished(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        get_resps = [
            _FakeResponse({"status_code": "IN_PROGRESS"}),
            _FakeResponse({"status_code": "IN_PROGRESS"}),
            _FakeResponse({"status_code": "FINISHED", "status": "ready"}),
        ]
        sleeps: list = []
        with patch.object(httpx, "get", side_effect=get_resps):
            res = poll_media_status(
                "CONT1",
                access_token="TOK",
                poll_interval_seconds=0.01,
                sleep=lambda s: sleeps.append(s),
            )
        assert res.creation_id == "CONT1"
        assert res.status_code == "FINISHED"
        assert res.is_finished is True
        assert len(sleeps) == 2

    def test_finished_immediately_no_sleep(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        with patch.object(
            httpx, "get", return_value=_FakeResponse({"status_code": "FINISHED"})
        ):
            res = poll_media_status(
                "CONT1", access_token="TOK", sleep=lambda s: pytest.fail("slept")
            )
        assert res.is_finished is True

    def test_error_status_raises(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        with patch.object(
            httpx,
            "get",
            return_value=_FakeResponse(
                {"status_code": "ERROR", "status": "transcode failed"}
            ),
        ):
            with pytest.raises(MetaGraphError) as exc:
                poll_media_status("CONT1", access_token="TOK")
        assert "processing failed" in str(exc.value)

    def test_expired_status_raises(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        with patch.object(
            httpx, "get", return_value=_FakeResponse({"status_code": "EXPIRED"})
        ):
            with pytest.raises(MetaGraphError):
                poll_media_status("CONT1", access_token="TOK")

    def test_timeout_raises_typed(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        with patch.object(
            httpx, "get", return_value=_FakeResponse({"status_code": "IN_PROGRESS"})
        ):
            with pytest.raises(MetaGraphError) as exc:
                poll_media_status(
                    "CONT1",
                    access_token="TOK",
                    timeout_seconds=0.0,
                    sleep=lambda s: None,
                )
        assert "video_processing_timeout" in str(exc.value)

    def test_permission_error_not_retried(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        perm = {"error": {"message": "no scope", "code": 200}}
        with patch.object(httpx, "get", return_value=_FakeResponse(perm)):
            with pytest.raises(MetaGraphError) as exc:
                poll_media_status(
                    "CONT1", access_token="TOK", sleep=lambda s: None
                )
        assert exc.value.requires_app_review is True

    def test_transient_5xx_retried_then_succeeds(self):
        from noctusai_lib.integrations.meta._meta_api import poll_media_status

        get_resps = [
            _FakeResponse("<html>503</html>", status_code=503, is_text=True),
            _FakeResponse({"status_code": "FINISHED"}),
        ]
        with patch.object(httpx, "get", side_effect=get_resps):
            res = poll_media_status(
                "CONT1", access_token="TOK", sleep=lambda s: None
            )
        assert res.is_finished is True


# ─── TestVideoReelPublish ─────────────────────────────────────────────────


class TestVideoReelPublish:
    """Video / IG Reel publish — the asynchronous resumable-upload +
    processing-status-poll surface. Fake = instant-ready; Real = full
    3-step Graph flow with the boundary (`httpx.get` / `httpx.post`)
    mocked, `sleep` injected for the poll. The App-Review gate is honest
    on the Real path; the Fake is the 'scope approved' path."""

    def _pages_body(self):
        return {
            "data": [{"id": "P1", "name": "Page1", "access_token": "PT1"}],
            "paging": {},
        }

    def test_fake_publish_instagram_reel_records(self):
        fake = FakeMetaAdapter()
        m = fake.publish_instagram_reel("IG1", "https://cdn/r.mp4", "cap")
        assert m.id == "IG1_reel_1"
        assert m.container_id == "IG1_reel_container_1"
        assert m.caption == "cap"
        assert m.processing_duration_ms == 0
        assert fake.published_media == [m]

    def test_fake_publish_facebook_video_records(self):
        fake = FakeMetaAdapter()
        v = fake.publish_facebook_video("P1", "https://cdn/v.mp4", "desc")
        assert v.id == "P1_video_1"
        assert v.message == "desc"
        assert fake.published_posts == [v]

    def test_fake_publish_facebook_reel_distinct_id(self):
        fake = FakeMetaAdapter()
        r = fake.publish_facebook_video("P1", "https://cdn/v.mp4", as_reel=True)
        assert r.id == "P1_reel_1"
        assert "/reel/" in r.permalink_url

    def test_fake_video_methods_reject_empty_url(self):
        fake = FakeMetaAdapter()
        with pytest.raises(ValueError, match="non-empty video_url"):
            fake.publish_instagram_reel("IG1", "")
        with pytest.raises(ValueError, match="non-empty video_url"):
            fake.publish_facebook_video("P1", "")

    def test_real_publish_instagram_reel_happy_path(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        post_resps = [
            _FakeResponse({"id": "CONT1"}),
            _FakeResponse({"id": "MED1"}),
        ]
        get_resps = [
            _FakeResponse({"status_code": "IN_PROGRESS"}),
            _FakeResponse({"status_code": "FINISHED"}),
            _FakeResponse({"permalink": "https://ig/reel/MED1"}),
        ]
        with patch.object(
            httpx, "post", side_effect=post_resps
        ), patch.object(httpx, "get", side_effect=get_resps), patch(
            "noctusai_lib.integrations.meta._meta_api.time.sleep",
            lambda s: None,
        ):
            out = a.publish_instagram_reel("IG1", "https://cdn/r.mp4", "cap")
        assert out.id == "MED1"
        assert out.container_id == "CONT1"
        assert out.permalink == "https://ig/reel/MED1"
        assert out.processing_duration_ms is not None
        assert out.processing_duration_ms >= 0

    def test_real_publish_instagram_reel_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        perm_err = {
            "error": {
                "message": "(#10) instagram_content_publish not granted",
                "code": 10,
                "type": "OAuthException",
            }
        }
        with patch.object(httpx, "post", return_value=_FakeResponse(perm_err)):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_instagram_reel("IG1", "https://cdn/r.mp4")
        assert exc.value.requires_app_review is True

    def test_real_publish_instagram_reel_processing_error_raises(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "CONT1"})
        ), patch.object(
            httpx, "get", return_value=_FakeResponse({"status_code": "ERROR"})
        ), patch(
            "noctusai_lib.integrations.meta._meta_api.time.sleep",
            lambda s: None,
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_instagram_reel("IG1", "https://cdn/r.mp4")
        assert "processing failed" in str(exc.value)

    def test_real_publish_instagram_reel_validates_empty_url(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with pytest.raises(ValueError, match="non-empty video_url"):
            a.publish_instagram_reel("IG1", "")

    def test_real_publish_facebook_video_happy_path(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "get", return_value=_FakeResponse(self._pages_body())
        ):
            a.list_facebook_pages()
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "VID9"})
        ), patch.object(
            httpx,
            "get",
            return_value=_FakeResponse({"permalink_url": "https://fb/VID9"}),
        ):
            out = a.publish_facebook_video("P1", "https://cdn/v.mp4", "desc")
        assert out.id == "VID9"
        assert out.page_id == "P1"
        assert out.message == "desc"
        assert out.permalink_url == "https://fb/VID9"
        assert out.processing_duration_ms is None

    def test_real_publish_facebook_reel_async_finalize(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "get", return_value=_FakeResponse(self._pages_body())
        ):
            a.list_facebook_pages()
        post_resps = [
            _FakeResponse({"video_id": "RV1"}),
            _FakeResponse({"success": True}),
        ]
        get_resps = [
            _FakeResponse({"status_code": "FINISHED"}),
            _FakeResponse({"permalink_url": "https://fb/RV1"}),
        ]
        with patch.object(
            httpx, "post", side_effect=post_resps
        ), patch.object(httpx, "get", side_effect=get_resps), patch(
            "noctusai_lib.integrations.meta._meta_api.time.sleep",
            lambda s: None,
        ):
            out = a.publish_facebook_video(
                "P1", "https://cdn/v.mp4", "reel desc", as_reel=True
            )
        assert out.id == "RV1"
        assert out.permalink_url == "https://fb/RV1"
        assert out.processing_duration_ms is not None

    def test_real_publish_facebook_video_scope_absent_raises_app_review(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with patch.object(
            httpx, "get", return_value=_FakeResponse(self._pages_body())
        ):
            a.list_facebook_pages()
        perm_err = {
            "error": {
                "message": "(#200) Requires pages_manage_posts permission",
                "code": 200,
            }
        }
        with patch.object(httpx, "post", return_value=_FakeResponse(perm_err)):
            with pytest.raises(MetaGraphError) as exc:
                a.publish_facebook_video("P1", "https://cdn/v.mp4")
        assert exc.value.requires_app_review is True

    def test_real_publish_facebook_video_validates_empty_url(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        with pytest.raises(ValueError, match="non-empty video_url"):
            a.publish_facebook_video("P1", "")
