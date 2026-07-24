"""Tests for the Meta Ads console router (W3.2/W3.3) —
``/api/meta/ads/*``.

Coverage:
  - Auth boundary: strict ``== 401`` for every route with no session
    (never ``in (401, 404)`` — ``KB § PATTERNS/compliance/
    auth-boundary-false-green.md``)
  - Happy path per endpoint against a seeded ``FakeMetaAdapter`` +
    ``MockSupabaseClient``
  - Org-scoping: a session for org A never sees org B's persisted rows
  - 503 "not configured" when ``settings.meta_ad_account_id`` is empty

Adapter is injected via ``app.dependency_overrides`` on
``_resolve_ads_adapter`` (the router's own DI seam, mirroring
``get_account_adapter``'s override pattern in ``test_ig_insights.py`` —
``KB § PATTERNS/backend/di-test-seam.md``, Class-B) — auth-boundary
tests deliberately do NOT override it, so the real
``Depends(get_current_user_org)`` nested inside fires.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    Ad,
    AdAccount,
    AdCampaign,
    AdSet,
    FakeMetaAdapter,
    MetaGraphError,
)
from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock

from app.config import settings

_ORG_A = "00000000-0000-4000-8000-0000000000aa"
_ORG_B = "00000000-0000-4000-8000-0000000000bb"
_ACT_ID = "873947475957808"


# ─── Schema-caching client — same shape as test_ig_insights.py's
# _SchemaCachingClient (recurrence N=2 — flagged in the delivery footer
# as a candidate for a shared `noctusai_lib.testing` helper). ──────────
class _SchemaCachingClient:
    def __init__(self, root: MockSupabaseClient) -> None:
        self._root = root
        self._scoped: dict[str, Any] = {}

    def schema(self, name: str):
        if name not in self._scoped:
            self._scoped[name] = self._root.schema(name)
        return self._scoped[name]

    def __getattr__(self, item):
        return getattr(self._root, item)


def _account() -> AdAccount:
    return AdAccount(
        id=_ACT_ID, name="One Consultoria", currency="BRL",
        timezone_name="America/Sao_Paulo",
        amount_spent="674426", balance="12519", spend_cap="50000000",
        account_status=1,
    )


def _campaign(cid: str = "camp_1") -> AdCampaign:
    return AdCampaign(
        id=cid, name="SENSEYS", objective="OUTCOME_LEADS",
        status="ACTIVE", effective_status="ACTIVE",
    )


def _adset(aid: str = "adset_1", campaign_id: str = "camp_1") -> AdSet:
    return AdSet(
        id=aid, name="Adset 1", status="ACTIVE", effective_status="ACTIVE",
        campaign_id=campaign_id, daily_budget=5000,
    )


def _ad(ad_id: str = "ad_1", adset_id: str = "adset_1") -> Ad:
    return Ad(
        id=ad_id, name="Ad 1", status="ACTIVE", effective_status="ACTIVE",
        adset_id=adset_id, creative_id="creative_1",
    )


def _seeded_adapter() -> FakeMetaAdapter:
    adapter = FakeMetaAdapter()
    acct = f"act_{_ACT_ID}"
    adapter.seed(
        ad_accounts=[_account()],
        ad_campaigns_by_account={acct: [_campaign()]},
        ad_sets_by_account={acct: [_adset()]},
        ads_by_account={acct: [_ad()]},
    )
    return adapter


@pytest.fixture(autouse=True)
def _configure_ad_account():
    original = settings.meta_ad_account_id
    settings.meta_ad_account_id = _ACT_ID  # self-patch-ok: test config, not a guard
    yield
    settings.meta_ad_account_id = original


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    from app.main import app

    app.dependency_overrides.clear()


@pytest.fixture
def client():
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
        yield tc, mock_sb, caching


def _override_adapter(org_id: str, adapter: FakeMetaAdapter) -> None:
    from app.main import app
    from app.modules.meta_ads.routers.ads_router import _resolve_ads_adapter

    app.dependency_overrides[_resolve_ads_adapter] = lambda: (org_id, adapter)


def _override_session_org(org_id: str) -> None:
    from app.dependencies import get_current_user_org
    from app.main import app

    app.dependency_overrides[get_current_user_org] = lambda: (
        object(), "test-token", org_id,
    )


# ─── Auth boundary — strict 401, never overridden ─────────────────────
class TestAuthBoundary:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/meta/ads/accounts",
            "/api/meta/ads/campaigns",
            "/api/meta/ads/campaigns/camp_1/children?level=adset",
            "/api/meta/ads/insights/series?object_id=camp_1&level=campaign&since=2026-07-01&until=2026-07-02",
            "/api/meta/ads/insights/compare?object_id=camp_1&level=campaign&since=2026-07-01&until=2026-07-02",
            "/api/meta/ads/insights/account?since=2026-07-01&until=2026-07-02",
            "/api/meta/ads/activities?since=2026-07-01&until=2026-07-02",
        ],
    )
    def test_no_session_returns_strict_401(self, client, path):
        tc, _mock_sb, _caching = client
        resp = tc.get(path)
        assert resp.status_code == 401, resp.text

    def test_sync_no_session_returns_strict_401(self, client):
        tc, _mock_sb, _caching = client
        resp = tc.post("/api/meta/ads/sync", json={"mode": "incremental"})
        assert resp.status_code == 401, resp.text


# ─── GET /accounts ────────────────────────────────────────────────────
class TestListAccounts:
    def test_returns_cents_shape(self, client):
        tc, _mock_sb, _caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        resp = tc.get("/api/meta/ads/accounts")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["act_id"] == _ACT_ID
        assert data[0]["amount_spent_cents"] == 674426
        assert data[0]["currency"] == "BRL"

    def test_meta_graph_error_maps_to_uniform_gate(self, client):
        """A `MetaGraphError` from the adapter must never surface as a
        raw unhandled 500 — the shared `handle_meta_graph_error` gate
        maps it to a structured 200 (`requires_app_review`/
        `requires_setup`) or a structured 502, per
        `app.routers._meta_common`."""
        tc, _mock_sb, _caching = client

        class _Raising(FakeMetaAdapter):
            def list_ad_accounts(self):
                raise MetaGraphError(
                    "simulated graph failure", code=1, http_status=400,
                )

        _override_adapter(_ORG_A, _Raising())

        resp = tc.get("/api/meta/ads/accounts")
        assert resp.status_code in (200, 502), resp.text


# ─── GET /campaigns ───────────────────────────────────────────────────
class TestListCampaigns:
    def test_returns_campaigns_with_latest_none_when_no_snapshot(self, client):
        tc, mock_sb, caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        caching.schema("social_wiring").set_table_data("ads_insight_snapshots", [])

        resp = tc.get("/api/meta/ads/campaigns")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["object_id"] == "camp_1"
        assert data[0]["latest"] is None

    def test_returns_latest_snapshot_when_present(self, client):
        tc, mock_sb, caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        caching.schema("social_wiring").set_table_data(
            "ads_insight_snapshots",
            [
                {
                    "org_id": _ORG_A,
                    "object_id": "camp_1", "date": "2026-07-01",
                    "spend_cents": 38050, "impressions": 1000,
                    "clicks": 42, "reach": 800,
                    "actions": {"lead": 12.0},
                }
            ],
        )

        resp = tc.get("/api/meta/ads/campaigns")
        assert resp.status_code == 200, resp.text
        latest = resp.json()["data"][0]["latest"]
        assert latest["spend_cents"] == 38050
        assert latest["leads"] == 12.0

    def test_status_filter(self, client):
        tc, _mock_sb, caching = client
        adapter = FakeMetaAdapter()
        acct = f"act_{_ACT_ID}"
        adapter.seed(
            ad_campaigns_by_account={
                acct: [
                    _campaign("camp_active"),
                    AdCampaign(id="camp_paused", status="PAUSED", effective_status="PAUSED"),
                ]
            }
        )
        _override_adapter(_ORG_A, adapter)
        caching.schema("social_wiring").set_table_data("ads_insight_snapshots", [])

        resp = tc.get("/api/meta/ads/campaigns?status=PAUSED")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert [c["object_id"] for c in data] == ["camp_paused"]

    def test_not_configured_returns_503(self, client):
        tc, _mock_sb, _caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        settings.meta_ad_account_id = ""  # self-patch-ok: test config gap
        resp = tc.get("/api/meta/ads/campaigns")
        assert resp.status_code == 503, resp.text


# ─── GET /insights/account ────────────────────────────────────────────
class TestAccountInsights:
    def test_sums_campaigns_server_side(self, client):
        tc, _mock_sb, caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        # Two campaigns, overlapping day 07-01 + camp_1 also on 07-02.
        caching.schema("social_wiring").set_table_data(
            "ads_insight_snapshots",
            [
                {"org_id": _ORG_A, "object_id": "camp_1", "level": "campaign",
                 "date": "2026-07-01", "breakdown_key": None,
                 "spend_cents": 10000, "impressions": 500, "reach": 400,
                 "clicks": 20, "actions": {"lead": 5.0, "link_click": 15.0}},
                {"org_id": _ORG_A, "object_id": "camp_2", "level": "campaign",
                 "date": "2026-07-01", "breakdown_key": None,
                 "spend_cents": 5000, "impressions": 250, "reach": 200,
                 "clicks": 10, "actions": {"lead": 3.0}},
                {"org_id": _ORG_A, "object_id": "camp_1", "level": "campaign",
                 "date": "2026-07-02", "breakdown_key": None,
                 "spend_cents": 8000, "impressions": 300, "reach": 250,
                 "clicks": 12, "actions": {"lead": 4.0}},
            ],
        )

        resp = tc.get("/api/meta/ads/insights/account?since=2026-07-01&until=2026-07-02")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Totals summed across both campaigns + both days.
        assert body["totals"]["spend_cents"] == 23000
        assert body["totals"]["leads"] == 12.0
        assert body["actions"]["lead"] == 12.0
        assert body["actions"]["link_click"] == 15.0
        # Daily series merged by date: 07-01 sums camp_1 + camp_2.
        by_date = {d["date"]: d for d in body["daily"]}
        assert by_date["2026-07-01"]["spend_cents"] == 15000
        assert by_date["2026-07-01"]["leads"] == 8.0
        assert by_date["2026-07-02"]["spend_cents"] == 8000

    def test_empty_is_zeros_not_error(self, client):
        tc, _mock_sb, caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        caching.schema("social_wiring").set_table_data("ads_insight_snapshots", [])
        resp = tc.get("/api/meta/ads/insights/account?since=2026-07-01&until=2026-07-02")
        assert resp.status_code == 200, resp.text
        assert resp.json()["totals"]["spend_cents"] == 0
        assert resp.json()["daily"] == []


# ─── GET /campaigns/{id}/children ─────────────────────────────────────
class TestListChildren:
    def test_adset_level(self, client):
        tc, _mock_sb, _caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        resp = tc.get("/api/meta/ads/campaigns/camp_1/children?level=adset")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data[0]["object_id"] == "adset_1"
        assert data[0]["level"] == "adset"
        assert data[0]["daily_budget_cents"] == 5000

    def test_ad_level(self, client):
        tc, _mock_sb, _caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        resp = tc.get("/api/meta/ads/campaigns/adset_1/children?level=ad")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data[0]["object_id"] == "ad_1"
        assert data[0]["creative_id"] == "creative_1"


# ─── GET /insights/series ─────────────────────────────────────────────
class TestInsightsSeries:
    def test_campaign_level_reads_persisted_snapshots(self, client):
        tc, _mock_sb, caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        caching.schema("social_wiring").set_table_data(
            "ads_insight_snapshots",
            [
                {
                    "org_id": _ORG_A,
                    "object_id": "camp_1", "date": "2026-07-01",
                    "breakdown_key": None,
                    "spend_cents": 38050, "impressions": 1000, "reach": 800,
                    "clicks": 42, "cpc_cents": 906, "cpm_cents": 38050,
                    "ctr": 4.2, "actions": {"lead": 12.0}, "action_values": {},
                }
            ],
        )
        resp = tc.get(
            "/api/meta/ads/insights/series"
            "?object_id=camp_1&level=campaign&since=2026-07-01&until=2026-07-01"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["object_id"] == "camp_1"
        assert len(body["rows"]) == 1
        assert body["rows"][0]["spend_cents"] == 38050
        assert body["rows"][0]["actions"] == {"lead": 12.0}

    def test_adset_level_reads_live_from_adapter(self, client):
        from noctusai_lib.integrations.meta import AdInsightsRow, AdInsightsSeries

        tc, _mock_sb, _caching = client
        adapter = _seeded_adapter()
        adapter.seed(
            ad_insights_series={
                "adset_1": AdInsightsSeries(
                    object_id="adset_1", level="adset",
                    rows=[
                        AdInsightsRow(
                            date_start="2026-07-01",
                            metrics={"spend": 100.0, "impressions": 500.0},
                            actions={"lead": 3.0},
                        )
                    ],
                )
            }
        )
        _override_adapter(_ORG_A, adapter)

        resp = tc.get(
            "/api/meta/ads/insights/series"
            "?object_id=adset_1&level=adset&since=2026-07-01&until=2026-07-01"
        )
        assert resp.status_code == 200, resp.text
        row = resp.json()["rows"][0]
        assert row["spend_cents"] == 10000
        assert row["actions"] == {"lead": 3.0}


# ─── GET /activities ──────────────────────────────────────────────────
class TestListActivities:
    def test_reads_persisted_events(self, client):
        tc, _mock_sb, caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        caching.schema("social_wiring").set_table_data(
            "ads_activity_events",
            [
                {
                    "org_id": _ORG_A,
                    "object_id": "camp_1", "object_level": "campaign",
                    "event_type": "update_ad_run_status",
                    "occurred_at": "2026-07-01T12:00:00+00:00",
                    "actor_name": "Leonardo Salomão",
                    "old_value": "PAUSED", "new_value": "ACTIVE",
                }
            ],
        )
        resp = tc.get(
            "/api/meta/ads/activities?since=2026-07-01&until=2026-07-02"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["event_type"] == "update_ad_run_status"
        assert data[0]["new_value"] == "ACTIVE"


# ─── Org scoping ──────────────────────────────────────────────────────
class TestOrgScoping:
    def test_org_a_session_never_sees_org_b_activity_rows(self, client):
        """A session authenticated for org A must not see org B's
        persisted activity rows even though both exist in the same
        (mocked) table."""
        tc, _mock_sb, caching = client
        _override_session_org(_ORG_A)
        caching.schema("social_wiring").set_table_data(
            "ads_activity_events",
            [
                {
                    "org_id": _ORG_B, "object_id": "camp_b",
                    "object_level": "campaign", "event_type": "update",
                    "occurred_at": "2026-07-01T12:00:00+00:00",
                    "actor_name": "Org B Actor",
                    "old_value": None, "new_value": None,
                },
                {
                    "org_id": _ORG_A, "object_id": "camp_a",
                    "object_level": "campaign", "event_type": "update",
                    "occurred_at": "2026-07-01T12:00:00+00:00",
                    "actor_name": "Org A Actor",
                    "old_value": None, "new_value": None,
                },
            ],
        )
        resp = tc.get(
            "/api/meta/ads/activities?since=2026-07-01&until=2026-07-02"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["object_id"] == "camp_a"


# ─── POST /sync · GET /sync/{job_id} ──────────────────────────────────
class TestSync:
    def test_start_sync_returns_202_with_job_id(self, client):
        tc, _mock_sb, _caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        resp = tc.post("/api/meta/ads/sync", json={"mode": "incremental"})
        assert resp.status_code == 202, resp.text
        assert "job_id" in resp.json()

    def test_sync_status_unknown_job_returns_404(self, client):
        tc, _mock_sb, _caching = client
        resp = tc.get("/api/meta/ads/sync/does-not-exist")
        assert resp.status_code == 404, resp.text

    def test_sync_status_reachable_after_start(self, client):
        tc, _mock_sb, _caching = client
        _override_adapter(_ORG_A, _seeded_adapter())
        started = tc.post("/api/meta/ads/sync", json={"mode": "incremental"})
        job_id = started.json()["job_id"]
        resp = tc.get(f"/api/meta/ads/sync/{job_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] in ("running", "done", "error")
