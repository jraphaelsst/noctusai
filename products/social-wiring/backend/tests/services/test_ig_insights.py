"""Tests for the Instagram insights (v1) backend slice — W-ig-insights.

Covers:
  - GET /api/meta/instagram/accounts — shape + adapter label
  - GET /api/meta/instagram/{id}/insights — metrics+series, and the
    non-raising MetaGraphError→error-field posture (mirrors meta_status)
  - GET /api/meta/instagram/{id}/media — per-item insights, and the
    per-item error guard (one bad media item never fails the list)
  - POST .../snapshot persists + GET .../snapshots reads it back
  - 404 on an unknown ig_user_id
  - The service layer directly (capture_ig_snapshot /
    capture_all_ig_snapshots / IGAccountNotFoundError)

The adapter is injected via the ``get_ig_adapter`` FastAPI dependency
(``app.dependency_overrides``) — no monkey-patching of production code,
per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    FakeMetaAdapter,
    InstagramAccount,
    InstagramMedia,
    MetaGraphError,
    PostInsights,
)
from noctusai_lib.testing import (
    MockSupabaseClient,
    bind_consent_module_to_mock,
)

from app.services.meta.snapshots import (
    IGAccountNotFoundError,
    capture_all_ig_snapshots,
    capture_ig_snapshot,
)

_ORG = "00000000-0000-4000-8000-000000000099"
_IG_USER = "17841400000000000"


# ─── Test doubles ───────────────────────────────────────────────────────
class _SchemaCachingClient:
    """Caches ``.schema(name)`` results so a write made by one request
    handler invocation is visible to a LATER one.

    ``MockSupabaseClient.schema(name)`` returns a fresh scoped client
    (with its own empty per-table row list) on EVERY call — fine within
    a single handler, but the router calls ``get_admin_client()`` +
    ``.schema(...)`` fresh on every request, so a POST-then-GET pair of
    TestClient calls needs this thin cache wrapper to observe the
    earlier write. Test-only; not a production code path.
    """

    def __init__(self, root: MockSupabaseClient) -> None:
        self._root = root
        self._scoped: dict[str, Any] = {}

    def schema(self, name: str):
        if name not in self._scoped:
            self._scoped[name] = self._root.schema(name)
        return self._scoped[name]

    def __getattr__(self, item):
        return getattr(self._root, item)


class _RaisingFakeMetaAdapter(FakeMetaAdapter):
    """``FakeMetaAdapter`` that raises ``MetaGraphError`` for specific
    ids. The seed Fake never raises on its own (it's the
    "scope already approved" happy path) — error-branch tests need this
    thin subclass to exercise the router's non-raising posture."""

    def __init__(
        self,
        *,
        raise_account_insights_for: frozenset[str] = frozenset(),
        raise_media_insights_for: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__()
        self._raise_account_insights_for = raise_account_insights_for
        self._raise_media_insights_for = raise_media_insights_for

    def get_instagram_account_insights(self, ig_user_id, **kwargs):
        if ig_user_id in self._raise_account_insights_for:
            raise MetaGraphError(
                "simulated graph failure", code=1, http_status=400
            )
        return super().get_instagram_account_insights(ig_user_id, **kwargs)

    def get_instagram_media_insights(self, media_id):
        if media_id in self._raise_media_insights_for:
            raise MetaGraphError(
                "simulated graph failure", code=1, http_status=400
            )
        return super().get_instagram_media_insights(media_id)


def _seeded_adapter(
    *,
    raise_account_insights_for: frozenset[str] = frozenset(),
    raise_media_insights_for: frozenset[str] = frozenset(),
) -> FakeMetaAdapter:
    adapter = _RaisingFakeMetaAdapter(
        raise_account_insights_for=raise_account_insights_for,
        raise_media_insights_for=raise_media_insights_for,
    )
    adapter.seed(
        ig_accounts=[
            InstagramAccount(
                id=_IG_USER,
                username="one_consultoria",
                name="One Consultoria",
                followers_count=1200,
                follows_count=180,
                media_count=42,
            )
        ],
        media_by_ig_user={
            _IG_USER: [
                InstagramMedia(
                    id="media-1", caption="Post 1", media_type="IMAGE",
                    like_count=10, comments_count=2,
                ),
                InstagramMedia(
                    id="media-2", caption="Post 2", media_type="VIDEO",
                    like_count=20, comments_count=5,
                ),
            ]
        },
        media_insights={
            "media-1": PostInsights(
                object_id="media-1", metrics={"reach": 100, "saved": 3}
            ),
        },
        account_insights={
            _IG_USER: PostInsights(
                object_id=_IG_USER,
                metrics={"reach": 500, "profile_views": 40},
                raw=[{"name": "reach", "period": "day", "values": [{"value": 500}]}],
            )
        },
    )
    return adapter


@pytest.fixture
def ig_client():
    """TestClient with a schema-caching mock admin client. No auth
    headers needed — the IG insights endpoints (like meta_router) run
    with an ``org_id`` query param, mirroring ``meta_status``."""
    mock_sb = MockSupabaseClient()
    caching = _SchemaCachingClient(mock_sb)

    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=caching),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    from app.main import app

    app.dependency_overrides.clear()


def _override_adapter(adapter: FakeMetaAdapter) -> FakeMetaAdapter:
    from app.main import app
    from app.routers.meta_insights_router import get_ig_adapter

    app.dependency_overrides[get_ig_adapter] = lambda: adapter
    return adapter


# ─── GET /accounts ───────────────────────────────────────────────────────
class TestAccountsEndpoint:
    def test_list_accounts_shape(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/instagram/accounts?org_id={_ORG}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["adapter"] == "fake"
        assert len(body["accounts"]) == 1
        account = body["accounts"][0]
        assert account["id"] == _IG_USER
        assert account["username"] == "one_consultoria"
        assert account["followers_count"] == 1200
        assert account["media_count"] == 42


# ─── GET /{id}/insights ──────────────────────────────────────────────────
class TestInsightsEndpoint:
    def test_insights_metrics_and_series(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(
            f"/api/meta/instagram/{_IG_USER}/insights?org_id={_ORG}&days=7"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["object_id"] == _IG_USER
        assert body["metrics"]["reach"] == 500
        assert body["metrics"]["profile_views"] == 40
        assert len(body["series"]) == 1
        assert body["error"] is None

    def test_insights_graph_error_returns_200_with_error_field(self, ig_client):
        _override_adapter(
            _seeded_adapter(raise_account_insights_for=frozenset({_IG_USER}))
        )
        resp = ig_client.get(
            f"/api/meta/instagram/{_IG_USER}/insights?org_id={_ORG}"
        )
        # Non-raising posture — a Graph failure is a 200 with a
        # structured error, never a 500.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metrics"] == {}
        assert body["series"] == []
        assert body["error"]

    def test_days_zero_omits_since_until_window(self, ig_client):
        captured: dict = {}
        adapter = _seeded_adapter()
        original = adapter.get_instagram_account_insights

        def _capturing(ig_user_id, **kwargs):
            captured.update(kwargs)
            return original(ig_user_id, **kwargs)

        adapter.get_instagram_account_insights = _capturing
        _override_adapter(adapter)

        resp = ig_client.get(
            f"/api/meta/instagram/{_IG_USER}/insights?org_id={_ORG}&days=0"
        )
        assert resp.status_code == 200, resp.text
        assert captured["since"] is None
        assert captured["until"] is None


# ─── GET /{id}/media ─────────────────────────────────────────────────────
class TestMediaEndpoint:
    def test_media_with_per_item_insights(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/instagram/{_IG_USER}/media?org_id={_ORG}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["media"]) == 2
        m1 = next(m for m in body["media"] if m["id"] == "media-1")
        assert m1["insights"] == {"reach": 100, "saved": 3}
        assert m1["like_count"] == 10
        assert m1["comments_count"] == 2

    def test_media_per_item_error_guard_never_fails_the_list(self, ig_client):
        _override_adapter(
            _seeded_adapter(raise_media_insights_for=frozenset({"media-2"}))
        )
        resp = ig_client.get(f"/api/meta/instagram/{_IG_USER}/media?org_id={_ORG}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["media"]) == 2
        m1 = next(m for m in body["media"] if m["id"] == "media-1")
        m2 = next(m for m in body["media"] if m["id"] == "media-2")
        assert m1["insights"] == {"reach": 100, "saved": 3}
        assert m2["insights"] is None  # one bad item never fails the page

    def test_with_insights_false_skips_the_per_item_fetch(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(
            f"/api/meta/instagram/{_IG_USER}/media?org_id={_ORG}&with_insights=false"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert all(m["insights"] is None for m in body["media"])


# ─── POST snapshot / GET snapshots ───────────────────────────────────────
class TestSnapshotEndpoints:
    def test_snapshot_persists_and_reads_back(self, ig_client):
        _override_adapter(_seeded_adapter())

        post_resp = ig_client.post(
            f"/api/meta/instagram/{_IG_USER}/snapshot?org_id={_ORG}"
        )
        assert post_resp.status_code == 200, post_resp.text
        snap = post_resp.json()
        assert snap["followers_count"] == 1200
        assert snap["follows_count"] == 180
        assert snap["media_count"] == 42
        assert snap["reach"] == 500
        assert snap["profile_views"] == 40

        get_resp = ig_client.get(
            f"/api/meta/instagram/{_IG_USER}/snapshots?org_id={_ORG}"
        )
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert len(body["snapshots"]) == 1
        assert body["snapshots"][0]["followers_count"] == 1200
        assert body["snapshots"][0]["reach"] == 500

    def test_snapshot_404_on_unknown_account(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.post(
            f"/api/meta/instagram/unknown-ig-id/snapshot?org_id={_ORG}"
        )
        assert resp.status_code == 404


# ─── Service layer ───────────────────────────────────────────────────────
class TestCaptureIgSnapshot:
    def test_writes_expected_shape(self):
        mock_sb = MockSupabaseClient()
        adapter = _seeded_adapter()
        row = capture_ig_snapshot(mock_sb, _ORG, _IG_USER, adapter)
        assert row["org_id"] == _ORG
        assert row["ig_user_id"] == _IG_USER
        assert row["username"] == "one_consultoria"
        assert row["followers_count"] == 1200
        assert row["reach"] == 500
        assert row["profile_views"] == 40
        assert row["raw"]

    def test_raises_for_unknown_account(self):
        mock_sb = MockSupabaseClient()
        adapter = _seeded_adapter()
        with pytest.raises(IGAccountNotFoundError):
            capture_ig_snapshot(mock_sb, _ORG, "nope", adapter)

    def test_degrades_reach_and_profile_views_to_zero_on_graph_error(self):
        mock_sb = MockSupabaseClient()
        adapter = _seeded_adapter(
            raise_account_insights_for=frozenset({_IG_USER})
        )
        row = capture_ig_snapshot(mock_sb, _ORG, _IG_USER, adapter)
        # Account-level counts still land even when the insights call fails.
        assert row["followers_count"] == 1200
        assert row["reach"] == 0
        assert row["profile_views"] == 0


class TestCaptureAllIgSnapshots:
    def test_no_meta_connection_returns_empty_list(self):
        """No stored credential / system-user token configured in test
        settings → the product factory falls back to a FRESH (unseeded)
        FakeMetaAdapter, whose `list_instagram_accounts()` is empty.
        Documents the "no connection → [] not an error" contract."""
        mock_sb = MockSupabaseClient()
        rows = capture_all_ig_snapshots(mock_sb, _ORG)
        assert rows == []
