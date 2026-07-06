"""Tests for meta_content_router — publish (IG/FB) + FB posts list.

Account-scoped (Wave 3): the adapter is injected via
``get_account_adapter`` DI override (``FakeMetaAdapter``), never a real
credential row. Covers the uniform ``MetaGraphError`` gate (
``requires_app_review`` → 200 structured, other errors → 502
structured)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    FacebookPost,
    FakeMetaAdapter,
    MetaGraphError,
)
from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock

_ACCOUNT = "00000000-0000-4000-8000-0000000000ac"
_ORG = "00000000-0000-4000-8000-000000000099"
_IG_USER = "17841400000000000"
_PAGE = "112233445566"
_QS = f"account_id={_ACCOUNT}&org_id={_ORG}"


class _GatedAdapter(FakeMetaAdapter):
    """Raises a chosen ``MetaGraphError`` for every write call — the
    write-surface analog of ``test_ig_insights._RaisingFakeMetaAdapter``."""

    def __init__(self, *, error: MetaGraphError | None = None) -> None:
        super().__init__()
        self._error = error

    def publish_instagram_media(self, *a, **kw):
        if self._error:
            raise self._error
        return super().publish_instagram_media(*a, **kw)

    def publish_instagram_carousel(self, *a, **kw):
        if self._error:
            raise self._error
        return super().publish_instagram_carousel(*a, **kw)

    def publish_instagram_reel(self, *a, **kw):
        if self._error:
            raise self._error
        return super().publish_instagram_reel(*a, **kw)

    def publish_instagram_story(self, *a, **kw):
        if self._error:
            raise self._error
        return super().publish_instagram_story(*a, **kw)

    def publish_facebook_post(self, *a, **kw):
        if self._error:
            raise self._error
        return super().publish_facebook_post(*a, **kw)

    def publish_facebook_video(self, *a, **kw):
        if self._error:
            raise self._error
        return super().publish_facebook_video(*a, **kw)

    def list_facebook_posts(self, *a, **kw):
        if self._error:
            raise self._error
        return super().list_facebook_posts(*a, **kw)


def _seed_ig_account(adapter: FakeMetaAdapter) -> FakeMetaAdapter:
    from noctusai_lib.integrations.meta import InstagramAccount

    adapter.seed(ig_accounts=[InstagramAccount(id=_IG_USER, username="one")])
    return adapter


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    from app.main import app

    app.dependency_overrides.clear()


def _override(adapter):
    from app.main import app
    from app.routers._meta_common import get_account_adapter

    app.dependency_overrides[get_account_adapter] = lambda: adapter
    return adapter


# ─── Instagram publish ───────────────────────────────────────────────────
class TestInstagramPublish:
    def test_publish_media_happy_path(self, client):
        _override(_seed_ig_account(FakeMetaAdapter()))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "media", "media_url": "https://x/img.jpg", "caption": "hi"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ig_user_id"] == _IG_USER
        assert body["id"]

    def test_publish_carousel_requires_two_urls(self, client):
        _override(_seed_ig_account(FakeMetaAdapter()))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "carousel", "media_urls": ["https://x/a.jpg"]},
        )
        assert resp.status_code == 422, resp.text

    def test_publish_reel_happy_path(self, client):
        _override(_seed_ig_account(FakeMetaAdapter()))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "reel", "media_url": "https://x/v.mp4"},
        )
        assert resp.status_code == 200, resp.text

    def test_publish_story_happy_path(self, client):
        _override(_seed_ig_account(FakeMetaAdapter()))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "story", "media_url": "https://x/s.jpg"},
        )
        assert resp.status_code == 200, resp.text

    def test_publish_app_review_gate_returns_200_structured(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("permission denied", code=10, http_status=400)
        )
        _override(_seed_ig_account(gated))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "media", "media_url": "https://x/img.jpg"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_app_review"] is True
        assert body["error"]

    def test_publish_other_graph_error_returns_502(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("rate limited", code=4, http_status=429)
        )
        _override(_seed_ig_account(gated))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "media", "media_url": "https://x/img.jpg"},
        )
        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]

    def test_unknown_key_rejected_422(self, client):
        _override(_seed_ig_account(FakeMetaAdapter()))
        resp = client.post(
            f"/api/meta/instagram/publish?{_QS}",
            json={"kind": "media", "media_url": "https://x/img.jpg", "bogus": 1},
        )
        assert resp.status_code == 422, resp.text


# ─── Facebook publish ────────────────────────────────────────────────────
class TestFacebookPublish:
    def test_publish_post_happy_path(self, client):
        _override(FakeMetaAdapter())
        resp = client.post(
            f"/api/meta/facebook/publish?{_QS}",
            json={"kind": "post", "page_id": _PAGE, "message": "hello"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["page_id"] == _PAGE

    def test_publish_photo_requires_photo_url(self, client):
        _override(FakeMetaAdapter())
        resp = client.post(
            f"/api/meta/facebook/publish?{_QS}",
            json={"kind": "photo", "page_id": _PAGE},
        )
        assert resp.status_code == 422, resp.text

    def test_publish_video_happy_path(self, client):
        _override(FakeMetaAdapter())
        resp = client.post(
            f"/api/meta/facebook/publish?{_QS}",
            json={"kind": "video", "page_id": _PAGE, "video_url": "https://x/v.mp4"},
        )
        assert resp.status_code == 200, resp.text

    def test_publish_app_review_gate_returns_200_structured(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("permission denied", code=200, http_status=400)
        )
        _override(gated)
        resp = client.post(
            f"/api/meta/facebook/publish?{_QS}",
            json={"kind": "post", "page_id": _PAGE, "message": "hello"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["requires_app_review"] is True


# ─── Facebook posts list ─────────────────────────────────────────────────
class TestFacebookPostsList:
    def test_list_posts(self, client):
        adapter = FakeMetaAdapter()
        adapter.seed(
            posts_by_page={
                _PAGE: [FacebookPost(id="p1", message="hi", likes=3, comments=1)]
            }
        )
        _override(adapter)
        resp = client.get(f"/api/meta/facebook/posts?{_QS}&page_id={_PAGE}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["posts"]) == 1
        assert body["posts"][0]["id"] == "p1"
        assert body["posts"][0]["likes"] == 3

    def test_list_posts_graph_error_502(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("boom", code=4, http_status=500)
        )
        _override(gated)
        resp = client.get(f"/api/meta/facebook/posts?{_QS}&page_id={_PAGE}")
        assert resp.status_code == 502, resp.text
