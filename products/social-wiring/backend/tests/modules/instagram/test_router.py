"""/api/instagram/accounts/{account_id}/... — auth boundary (strict 401),
org + provider + marca scoping, grid ordering + cursor pagination, history
shape, sync trigger.

DI seams only (``app.dependency_overrides``): ``get_current_user_org``
(session), ``get_ig_repository`` (in-memory PostgREST double),
``get_ig_adapter_builder`` (seed ``FakeInstagramLoginAdapter``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    FakeInstagramLoginAdapter,
    IgMediaItem,
    IgProfile,
    MetaGraphError,
)

from app.modules.instagram.repository import IgInsightsRepository, encode_cursor
from tests.modules.instagram.fakes import FakeSupabase

ORG_A = "00000000-0000-4000-8000-00000000000a"
ORG_B = "00000000-0000-4000-8000-00000000000b"
ACC = "00000000-0000-4000-8000-0000000000a1"
ACC_META = "00000000-0000-4000-8000-0000000000a2"
ACC_B = "00000000-0000-4000-8000-0000000000b1"
MARCA = "00000000-0000-4000-8000-0000000000c1"
OTHER_MARCA = "00000000-0000-4000-8000-0000000000c2"
INSIGHTS_SCOPES = ["instagram_business_basic", "instagram_business_manage_insights"]

PATHS = [
    ("get", f"/api/instagram/accounts/{ACC}/profile"),
    ("get", f"/api/instagram/accounts/{ACC}/profile/trend"),
    ("get", f"/api/instagram/accounts/{ACC}/media"),
    ("get", f"/api/instagram/accounts/{ACC}/media/M1/insights/history"),
    ("post", f"/api/instagram/accounts/{ACC}/sync"),
]


def _acct(id_, org, provider="instagram", marca=MARCA, scopes=INSIGHTS_SCOPES, **kw):
    return {
        "id": id_, "org_id": org, "provider": provider, "status": "validated",
        "marca_id": marca, "account_label": "acme",
        "metadata": {"channel_id": "IGU", "channel_title": "acme", "scopes": scopes},
        "channel_info": {}, "last_synced_at": None, **kw,
    }


@pytest.fixture
def sb():
    s = FakeSupabase()
    s.tables["integration_accounts"] = [
        _acct(ACC, ORG_A),
        _acct(ACC_META, ORG_A, provider="meta"),
        _acct(ACC_B, ORG_B),
    ]
    return s


@pytest.fixture
def adapter():
    now = datetime.now(timezone.utc)
    return FakeInstagramLoginAdapter().seed(
        profile=IgProfile(id="APP", user_id="IGU", username="acme", name="Acme",
                          followers_count=1500, follows_count=12, media_count=2),
        media=[
            IgMediaItem(id="M1", media_type="VIDEO", media_product_type="REELS",
                        timestamp=now - timedelta(days=1), like_count=3, comments_count=1),
            IgMediaItem(id="M2", media_type="IMAGE", media_product_type="FEED",
                        timestamp=now - timedelta(days=2)),
        ],
        media_insights={"M1": {"views": 100, "reach": 80, "ig_reels_avg_watch_time": 3500}},
        user_insights={"reach": 10},
    )


@pytest.fixture
def client(sb, adapter):
    from app.main import app
    from app.modules.instagram.router import get_ig_adapter_builder, get_ig_repository

    app.dependency_overrides[get_ig_repository] = lambda: IgInsightsRepository(sb)
    app.dependency_overrides[get_ig_adapter_builder] = lambda: (lambda a, o: adapter)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _login(org=ORG_A):
    from app.dependencies import get_current_user_org
    from app.main import app

    app.dependency_overrides[get_current_user_org] = lambda: (object(), "tok", org)


def _seed_catalog(sb, rows):
    sb.tables["ig_media"] = [
        {"org_id": ORG_A, "account_id": ACC, "media_type": "IMAGE", "media_product_type": "FEED",
         "latest_metrics": None, "latest_snapshot_date": None, "synced_at": "2026-10-06T00:00:00+00:00",
         **r}
        for r in rows
    ]


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path", PATHS)
    def test_no_session_is_strict_401(self, client, method, path):
        assert getattr(client, method)(path).status_code == 401


class TestScoping:
    @pytest.mark.parametrize("method,path", PATHS)
    def test_other_orgs_account_is_404(self, client, method, path):
        _login(ORG_B)  # ACC belongs to ORG_A
        assert getattr(client, method)(path).status_code == 404

    def test_meta_provider_account_is_404(self, client):
        _login()
        assert client.get(f"/api/instagram/accounts/{ACC_META}/profile").status_code == 404

    def test_marca_pin(self, client):
        _login()
        assert client.get(f"/api/instagram/accounts/{ACC}/profile?marca_id={MARCA}").status_code == 200
        assert client.get(f"/api/instagram/accounts/{ACC}/profile?marca_id={OTHER_MARCA}").status_code == 404

    def test_malformed_account_id_is_400(self, client):
        _login()
        assert client.get("/api/instagram/accounts/not-a-uuid/profile").status_code == 400


class TestMediaGrid:
    def test_order_and_cursor_pagination(self, client, sb):
        _login()
        same = "2026-10-03T10:00:00+00:00"
        _seed_catalog(sb, [
            {"ig_media_id": "100", "published_at": "2026-10-01T10:00:00+00:00"},
            {"ig_media_id": "200", "published_at": same},
            {"ig_media_id": "300", "published_at": same},   # tie → id DESC
            {"ig_media_id": "400", "published_at": "2026-10-05T10:00:00+00:00"},
            {"ig_media_id": "500", "published_at": "2026-10-02T10:00:00+00:00"},
        ])
        # Another account's media must never leak in.
        sb.tables["ig_media"].append({"org_id": ORG_B, "account_id": ACC_B, "ig_media_id": "999",
                                      "published_at": "2026-10-09T00:00:00+00:00"})
        seen, cursor = [], None
        for _ in range(5):
            url = f"/api/instagram/accounts/{ACC}/media?limit=2" + (f"&cursor={cursor}" if cursor else "")
            body = client.get(url).json()
            seen += [i["id"] for i in body["items"]]
            cursor = body["next_cursor"]
            if not cursor:
                break
        assert seen == ["400", "300", "200", "500", "100"]

    def test_item_shape(self, client, sb):
        _login()
        _seed_catalog(sb, [{"ig_media_id": "1", "published_at": "2026-10-01T10:00:00+00:00",
                            "permalink": "https://instagram.com/p/x", "like_count": None,
                            "latest_metrics": {"views": 5, "saved": None}}])
        item = client.get(f"/api/instagram/accounts/{ACC}/media").json()["items"][0]
        assert item["id"] == "1" and item["timestamp"].startswith("2026-10-01T10:00:00")
        assert item["like_count"] is None  # hidden likes stay null
        assert item["latest"] == {"views": 5, "saved": None}

    def test_bad_cursor_is_400(self, client, sb):
        _login()
        _seed_catalog(sb, [])
        assert client.get(f"/api/instagram/accounts/{ACC}/media?cursor=%%%").status_code == 400

    def test_limit_bounds(self, client):
        _login()
        assert client.get(f"/api/instagram/accounts/{ACC}/media?limit=0").status_code == 422
        assert client.get(f"/api/instagram/accounts/{ACC}/media?limit=101").status_code == 422

    def test_cursor_roundtrip_is_opaque(self):
        from app.modules.instagram.repository import decode_cursor

        c = encode_cursor("2026-10-01T10:00:00+00:00", "17890")
        assert decode_cursor(c) == ("2026-10-01T10:00:00+00:00", "17890")


class TestSyncThenRead:
    def test_sync_then_profile_trend_media_history(self, client, sb):
        _login()
        r = client.post(f"/api/instagram/accounts/{ACC}/sync")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "done" and body["media_synced"] == 2 and body["snapshots_written"] == 2

        prof = client.get(f"/api/instagram/accounts/{ACC}/profile").json()
        assert prof["username"] == "acme" and prof["followers_count"] == 1500
        assert prof["last_synced_at"] is not None and prof["insights_scope_granted"] is True

        trend = client.get(f"/api/instagram/accounts/{ACC}/profile/trend?days=7").json()
        assert len(trend["points"]) == 1
        pt = trend["points"][0]
        assert pt["followers_count"] == 1500 and pt["reach"] == 10 and pt["views"] is None
        assert [m["key"] for m in trend["metrics"]][:3] == ["followers_count", "reach", "views"]

        grid = client.get(f"/api/instagram/accounts/{ACC}/media").json()
        assert [i["id"] for i in grid["items"]] == ["M1", "M2"]
        assert grid["items"][0]["latest"]["views"] == 100

        hist = client.get(f"/api/instagram/accounts/{ACC}/media/M1/insights/history").json()
        assert hist["media"]["id"] == "M1" and hist["media"]["media_product_type"] == "REELS"
        keys = [m["key"] for m in hist["metrics"]]
        assert keys[:3] == ["views", "reach", "ig_reels_avg_watch_time"]
        assert [m["priority"] for m in hist["metrics"]] == list(range(1, len(keys) + 1))
        fmt = {m["key"]: m["format"] for m in hist["metrics"]}
        assert fmt["ig_reels_avg_watch_time"] == "duration_ms" and fmt["reels_skip_rate"] == "percent"
        assert {m["key"]: m["label"] for m in hist["metrics"]}["views"] == "Visualizações"
        assert len(hist["points"]) == 1
        p = hist["points"][0]
        assert p["views"] == 100 and p["ig_reels_avg_watch_time"] == 3500 and p["likes"] is None
        assert set(p) == {"date", *keys}

        # Second sync same day → skipped (claim guard).
        assert client.post(f"/api/instagram/accounts/{ACC}/sync").json()["status"] == "skipped"

    def test_history_unknown_media_is_404(self, client, sb):
        _login()
        _seed_catalog(sb, [])
        assert client.get(f"/api/instagram/accounts/{ACC}/media/NOPE/insights/history").status_code == 404

    def test_profile_before_first_sync_is_nulls_not_zero(self, client):
        _login()
        prof = client.get(f"/api/instagram/accounts/{ACC}/profile").json()
        assert prof["username"] == "acme" and prof["followers_count"] is None


class TestSyncErrors:
    def test_missing_scope_is_409_requires_reconnect(self, client, sb):
        sb.tables["integration_accounts"][0]["metadata"]["scopes"] = [
            "instagram_business_basic", "instagram_business_manage_messages"]
        _login()
        r = client.post(f"/api/instagram/accounts/{ACC}/sync")
        assert r.status_code == 409
        assert r.json()["requires_reconnect"] is True
        assert r.json()["missing_scopes"] == ["instagram_business_manage_insights"]

    def test_graph_auth_error_is_structured_502(self, client, adapter):
        adapter.seed(user_insights_error=MetaGraphError("expired", code=190))
        _login()
        r = client.post(f"/api/instagram/accounts/{ACC}/sync")
        assert r.status_code == 502 and r.json()["code"] == 190

    def test_permission_error_is_requires_app_review(self, client, adapter):
        adapter.seed(user_insights_error=MetaGraphError("no advanced access", code=200))
        _login()
        r = client.post(f"/api/instagram/accounts/{ACC}/sync")
        assert r.status_code == 200 and r.json()["requires_app_review"] is True
