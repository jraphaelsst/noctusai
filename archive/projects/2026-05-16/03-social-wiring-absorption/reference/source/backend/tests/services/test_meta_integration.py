"""Tests for the Meta (Facebook + Instagram) integration.

Mocked tests cover wire-shape correctness — body parsers, error
parsing, OAuth token-exchange call shape, factory resolution. They do
NOT hit live Graph API; end-to-end validation lives in the
SESSION-NOTES doc + the manual validation log, same posture as
``test_google_integrations.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from app.services.meta import (
    FacebookPage,
    FacebookPost,
    FakeMetaAdapter,
    InstagramAccount,
    InstagramMedia,
    PostInsights,
    get_meta_adapter,
)
from app.services.meta._meta_api import (
    META_KITCHEN_SINK_SCOPES,
    MetaGraphError,
    _raise_for_graph_error,
    app_access_token,
    discover_app_permissions,
    exchange_code_for_token,
    exchange_short_for_long_lived,
    resolve_oauth_scopes,
)
from app.services.meta.mappers import (
    ig_account_body_to_instagram_account,
    insight_body_to_post_insights,
    media_body_to_instagram_media,
    page_body_to_facebook_page,
    parse_graph_datetime,
    post_body_to_facebook_post,
)


# ─── Mappers ───────────────────────────────────────────────────────────
class TestMappers:
    def test_parse_graph_datetime_normalizes_z_offset(self):
        dt = parse_graph_datetime("2026-05-13T10:15:30+0000")
        assert dt is not None
        assert dt == datetime(2026, 5, 13, 10, 15, 30, tzinfo=timezone.utc)

    def test_parse_graph_datetime_accepts_full_offset(self):
        dt = parse_graph_datetime("2026-05-13T07:15:30-03:00")
        assert dt is not None
        assert dt.utcoffset().total_seconds() == -3 * 3600

    def test_parse_graph_datetime_returns_none_for_garbage(self):
        assert parse_graph_datetime("not a date") is None
        assert parse_graph_datetime(None) is None
        assert parse_graph_datetime(123) is None

    def test_page_body_maps_canonical_fields(self):
        body = {
            "id": "111",
            "name": "Imobiliaria One",
            "category": "Real Estate",
            "access_token": "PAGE-TOKEN",
            "fan_count": "1500",
            "followers_count": 1530,
            "link": "https://facebook.com/one",
            "tasks": ["MANAGE", "ANALYZE"],
        }
        page = page_body_to_facebook_page(body)
        assert isinstance(page, FacebookPage)
        assert page.page_id == "111"
        assert page.fan_count == 1500  # str → int coercion
        assert page.followers_count == 1530
        assert page.tasks == ["MANAGE", "ANALYZE"]
        assert page.access_token == "PAGE-TOKEN"

    def test_post_body_summarizes_likes_comments_shares(self):
        body = {
            "id": "111_222",
            "message": "Novo lancamento",
            "created_time": "2026-05-10T12:00:00+0000",
            "permalink_url": "https://facebook.com/111/posts/222",
            "full_picture": "https://scontent.../pic.jpg",
            "likes": {"summary": {"total_count": 42}},
            "comments": {"summary": {"total_count": 7}},
            "shares": {"count": 3},
            "attachments": {
                "data": [
                    {"title": "Vista da varanda", "type": "photo"},
                    {"type": "video_inline"},
                ]
            },
        }
        post = post_body_to_facebook_post(body, page_id="111")
        assert isinstance(post, FacebookPost)
        assert post.page_id == "111"
        assert post.likes_count == 42
        assert post.comments_count == 7
        assert post.shares_count == 3
        assert post.attachments_summary == ["Vista da varanda", "video_inline"]
        assert post.created_at is not None and post.created_at.year == 2026

    def test_ig_account_maps_canonical_fields_and_linked_page(self):
        body = {
            "id": "999",
            "username": "one.consultoria",
            "name": "One Consultoria",
            "profile_picture_url": "https://cdn/pic.jpg",
            "followers_count": 2300,
            "follows_count": 180,
            "media_count": 412,
            "biography": "Imoveis em SP",
            "website": "https://one.com.br",
        }
        account = ig_account_body_to_instagram_account(body, linked_page_id="111")
        assert isinstance(account, InstagramAccount)
        assert account.ig_user_id == "999"
        assert account.linked_page_id == "111"
        assert account.followers_count == 2300

    def test_media_body_maps_canonical_fields(self):
        body = {
            "id": "MEDIA-1",
            "caption": "ONE5970 — vista panoramica",
            "media_type": "VIDEO",
            "media_url": "https://cdn/video.mp4",
            "permalink": "https://instagram.com/p/abc",
            "thumbnail_url": "https://cdn/thumb.jpg",
            "timestamp": "2026-05-12T08:00:00+0000",
            "like_count": 88,
            "comments_count": 4,
        }
        media = media_body_to_instagram_media(body, ig_user_id="999")
        assert isinstance(media, InstagramMedia)
        assert media.id == "MEDIA-1"
        assert media.ig_user_id == "999"
        assert media.media_type == "VIDEO"
        assert media.like_count == 88

    def test_insight_body_flattens_to_metric_dict(self):
        body = {
            "data": [
                {
                    "name": "post_impressions",
                    "period": "lifetime",
                    "values": [{"value": 1234}],
                },
                {
                    "name": "post_engaged_users",
                    "period": "lifetime",
                    "values": [{"value": 87}],
                },
                {
                    "name": "post_reactions_like_total",
                    "period": "lifetime",
                    "values": [{"value": {"like": 40, "love": 2}}],  # dict flatten
                },
            ]
        }
        insights = insight_body_to_post_insights(body, object_id="111_222")
        assert isinstance(insights, PostInsights)
        assert insights.object_id == "111_222"
        assert insights.period == "lifetime"
        assert insights.metrics["post_impressions"] == 1234
        assert insights.metrics["post_engaged_users"] == 87
        # dict-valued metric got summed.
        assert insights.metrics["post_reactions_like_total"] == 42

    def test_insight_body_handles_empty_data(self):
        insights = insight_body_to_post_insights({"data": []}, object_id="x")
        assert insights.metrics == {}


# ─── Error envelope parser ────────────────────────────────────────────
class TestGraphErrorParsing:
    def _make_response(self, json_body, status_code):
        request = httpx.Request("GET", "https://graph.facebook.com/v21.0/me")
        return httpx.Response(
            status_code=status_code,
            json=json_body,
            request=request,
        )

    def test_raises_for_error_envelope_even_on_http_200(self):
        # Graph occasionally returns 200 with an error body (paging edge cases).
        body = {
            "error": {
                "message": "Invalid OAuth access token.",
                "type": "OAuthException",
                "code": 190,
                "fbtrace_id": "ABC123",
            }
        }
        response = self._make_response(body, status_code=200)
        with pytest.raises(MetaGraphError) as exc_info:
            _raise_for_graph_error(response)
        err = exc_info.value
        assert err.code == 190
        assert err.is_auth_error is True
        assert err.fbtrace_id == "ABC123"

    def test_rate_limit_codes_classified(self):
        body = {"error": {"message": "rate", "code": 4, "type": "OAuthException"}}
        response = self._make_response(body, status_code=200)
        with pytest.raises(MetaGraphError) as exc_info:
            _raise_for_graph_error(response)
        assert exc_info.value.is_rate_limited is True
        assert exc_info.value.is_auth_error is False

    def test_http_error_without_envelope_still_raises(self):
        # Some upstream failures (503, gateway timeouts) return text/html.
        request = httpx.Request("GET", "https://graph.facebook.com/v21.0/me")
        response = httpx.Response(
            status_code=503,
            content=b"<html>Service unavailable</html>",
            request=request,
        )
        with pytest.raises(MetaGraphError) as exc_info:
            _raise_for_graph_error(response)
        assert exc_info.value.http_status == 503

    def test_success_body_passes_through(self):
        response = self._make_response({"data": [{"id": "1"}]}, status_code=200)
        _raise_for_graph_error(response)  # must not raise


# ─── OAuth token exchange (httpx-mocked) ──────────────────────────────
class TestOAuthExchange:
    def test_code_for_token_passes_correct_params(self):
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            request = httpx.Request("GET", url)
            return httpx.Response(
                status_code=200,
                json={"access_token": "SHORT", "token_type": "bearer"},
                request=request,
            )

        with patch("httpx.get", side_effect=fake_get):
            bundle = exchange_code_for_token(
                code="THE-CODE",
                client_id="APP-ID",
                client_secret="APP-SECRET",
                redirect_uri="https://example.com/cb",
            )

        assert bundle["access_token"] == "SHORT"
        assert captured["url"].endswith("/oauth/access_token")
        assert captured["params"]["code"] == "THE-CODE"
        assert captured["params"]["client_id"] == "APP-ID"
        assert captured["params"]["client_secret"] == "APP-SECRET"
        assert captured["params"]["redirect_uri"] == "https://example.com/cb"

    def test_short_to_long_lived_uses_fb_exchange_grant(self):
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured["params"] = params
            request = httpx.Request("GET", url)
            return httpx.Response(
                status_code=200,
                json={
                    "access_token": "LONG",
                    "token_type": "bearer",
                    "expires_in": 5183944,
                },
                request=request,
            )

        with patch("httpx.get", side_effect=fake_get):
            bundle = exchange_short_for_long_lived(
                short_lived_token="SHORT",
                client_id="APP-ID",
                client_secret="APP-SECRET",
            )

        assert bundle["access_token"] == "LONG"
        assert captured["params"]["grant_type"] == "fb_exchange_token"
        assert captured["params"]["fb_exchange_token"] == "SHORT"


# ─── Factory ───────────────────────────────────────────────────────────
class TestFactory:
    def test_returns_fake_when_no_credentials(self):
        adapter = get_meta_adapter()
        assert isinstance(adapter, FakeMetaAdapter)

    def test_returns_fake_when_no_credential_row(self):
        from uuid import uuid4

        class _NoRowStore:
            def get(self, *, org_id, provider):  # noqa: ARG002
                return None

        class _Settings:
            meta_app_id = "x"
            meta_app_secret = "y"

        adapter = get_meta_adapter(
            org_id=uuid4(),
            credential_store=_NoRowStore(),
            settings=_Settings(),
        )
        assert isinstance(adapter, FakeMetaAdapter)


# ─── Scope discovery / resolution ─────────────────────────────────────
class TestScopeDiscovery:
    def test_app_access_token_concatenates(self):
        assert app_access_token("123", "secret") == "123|secret"

    def test_discover_returns_graph_perms_when_present(self):
        body = {
            "data": [
                {"permission": "pages_show_list", "status": "live"},
                {"permission": "instagram_basic", "status": "approved"},
                # status="declined" should be filtered out
                {"permission": "something_else", "status": "declined"},
            ]
        }

        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, json=body, request=request)

        with patch("httpx.Client") as mock_client_cls:
            client = mock_client_cls.return_value.__enter__.return_value
            client.get.side_effect = fake_get
            perms = discover_app_permissions(app_id="123", app_secret="x")

        assert perms == ["pages_show_list", "instagram_basic"]

    def test_discover_falls_back_to_kitchen_sink_on_empty(self):
        body = {"data": []}

        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, json=body, request=request)

        with patch("httpx.Client") as mock_client_cls:
            client = mock_client_cls.return_value.__enter__.return_value
            client.get.side_effect = fake_get
            perms = discover_app_permissions(app_id="123", app_secret="x")

        assert perms == list(META_KITCHEN_SINK_SCOPES)

    def test_discover_falls_back_on_graph_error(self):
        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(
                status_code=400,
                json={"error": {"message": "boom", "code": 100}},
                request=request,
            )

        with patch("httpx.Client") as mock_client_cls:
            client = mock_client_cls.return_value.__enter__.return_value
            client.get.side_effect = fake_get
            perms = discover_app_permissions(app_id="123", app_secret="x")

        assert perms == list(META_KITCHEN_SINK_SCOPES)

    def test_resolve_uses_configured_when_explicit(self):
        scopes = resolve_oauth_scopes(
            configured="a,b,c",
            app_id="123",
            app_secret="x",
        )
        assert scopes == ["a", "b", "c"]

    def test_resolve_deduplicates_and_strips(self):
        scopes = resolve_oauth_scopes(
            configured="a, b , a, c, b",
            app_id="123",
            app_secret="x",
        )
        assert scopes == ["a", "b", "c"]

    def test_resolve_auto_triggers_discovery(self):
        body = {
            "data": [
                {"permission": "pages_show_list", "status": "live"},
            ]
        }

        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, json=body, request=request)

        with patch("httpx.Client") as mock_client_cls:
            client = mock_client_cls.return_value.__enter__.return_value
            client.get.side_effect = fake_get
            scopes = resolve_oauth_scopes(
                configured="auto",
                app_id="123",
                app_secret="x",
            )

        assert scopes == ["pages_show_list"]

    def test_resolve_empty_string_treated_as_auto(self):
        body = {"data": []}  # → fallback path

        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, json=body, request=request)

        with patch("httpx.Client") as mock_client_cls:
            client = mock_client_cls.return_value.__enter__.return_value
            client.get.side_effect = fake_get
            scopes = resolve_oauth_scopes(
                configured="",
                app_id="123",
                app_secret="x",
            )

        assert scopes == list(META_KITCHEN_SINK_SCOPES)


# ─── System User Token path ───────────────────────────────────────────
class TestSystemUserToken:
    """The Path B auth mode — token-based, no OAuth flow."""

    def test_factory_prefers_system_user_token_over_oauth(self):
        from app.services.meta import MetaOAuthAdapter, get_meta_adapter

        class _Settings:
            meta_system_user_token = "SYSTEM_USER_TOKEN_VALUE"
            meta_app_id = ""
            meta_app_secret = ""

        adapter = get_meta_adapter(settings=_Settings())
        assert isinstance(adapter, MetaOAuthAdapter)
        assert adapter.auth_mode == "system_user"

    def test_user_token_returns_system_token_when_configured(self):
        from app.services.meta import MetaOAuthAdapter

        class _Settings:
            meta_system_user_token = "SYS-TOKEN-123"

        adapter = MetaOAuthAdapter(settings=_Settings())
        assert adapter._user_token() == "SYS-TOKEN-123"
        assert adapter.auth_mode == "system_user"

    def test_user_oauth_mode_when_no_system_token(self):
        from uuid import uuid4

        from app.services.meta import MetaOAuthAdapter

        class _Settings:
            meta_system_user_token = ""

        class _Store:
            class _Stored:
                tokens = {"access_token": "USER-OAUTH-TOKEN"}

            def get(self, *, org_id, provider):  # noqa: ARG002
                return self._Stored()

        adapter = MetaOAuthAdapter(
            credential_store=_Store(),
            org_id=uuid4(),
            settings=_Settings(),
        )
        assert adapter._user_token() == "USER-OAUTH-TOKEN"
        assert adapter.auth_mode == "user_oauth"

    def test_user_token_raises_when_neither_path_configured(self):
        from app.services.meta import MetaOAuthAdapter
        from app.services.meta._meta_api import MetaGraphError

        class _Settings:
            meta_system_user_token = ""

        adapter = MetaOAuthAdapter(settings=_Settings())
        with pytest.raises(MetaGraphError) as exc_info:
            adapter._user_token()
        assert "META_SYSTEM_USER_TOKEN" in str(exc_info.value)


# ─── Fake adapter sanity ──────────────────────────────────────────────
class TestFakeAdapter:
    def test_seeded_data_is_returned_in_order(self):
        adapter = FakeMetaAdapter()
        adapter.seed(
            pages=[
                FacebookPage(
                    page_id="111",
                    name="Imobiliaria One",
                    category="Real Estate",
                    access_token="P",
                ),
            ],
            posts_by_page={
                "111": [
                    FacebookPost(
                        id="111_222",
                        page_id="111",
                        message="Novo imovel",
                        created_at=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
                        permalink_url=None,
                        likes_count=12,
                        comments_count=3,
                    ),
                ]
            },
        )
        assert adapter.list_pages()[0].page_id == "111"
        posts = adapter.list_facebook_posts("111", limit=10)
        assert posts[0].likes_count == 12
        assert adapter.list_facebook_posts("999") == []  # unknown page

    def test_limit_truncates(self):
        adapter = FakeMetaAdapter()
        adapter.seed(
            pages=[
                FacebookPage(page_id="111", name="X", category=None, access_token=""),
            ],
            posts_by_page={
                "111": [
                    FacebookPost(
                        id=f"111_{i}",
                        page_id="111",
                        message=f"post {i}",
                        created_at=None,
                        permalink_url=None,
                    )
                    for i in range(20)
                ]
            },
        )
        assert len(adapter.list_facebook_posts("111", limit=5)) == 5
