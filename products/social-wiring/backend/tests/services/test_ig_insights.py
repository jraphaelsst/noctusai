"""Tests for the Instagram + Facebook insights backend slice — Wave 3
(account-scoped).

Covers:
  - GET /api/meta/context — instagram/pages/user shape
  - GET /api/meta/instagram/insights — metrics+series, resolved from the
    account (no ig_user_id path param)
  - GET /api/meta/instagram/media — per-item insights, and the per-item
    error guard (one bad media item never fails the list)
  - GET /api/meta/facebook/insights — per-metric degrade
  - POST .../snapshot persists + GET .../snapshots reads it back
  - The uniform Wave 3 MetaGraphError gate: requires_app_review → 200
    structured; other MetaGraphError → 502 structured
  - The service layer directly (capture_ig_snapshot /
    capture_all_ig_snapshots / IGAccountNotFoundError) — unchanged,
    still org-scoped (the daily scheduler's Store-A path)

The adapter is injected via the ``get_account_adapter`` FastAPI
dependency (``app.dependency_overrides``) — no monkey-patching of
production code, per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    FacebookPage,
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
_ACCOUNT = "00000000-0000-4000-8000-0000000000ac"
_IG_USER = "17841400000000000"
_PAGE = "112233445566"


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
    ids/scopes. The seed Fake never raises on its own (it's the
    "scope already approved" happy path) — error-branch tests need this
    thin subclass to exercise the router's uniform gate."""

    def __init__(
        self,
        *,
        raise_account_insights_for: frozenset[str] = frozenset(),
        raise_media_insights_for: frozenset[str] = frozenset(),
        raise_list_instagram_accounts: bool = False,
        app_review_gate_on_account_insights: bool = False,
    ) -> None:
        super().__init__()
        self._raise_account_insights_for = raise_account_insights_for
        self._raise_media_insights_for = raise_media_insights_for
        self._raise_list_instagram_accounts = raise_list_instagram_accounts
        self._app_review_gate = app_review_gate_on_account_insights

    def list_instagram_accounts(self):
        if self._raise_list_instagram_accounts:
            raise MetaGraphError("simulated graph failure", code=1, http_status=400)
        return super().list_instagram_accounts()

    def get_instagram_account_insights(self, ig_user_id, **kwargs):
        if self._app_review_gate:
            raise MetaGraphError(
                "permission denied", code=10, http_status=400
            )
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
    raise_list_instagram_accounts: bool = False,
    app_review_gate_on_account_insights: bool = False,
) -> FakeMetaAdapter:
    adapter = _RaisingFakeMetaAdapter(
        raise_account_insights_for=raise_account_insights_for,
        raise_media_insights_for=raise_media_insights_for,
        raise_list_instagram_accounts=raise_list_instagram_accounts,
        app_review_gate_on_account_insights=app_review_gate_on_account_insights,
    )
    adapter.seed(
        me={"id": "meta-user-1", "name": "One Consultoria"},
        pages=[
            FacebookPage(id=_PAGE, name="One Consultoria Page", fan_count=500),
        ],
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
        page_insights={
            _PAGE: PostInsights(
                object_id=_PAGE,
                metrics={"page_impressions_unique": 900},
                raw=[{"name": "page_impressions_unique", "period": "day", "values": [{"value": 900}]}],
            )
        },
    )
    return adapter


@pytest.fixture
def ig_client():
    """TestClient with a schema-caching mock admin client. Most Meta
    endpoints here take ``account_id`` and resolve their adapter (and,
    since ``sw-meta-org-auth-wiring``, their org) entirely through the
    ``get_account_adapter`` DI-seam override below — overriding that ONE
    dependency also bypasses its own nested
    ``Depends(get_current_user_org)``, so those endpoints need no
    Authorization header in tests. The ``/instagram/snapshot(s)``
    endpoints additionally take a SIBLING ``Depends(get_current_user_org)``
    of their own (not nested inside ``get_account_adapter`` — the
    ``ig_metric_snapshots`` table read/write is a second org-scoped
    query) — those tests override it via ``_override_session_org``."""
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
    from app.routers._meta_common import get_account_adapter

    app.dependency_overrides[get_account_adapter] = lambda: adapter
    return adapter


def _override_session_org(org_id: str = _ORG) -> None:
    """Override ``get_current_user_org`` so the session resolves to
    ``org_id`` — the DI seam the ``/instagram/snapshot(s)`` endpoints
    depend on directly (``KB § PATTERNS/backend/di-test-seam.md``,
    Class-A)."""
    from app.dependencies import get_current_user_org
    from app.main import app

    app.dependency_overrides[get_current_user_org] = lambda: (object(), "test-token", org_id)


_QS = f"account_id={_ACCOUNT}&org_id={_ORG}"


# ─── GET /context ────────────────────────────────────────────────────────
class TestContextEndpoint:
    def test_context_shape(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/context?{_QS}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["adapter"] == "fake"
        assert body["instagram"]["id"] == _IG_USER
        assert body["instagram"]["username"] == "one_consultoria"
        assert len(body["pages"]) == 1
        assert body["pages"][0]["id"] == _PAGE
        assert body["user"]["id"] == "meta-user-1"

    def test_context_no_instagram_is_null(self, ig_client):
        adapter = FakeMetaAdapter()
        adapter.seed(me={"id": "u1"}, pages=[FacebookPage(id=_PAGE, name="Page")])
        _override_adapter(adapter)
        resp = ig_client.get(f"/api/meta/context?{_QS}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["instagram"] is None

    def test_context_graph_error_502(self, ig_client):
        _override_adapter(_seeded_adapter(raise_list_instagram_accounts=True))
        resp = ig_client.get(f"/api/meta/context?{_QS}")
        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]


# ─── GET /instagram/insights ─────────────────────────────────────────────
class TestInsightsEndpoint:
    def test_insights_metrics_and_series(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/instagram/insights?{_QS}&days=7")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["object_id"] == _IG_USER
        assert body["metrics"]["reach"] == 500
        assert body["metrics"]["profile_views"] == 40
        assert len(body["series"]) == 1

    def test_insights_graph_error_returns_502(self, ig_client):
        _override_adapter(
            _seeded_adapter(raise_account_insights_for=frozenset({_IG_USER}))
        )
        resp = ig_client.get(f"/api/meta/instagram/insights?{_QS}")
        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]

    def test_insights_app_review_gate_returns_200(self, ig_client):
        _override_adapter(
            _seeded_adapter(app_review_gate_on_account_insights=True)
        )
        resp = ig_client.get(f"/api/meta/instagram/insights?{_QS}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_app_review"] is True
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

        resp = ig_client.get(f"/api/meta/instagram/insights?{_QS}&days=0")
        assert resp.status_code == 200, resp.text
        assert captured["since"] is None
        assert captured["until"] is None


# ─── GET /instagram/media ────────────────────────────────────────────────
class TestMediaEndpoint:
    def test_media_with_per_item_insights(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/instagram/media?{_QS}")
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
        resp = ig_client.get(f"/api/meta/instagram/media?{_QS}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["media"]) == 2
        m1 = next(m for m in body["media"] if m["id"] == "media-1")
        m2 = next(m for m in body["media"] if m["id"] == "media-2")
        assert m1["insights"] == {"reach": 100, "saved": 3}
        assert m2["insights"] is None  # one bad item never fails the page

    def test_with_insights_false_skips_the_per_item_fetch(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/instagram/media?{_QS}&with_insights=false")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert all(m["insights"] is None for m in body["media"])


# ─── GET /facebook/insights ──────────────────────────────────────────────
class TestFacebookInsightsEndpoint:
    def test_page_insights_metrics(self, ig_client):
        _override_adapter(_seeded_adapter())
        resp = ig_client.get(f"/api/meta/facebook/insights?{_QS}&page_id={_PAGE}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["object_id"] == _PAGE
        assert body["metrics"]["page_impressions_unique"] == 900


# ─── POST snapshot / GET snapshots ───────────────────────────────────────
class TestSnapshotEndpoints:
    def test_snapshot_persists_and_reads_back(self, ig_client):
        _override_adapter(_seeded_adapter())
        _override_session_org()

        post_resp = ig_client.post(f"/api/meta/instagram/snapshot?{_QS}")
        assert post_resp.status_code == 200, post_resp.text
        snap = post_resp.json()
        assert snap["followers_count"] == 1200
        assert snap["follows_count"] == 180
        assert snap["media_count"] == 42
        assert snap["reach"] == 500
        assert snap["profile_views"] == 40

        get_resp = ig_client.get(f"/api/meta/instagram/snapshots?{_QS}")
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert len(body["snapshots"]) == 1
        assert body["snapshots"][0]["followers_count"] == 1200
        assert body["snapshots"][0]["reach"] == 500


# ─── Service layer (unchanged — org-scoped Store-A daily scheduler path) ──
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


@pytest.mark.usefixtures("isolate_meta_config_db")
class TestCaptureAllIgSnapshots:
    def test_no_meta_connection_returns_empty_list(self):
        """No stored credential / system-user token configured in test
        settings → the product factory falls back to a FRESH (unseeded)
        FakeMetaAdapter, whose `list_instagram_accounts()` is empty.
        Documents the "no connection → [] not an error" contract."""
        mock_sb = MockSupabaseClient()
        rows = capture_all_ig_snapshots(mock_sb, _ORG)
        assert rows == []
