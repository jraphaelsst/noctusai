"""Tests for meta_comments_router — list/create/reply/hide/delete, IG+FB.

Account-scoped (Wave 3). Covers the reconciled contract: GET list, POST
create-or-reply (``parent_comment_id`` discriminates for IG), POST
``/hide`` sub-route, DELETE via query param — plus the uniform
``MetaGraphError`` gate."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    FacebookComment,
    FakeMetaAdapter,
    InstagramComment,
    MetaGraphError,
)
from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock

_ACCOUNT = "00000000-0000-4000-8000-0000000000ac"
_ORG = "00000000-0000-4000-8000-000000000099"
_QS = f"account_id={_ACCOUNT}&org_id={_ORG}"


class _GatedAdapter(FakeMetaAdapter):
    def __init__(self, *, error: MetaGraphError) -> None:
        super().__init__()
        self._error = error

    def reply_instagram_comment(self, *a, **kw):
        raise self._error

    def create_instagram_comment(self, *a, **kw):
        raise self._error

    def hide_instagram_comment(self, *a, **kw):
        raise self._error

    def delete_instagram_comment(self, *a, **kw):
        raise self._error


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


# ─── Instagram ───────────────────────────────────────────────────────────
class TestInstagramComments:
    def test_list(self, client):
        adapter = FakeMetaAdapter()
        adapter.seed(
            ig_comments_by_media={
                "media-1": [
                    InstagramComment(id="c1", text="nice", username="bob", like_count=2)
                ]
            }
        )
        _override(adapter)
        resp = client.get(f"/api/meta/instagram/comments?{_QS}&media_id=media-1")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["comments"]) == 1
        assert body["comments"][0]["id"] == "c1"
        assert body["comments"][0]["author"] == "bob"

    def test_create_top_level_when_no_parent(self, client):
        _override(FakeMetaAdapter())
        resp = client.post(
            f"/api/meta/instagram/comments?{_QS}",
            json={"media_id": "media-1", "message": "hello"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == "hello"
        assert body["parent_id"] is None

    def test_reply_when_parent_given(self, client):
        adapter = FakeMetaAdapter()
        _override(adapter)
        resp = client.post(
            f"/api/meta/instagram/comments?{_QS}",
            json={"media_id": "media-1", "message": "reply!", "parent_comment_id": "c1"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["parent_id"] == "c1"
        assert len(adapter.replied_instagram_comments) == 1

    def test_hide(self, client):
        adapter = FakeMetaAdapter()
        _override(adapter)
        resp = client.post(
            f"/api/meta/instagram/comments/hide?{_QS}",
            json={"comment_id": "c1", "hide": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"comment_id": "c1", "hidden": True}
        assert adapter.hidden_instagram_comments == [("c1", True)]

    def test_delete(self, client):
        adapter = FakeMetaAdapter()
        _override(adapter)
        resp = client.delete(f"/api/meta/instagram/comments?{_QS}&comment_id=c1")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"comment_id": "c1", "deleted": True}
        assert adapter.deleted_instagram_comment_ids == ["c1"]

    def test_create_app_review_gate_returns_200_structured(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("permission denied", code=10, http_status=400)
        )
        _override(gated)
        resp = client.post(
            f"/api/meta/instagram/comments?{_QS}",
            json={"media_id": "media-1", "message": "hello"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["requires_app_review"] is True

    def test_delete_other_graph_error_returns_502(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("boom", code=4, http_status=500)
        )
        _override(gated)
        resp = client.delete(f"/api/meta/instagram/comments?{_QS}&comment_id=c1")
        assert resp.status_code == 502, resp.text


# ─── Facebook ────────────────────────────────────────────────────────────
class TestFacebookComments:
    def test_list(self, client):
        adapter = FakeMetaAdapter()
        adapter.seed(
            fb_comments_by_post={
                "post-1": [
                    FacebookComment(id="fc1", message="great", from_name="Alice")
                ]
            }
        )
        _override(adapter)
        resp = client.get(f"/api/meta/facebook/comments?{_QS}&post_id=post-1")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["comments"][0]["author"] == "Alice"

    def test_create(self, client):
        adapter = FakeMetaAdapter()
        _override(adapter)
        resp = client.post(
            f"/api/meta/facebook/comments?{_QS}",
            json={"post_id": "post-1", "message": "hi there"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == "hi there"
        assert len(adapter.created_facebook_comments) == 1

    def test_hide(self, client):
        adapter = FakeMetaAdapter()
        _override(adapter)
        resp = client.post(
            f"/api/meta/facebook/comments/hide?{_QS}",
            json={"comment_id": "fc1", "hide": False},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"comment_id": "fc1", "hidden": False}

    def test_delete(self, client):
        adapter = FakeMetaAdapter()
        _override(adapter)
        resp = client.delete(f"/api/meta/facebook/comments?{_QS}&comment_id=fc1")
        assert resp.status_code == 200, resp.text
        assert adapter.deleted_facebook_comment_ids == ["fc1"]
