"""Mocked test suite for the Meta **ads-read** surface completion (W1 of
the Meta Ads console roadmap — `project-history/roadmaps/
meta-ads-console-2026-07.md`).

Mirrors `test_meta_ads_management.py`'s structure/idiom, applied to the
READ side of the ads Graph:

- `list_ad_accounts` — the missing `ad_account_id` discovery path.
- `list_ad_sets` / `list_ads` — the missing campaign→adset→ad READ
  hierarchy (only writes existed before).
- `ad_insights_series` — the multi-row, `actions`/`action_values`-aware
  sibling of `ad_insights` (which only ever surfaced the first row and
  silently dropped conversion metrics — see the regression test below).
- `list_activities` — the ad-account change log (intra-day status-flip
  history a daily insights snapshot cannot see).

External boundary only is mocked: `httpx.get` is patched (the real
external Graph endpoint — sanctioned per CLAUDE.md "external
integrations OK"). No `noctusai_lib` code is monkey-patched; the
adapter, mappers and factory run for real against canned bodies.

**Mock-only.** `ads_read` is not yet granted for this app (roadmap
trigger T1, pending an operator action in Business Manager) — nothing
here is exercised against a live token. Every "real adapter" test below
mocks `httpx.get`, matching the sibling IG-DM initiative's S1 posture.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from noctusai_lib.integrations.meta import (
    Ad,
    AdAccount,
    AdActivity,
    AdInsightsRow,
    AdInsightsSeries,
    AdSet,
    FakeMetaAdapter,
    MetaGraphError,
    get_meta_adapter,
)
from noctusai_lib.integrations.meta.mappers import (
    ad_account_from_body,
    ad_activity_from_body,
    ad_from_body,
    ad_insights_row_from_body,
    ad_set_from_body,
)
from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter


# ─── Test transport helper (mirrors test_meta_ads_management.py) ──────────


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


_PERM_ERR = {
    "error": {
        "message": "(#200) ads_read permission required",
        "code": 200,
        "type": "OAuthException",
    }
}


# ─── TestAdsReadTypes ──────────────────────────────────────────────────────


class TestAdsReadTypes:
    """The new value objects (safety: frozen; defaults sane)."""

    def test_value_objects_are_frozen(self):
        with pytest.raises(Exception):
            AdAccount(id="1").id = "mutated"
        with pytest.raises(Exception):
            AdActivity(id="a1").id = "mutated"
        with pytest.raises(Exception):
            AdInsightsRow().date_start = "mutated"
        with pytest.raises(Exception):
            AdInsightsSeries(object_id="1", level="campaign").object_id = "x"

    def test_ad_account_defaults(self):
        acct = AdAccount(id="123")
        assert acct.name is None
        assert acct.account_status is None

    def test_ad_insights_row_defaults_are_independent_dicts(self):
        row1 = AdInsightsRow()
        row2 = AdInsightsRow()
        row1.metrics["x"] = 1.0
        assert row2.metrics == {}
        assert row1.actions == {} and row1.action_values == {}

    def test_ad_gained_creative_thumbnail_fields_with_safe_defaults(self):
        # Extended for the read surface (list_ads); the ads-management
        # write surface (create_ad) never sets these — must default
        # safely so it stays back-compat.
        ad = Ad(id="ad1")
        assert ad.creative_thumbnail_url is None
        assert ad.creative_object_story_spec == {}


# ─── TestMappersAdsRead (pure functions, no adapter needed) ───────────────


class TestMappersAdsRead:
    def test_ad_account_from_body_strips_act_prefix(self):
        acct = ad_account_from_body({
            "id": "act_123456",
            "name": "Acct",
            "currency": "BRL",
            "timezone_name": "America/Sao_Paulo",
            "amount_spent": "50000",
            "balance": "0",
            "spend_cap": "0",
            "account_status": 1,
        })
        assert acct.id == "123456"  # bare — act_ prefix stripped
        assert acct.currency == "BRL"
        assert acct.amount_spent == "50000"  # kept as raw string
        assert acct.account_status == 1

    def test_ad_account_from_body_tolerates_missing_prefix(self):
        # Defensive: if Graph ever returns a bare id, don't mangle it.
        acct = ad_account_from_body({"id": "999"})
        assert acct.id == "999"

    def test_ad_set_from_body_parses_budget_as_int(self):
        ad_set = ad_set_from_body({
            "id": "adset1",
            "name": "Set1",
            "status": "ACTIVE",
            "campaign_id": "camp1",
            "daily_budget": "5000",
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "REACH",
            "targeting": {"geo_locations": {"countries": ["BR"]}},
        })
        assert ad_set.daily_budget == 5000
        assert isinstance(ad_set.daily_budget, int)
        assert ad_set.targeting == {"geo_locations": {"countries": ["BR"]}}

    def test_ad_set_from_body_missing_budget_is_none_not_zero(self):
        ad_set = ad_set_from_body({"id": "adset1"})
        assert ad_set.daily_budget is None  # never a silent 0

    def test_ad_from_body_extracts_nested_creative(self):
        ad = ad_from_body({
            "id": "ad1",
            "name": "Ad One",
            "status": "ACTIVE",
            "effective_status": "ACTIVE",
            "adset_id": "adset1",
            "creative": {
                "id": "cr1",
                "thumbnail_url": "https://thumb/1.jpg",
                "object_story_spec": {"page_id": "P1"},
            },
        })
        assert ad.creative_id == "cr1"
        assert ad.creative_thumbnail_url == "https://thumb/1.jpg"
        assert ad.creative_object_story_spec == {"page_id": "P1"}

    def test_ad_from_body_tolerates_missing_creative(self):
        ad = ad_from_body({"id": "ad1", "adset_id": "adset1"})
        assert ad.creative_id is None
        assert ad.creative_thumbnail_url is None
        assert ad.creative_object_story_spec == {}

    # ── The gap #4 regression: actions/action_values parsing ──────────

    def test_ad_insights_row_from_body_parses_actions_and_action_values(self):
        row = ad_insights_row_from_body({
            "date_start": "2026-07-01",
            "date_stop": "2026-07-01",
            "impressions": "1000",
            "spend": "12.50",
            "actions": [
                {"action_type": "onsite_conversion.purchase", "value": "3"},
                {"action_type": "link_click", "value": "42"},
            ],
            "action_values": [
                {"action_type": "onsite_conversion.purchase", "value": "150.00"},
            ],
        })
        # Plain numeric fields still flatten as before.
        assert row.metrics["impressions"] == 1000.0
        assert row.metrics["spend"] == 12.5
        # THE fix: conversion metrics survive into typed maps, keyed by
        # action_type — the old flatten dropped these two keys
        # ENTIRELY (a bare `float(<list>)` always raises and was
        # silently `continue`d past).
        assert row.actions["onsite_conversion.purchase"] == 3.0
        assert row.actions["link_click"] == 42.0
        assert row.action_values["onsite_conversion.purchase"] == 150.0
        # actions/action_values must NOT also leak into `metrics`.
        assert "actions" not in row.metrics
        assert "action_values" not in row.metrics

    def test_ad_insights_row_from_body_separates_breakdown_keys(self):
        row = ad_insights_row_from_body(
            {
                "date_start": "2026-07-01",
                "publisher_platform": "instagram",
                "impressions": "500",
            },
            breakdown_keys=["publisher_platform"],
        )
        assert row.breakdown == {"publisher_platform": "instagram"}
        # The breakdown dimension value ("instagram") must not also be
        # coerced into `metrics` (it isn't numeric anyway, but the
        # exclusion is explicit, not accidental).
        assert "publisher_platform" not in row.metrics

    def test_ad_insights_row_from_body_no_breakdowns_default_empty(self):
        row = ad_insights_row_from_body({"impressions": "1"})
        assert row.breakdown == {}

    def test_ad_insights_row_from_body_preserves_raw(self):
        body = {"impressions": "1", "actions": [{"action_type": "x", "value": "1"}]}
        row = ad_insights_row_from_body(body)
        assert row.raw == body

    # ── AdActivity mapping ─────────────────────────────────────────────

    def test_ad_activity_from_body_parses_timestamp_and_extra_data(self):
        activity = ad_activity_from_body({
            "event_type": "update_campaign_group_run_status",
            "event_time": "2026-07-21T09:00:00+0000",
            "object_id": "camp1",
            "object_type": "campaign",
            "actor_id": "u1",
            "actor_name": "Operator",
            "extra_data": json.dumps({"old_value": "PAUSED", "new_value": "ACTIVE"}),
        })
        assert activity.object_level == "campaign"
        assert activity.old_value == "PAUSED"
        assert activity.new_value == "ACTIVE"
        assert activity.occurred_at == datetime(2026, 7, 21, 9, 0, 0, tzinfo=timezone.utc)
        assert activity.occurred_at.tzinfo is not None

    def test_ad_activity_from_body_synthesizes_id_when_absent(self):
        # Graph's Activities edge does not return a stable per-row id
        # (it's an audit log, not a Graph node) — the mapper
        # synthesizes a composite key instead of leaving it blank.
        activity = ad_activity_from_body({
            "event_type": "update_campaign_group_run_status",
            "event_time": "2026-07-21T09:00:00+0000",
            "object_id": "camp1",
        })
        assert activity.id == "camp1:2026-07-21T09:00:00+0000:update_campaign_group_run_status"

    def test_ad_activity_from_body_uses_graph_id_when_present(self):
        activity = ad_activity_from_body({"id": "native123", "object_id": "camp1"})
        assert activity.id == "native123"

    def test_ad_activity_from_body_tolerates_non_json_extra_data(self):
        activity = ad_activity_from_body({
            "object_id": "camp1",
            "extra_data": "not-json",
        })
        assert activity.old_value is None
        assert activity.new_value is None

    def test_ad_activity_from_body_no_before_after_leaves_values_none_raw_kept(self):
        # Not every event type carries an old/new pair — those fields
        # stay None, but the raw payload is never lost.
        body = {
            "event_type": "create_ad",
            "object_id": "ad1",
            "extra_data": json.dumps({"something_else": "x"}),
        }
        activity = ad_activity_from_body(body)
        assert activity.old_value is None
        assert activity.new_value is None
        assert activity.raw == body


# ─── TestFakeAdsReadGraph ──────────────────────────────────────────────────


class TestFakeAdsReadGraph:
    """Deterministic in-memory read surface — the 'scope approved' path
    that lets MCP/consumer tests exercise the real handler with no
    network. The Fake NEVER raises the App-Review gate — that lives on
    the live adapter only."""

    def test_list_ad_accounts_returns_seeded(self):
        fake = FakeMetaAdapter()
        fake.seed(ad_accounts=[AdAccount(id="1", name="Acct1")])
        assert fake.list_ad_accounts() == [AdAccount(id="1", name="Acct1")]

    def test_list_ad_sets_filters_by_campaign_id(self):
        fake = FakeMetaAdapter()
        s1 = AdSet(id="s1", campaign_id="c1")
        s2 = AdSet(id="s2", campaign_id="c2")
        fake.seed(ad_sets_by_account={"act_1": [s1, s2]})
        assert fake.list_ad_sets("act_1") == [s1, s2]
        assert fake.list_ad_sets("act_1", campaign_id="c1") == [s1]
        assert fake.list_ad_sets("1", campaign_id="c2") == [s2]  # bare id also resolves

    def test_list_ads_filters_by_adset_id(self):
        fake = FakeMetaAdapter()
        a1 = Ad(id="a1", adset_id="s1")
        a2 = Ad(id="a2", adset_id="s2")
        fake.seed(ads_by_account={"act_1": [a1, a2]})
        assert fake.list_ads("act_1") == [a1, a2]
        assert fake.list_ads("act_1", adset_id="s2") == [a2]

    def test_ad_insights_series_multi_row_seeded(self):
        # The multi-row fixture — exercises real pagination/series
        # shape on the consumer side, not a single row.
        fake = FakeMetaAdapter()
        rows = [
            AdInsightsRow(date_start=f"2026-07-0{i}", metrics={"impressions": float(i)})
            for i in range(1, 6)
        ]
        series = AdInsightsSeries(object_id="ad_1", level="ad", rows=rows)
        fake.seed(ad_insights_series={"ad_1": series})
        out = fake.ad_insights_series("ad_1", "ad")
        assert len(out.rows) == 5
        assert out.rows[0].date_start == "2026-07-01"
        assert out.rows[-1].metrics["impressions"] == 5.0

    def test_list_activities_activate_pause_reactivate_same_day(self):
        # THE fixture that's the entire reason the change log exists:
        # an operator flips a campaign on/off multiple times within one
        # calendar day — invisible to any daily insights snapshot.
        fake = FakeMetaAdapter()
        seq = [
            AdActivity(
                id="a1", object_id="camp1", object_level="campaign",
                event_type="update_campaign_group_run_status",
                occurred_at=datetime(2026, 7, 21, 9, 0, 0, tzinfo=timezone.utc),
                old_value="PAUSED", new_value="ACTIVE",
            ),
            AdActivity(
                id="a2", object_id="camp1", object_level="campaign",
                event_type="update_campaign_group_run_status",
                occurred_at=datetime(2026, 7, 21, 13, 0, 0, tzinfo=timezone.utc),
                old_value="ACTIVE", new_value="PAUSED",
            ),
            AdActivity(
                id="a3", object_id="camp1", object_level="campaign",
                event_type="update_campaign_group_run_status",
                occurred_at=datetime(2026, 7, 21, 17, 0, 0, tzinfo=timezone.utc),
                old_value="PAUSED", new_value="ACTIVE",
            ),
        ]
        fake.seed(activities_by_account={"act_1": seq})
        out = fake.list_activities("act_1", since=0, until=1)
        # Ordering preserved exactly as seeded.
        assert [a.new_value for a in out] == ["ACTIVE", "PAUSED", "ACTIVE"]
        # Distinct timestamps, all tz-aware, all the same calendar day.
        assert len({a.occurred_at for a in out}) == 3
        assert all(a.occurred_at.tzinfo is not None for a in out)
        assert len({a.occurred_at.date() for a in out}) == 1

    def test_fake_never_raises_app_review_gate_for_reads(self):
        fake = FakeMetaAdapter()
        fake.seed(ad_accounts=[AdAccount(id="1")])
        accounts = fake.list_ad_accounts()  # would raise on live adapter if scope absent
        assert accounts == [AdAccount(id="1")]


# ─── TestRealAdsReadGraph ──────────────────────────────────────────────────


class TestRealAdsReadGraph:
    """The live adapter ads-read paths — external Graph boundary mocked
    (`httpx.get` patched; no `noctusai_lib` code monkey-patched)."""

    def _adapter(self):
        return MetaOAuthAdapter(system_user_token="SYSTOK")

    def test_list_ad_accounts_real_strips_act_prefix(self):
        a = self._adapter()
        body = {
            "data": [{
                "id": "act_123456", "name": "Acct", "currency": "BRL",
                "timezone_name": "America/Sao_Paulo", "amount_spent": "50000",
                "balance": "0", "spend_cap": "0", "account_status": 1,
            }],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            accounts = a.list_ad_accounts()
        assert len(accounts) == 1
        assert accounts[0].id == "123456"  # bare, act_ prefix stripped
        assert accounts[0].currency == "BRL"
        assert accounts[0].account_status == 1

    def test_list_ad_sets_real_parses_budget_and_targeting(self):
        a = self._adapter()
        body = {
            "data": [{
                "id": "adset1", "name": "Set1", "status": "ACTIVE",
                "campaign_id": "camp1", "daily_budget": "5000",
                "billing_event": "IMPRESSIONS", "optimization_goal": "REACH",
                "targeting": {"geo_locations": {"countries": ["BR"]}},
            }],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            sets = a.list_ad_sets("123", campaign_id="camp1")
        assert sets[0].daily_budget == 5000
        assert isinstance(sets[0].daily_budget, int)
        assert sets[0].targeting == {"geo_locations": {"countries": ["BR"]}}

    def test_list_ad_sets_filters_server_side_via_filtering_param(self):
        a = self._adapter()
        captured: dict = {}

        def _get(url, params=None, **kwargs):
            captured["params"] = params
            return _FakeResponse({"data": [], "paging": {}})

        with patch.object(httpx, "get", side_effect=_get):
            a.list_ad_sets("123", campaign_id="camp1")
        assert "filtering" in captured["params"]
        filt = json.loads(captured["params"]["filtering"])
        assert filt == [{"field": "campaign.id", "operator": "EQUAL", "value": "camp1"}]

    def test_list_ads_real_with_creative_expansion(self):
        a = self._adapter()
        body = {
            "data": [{
                "id": "ad1", "name": "Ad One", "status": "ACTIVE",
                "effective_status": "ACTIVE", "adset_id": "adset1",
                "creative": {
                    "id": "cr1", "thumbnail_url": "https://thumb/1.jpg",
                    "object_story_spec": {"page_id": "P1"},
                },
            }],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            ads = a.list_ads("123", adset_id="adset1")
        assert len(ads) == 1
        assert ads[0].creative_id == "cr1"
        assert ads[0].creative_thumbnail_url == "https://thumb/1.jpg"
        assert ads[0].creative_object_story_spec == {"page_id": "P1"}

    def test_list_ads_filters_server_side_via_filtering_param(self):
        a = self._adapter()
        captured: dict = {}

        def _get(url, params=None, **kwargs):
            captured["params"] = params
            return _FakeResponse({"data": [], "paging": {}})

        with patch.object(httpx, "get", side_effect=_get):
            a.list_ads("123", adset_id="adset1")
        assert "filtering" in captured["params"]
        filt = json.loads(captured["params"]["filtering"])
        assert filt == [{"field": "adset.id", "operator": "EQUAL", "value": "adset1"}]

    # ── ad_insights_series: multi-row, pagination, actions parsing ────

    def test_ad_insights_series_multi_row_n_in_n_out(self):
        a = self._adapter()
        body = {
            "data": [
                {"date_start": "2026-07-01", "date_stop": "2026-07-01", "impressions": "1"},
                {"date_start": "2026-07-02", "date_stop": "2026-07-02", "impressions": "2"},
                {"date_start": "2026-07-03", "date_stop": "2026-07-03", "impressions": "3"},
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            series = a.ad_insights_series("123", "ad", time_increment=1)
        # N rows in, N rows out — the direct fix for gap #4's rows[0]-only read.
        assert len(series.rows) == 3
        assert [r.date_start for r in series.rows] == [
            "2026-07-01", "2026-07-02", "2026-07-03",
        ]

    def test_ad_insights_series_paginates_across_next_cursor(self):
        a = self._adapter()
        page1 = {
            "data": [
                {"date_start": "2026-07-01", "date_stop": "2026-07-01", "impressions": "100"},
                {"date_start": "2026-07-02", "date_stop": "2026-07-02", "impressions": "200"},
            ],
            "paging": {"next": "https://graph.facebook.com/v22.0/123/insights?after=CURSOR1"},
        }
        page2 = {
            "data": [
                {"date_start": "2026-07-03", "date_stop": "2026-07-03", "impressions": "300"},
            ],
            "paging": {},
        }
        with patch.object(
            httpx, "get", side_effect=[_FakeResponse(page1), _FakeResponse(page2)]
        ):
            series = a.ad_insights_series("123", "ad", time_increment=1)
        assert len(series.rows) == 3
        assert [r.date_start for r in series.rows] == [
            "2026-07-01", "2026-07-02", "2026-07-03",
        ]
        assert series.rows[2].metrics["impressions"] == 300.0

    def test_ad_insights_series_parses_actions_where_ad_insights_drops_them(self):
        # THE regression test for gap #4. Same payload fed to both
        # methods: the new `ad_insights_series` must surface the
        # conversion metrics; the OLD `ad_insights` (kept as-is,
        # unmodified, for back-compat) demonstrably still drops them
        # — proving the gap existed and that the fix lives in the NEW
        # method rather than a shared code path silently patched.
        a = self._adapter()
        row = {
            "date_start": "2026-07-01",
            "date_stop": "2026-07-01",
            "impressions": "1000",
            "spend": "12.50",
            "actions": [
                {"action_type": "onsite_conversion.purchase", "value": "3"},
            ],
            "action_values": [
                {"action_type": "onsite_conversion.purchase", "value": "150.00"},
            ],
        }
        body = {"data": [row], "paging": {}}

        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            series = a.ad_insights_series("123", "campaign")
        assert len(series.rows) == 1
        r = series.rows[0]
        assert r.metrics["impressions"] == 1000.0
        assert r.actions["onsite_conversion.purchase"] == 3.0
        assert r.action_values["onsite_conversion.purchase"] == 150.0

        # The pre-existing method, same exact payload: the conversion
        # keys never survive its naive float() flatten.
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            old = a.ad_insights("123", "campaign")
        assert old.metrics["impressions"] == 1000.0
        assert "actions" not in old.metrics
        assert "action_values" not in old.metrics

    def test_ad_insights_series_time_range_and_breakdowns_encoded(self):
        a = self._adapter()
        captured: dict = {}

        def _get(url, params=None, **kwargs):
            captured["params"] = params
            return _FakeResponse({"data": [], "paging": {}})

        with patch.object(httpx, "get", side_effect=_get):
            a.ad_insights_series(
                "123",
                "ad",
                time_range=(date(2026, 1, 1), date(2026, 12, 31)),
                breakdowns=["publisher_platform"],
                action_attribution_windows=["7d_click", "1d_view"],
            )
        params = captured["params"]
        assert json.loads(params["time_range"]) == {
            "since": "2026-01-01", "until": "2026-12-31",
        }
        assert params["breakdowns"] == "publisher_platform"
        assert json.loads(params["action_attribution_windows"]) == [
            "7d_click", "1d_view",
        ]

    # ── list_activities ─────────────────────────────────────────────

    def test_list_activities_real_activate_pause_reactivate_same_day(self):
        a = self._adapter()
        body = {
            "data": [
                {
                    "event_type": "update_campaign_group_run_status",
                    "event_time": "2026-07-21T09:00:00+0000",
                    "object_id": "camp1", "object_type": "campaign",
                    "actor_id": "u1", "actor_name": "Op",
                    "extra_data": json.dumps({"old_value": "PAUSED", "new_value": "ACTIVE"}),
                },
                {
                    "event_type": "update_campaign_group_run_status",
                    "event_time": "2026-07-21T13:00:00+0000",
                    "object_id": "camp1", "object_type": "campaign",
                    "actor_id": "u1", "actor_name": "Op",
                    "extra_data": json.dumps({"old_value": "ACTIVE", "new_value": "PAUSED"}),
                },
                {
                    "event_type": "update_campaign_group_run_status",
                    "event_time": "2026-07-21T17:00:00+0000",
                    "object_id": "camp1", "object_type": "campaign",
                    "actor_id": "u1", "actor_name": "Op",
                    "extra_data": json.dumps({"old_value": "PAUSED", "new_value": "ACTIVE"}),
                },
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            activities = a.list_activities("act_1", since=1753113600, until=1753200000)
        assert [act.new_value for act in activities] == ["ACTIVE", "PAUSED", "ACTIVE"]
        # Distinct, tz-aware timestamps, same calendar day.
        assert len({act.occurred_at for act in activities}) == 3
        assert all(act.occurred_at.tzinfo is not None for act in activities)
        assert len({act.occurred_at.date() for act in activities}) == 1
        # id synthesized (Graph doesn't return one on this edge) but
        # distinct per row.
        assert all(act.id for act in activities)
        assert len({act.id for act in activities}) == 3

    # ── The App-Review honesty gate — scope absent → never faked ──────

    def test_list_ad_accounts_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(httpx, "get", return_value=_FakeResponse(_PERM_ERR)):
            with pytest.raises(MetaGraphError) as exc:
                a.list_ad_accounts()
        assert exc.value.requires_app_review is True
        assert exc.value.is_permission is True
        assert exc.value.is_auth_error is False

    def test_list_ad_sets_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(httpx, "get", return_value=_FakeResponse(_PERM_ERR)):
            with pytest.raises(MetaGraphError) as exc:
                a.list_ad_sets("123")
        assert exc.value.requires_app_review is True

    def test_list_ads_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(httpx, "get", return_value=_FakeResponse(_PERM_ERR)):
            with pytest.raises(MetaGraphError) as exc:
                a.list_ads("123")
        assert exc.value.requires_app_review is True

    def test_ad_insights_series_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(httpx, "get", return_value=_FakeResponse(_PERM_ERR)):
            with pytest.raises(MetaGraphError) as exc:
                a.ad_insights_series("123", "campaign")
        assert exc.value.requires_app_review is True

    def test_list_activities_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(httpx, "get", return_value=_FakeResponse(_PERM_ERR)):
            with pytest.raises(MetaGraphError) as exc:
                a.list_activities("act_1", since=0, until=1)
        assert exc.value.requires_app_review is True


# ─── TestPriorSurfaceRegression ────────────────────────────────────────────


class TestPriorSurfaceRegression:
    """Sentinel: this additive ads-read extension must NOT alter the
    pre-existing `list_ad_campaigns` / `ad_insights` / ads-management
    surface. Re-exercises them + the parity idiom on both adapters."""

    def test_ad_insights_and_list_ad_campaigns_unbroken(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        campaigns_body = {
            "data": [{"id": "c1", "name": "Camp1", "status": "ACTIVE"}],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(campaigns_body)):
            camps = a.list_ad_campaigns("123")
        assert [c.id for c in camps] == ["c1"]
        insights_body = {"data": [{"impressions": "1000", "spend": "12.50"}]}
        with patch.object(httpx, "get", return_value=_FakeResponse(insights_body)):
            ins = a.ad_insights("c1", "campaign")
        assert ins.metrics["impressions"] == 1000.0

    def test_list_ad_campaigns_parses_cbo_budget(self):
        """CBO campaigns carry a campaign-level daily/lifetime budget
        (minor unit, coerced to int); ABO campaigns omit it → None,
        never a silent 0 (the pacing rollup relies on that distinction)."""
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        body = {
            "data": [
                {
                    "id": "cbo1", "name": "CBO", "status": "ACTIVE",
                    "effective_status": "ACTIVE", "daily_budget": "15000",
                    "lifetime_budget": "300000",
                },
                {  # ABO — no campaign-level budget field at all
                    "id": "abo1", "name": "ABO", "status": "ACTIVE",
                    "effective_status": "ACTIVE",
                },
            ],
            "paging": {},
        }
        with patch.object(httpx, "get", return_value=_FakeResponse(body)):
            camps = a.list_ad_campaigns("123")
        by_id = {c.id: c for c in camps}
        assert by_id["cbo1"].daily_budget == 15000
        assert isinstance(by_id["cbo1"].daily_budget, int)
        assert by_id["cbo1"].lifetime_budget == 300000
        assert by_id["abo1"].daily_budget is None  # never a silent 0
        assert by_id["abo1"].lifetime_budget is None

    def test_factory_default_fake_carries_ads_read_contract(self):
        impl = get_meta_adapter()
        assert isinstance(impl, FakeMetaAdapter)
        surface = (
            "list_ad_accounts",
            "list_ad_sets",
            "list_ads",
            "ad_insights_series",
            "list_activities",
        )
        for name in surface:
            assert callable(getattr(impl, name)), f"Fake missing {name}"

    def test_both_adapters_carry_ads_read_contract(self):
        surface = (
            "list_ad_accounts",
            "list_ad_sets",
            "list_ads",
            "ad_insights_series",
            "list_activities",
        )
        for impl in (FakeMetaAdapter(), MetaOAuthAdapter(system_user_token="X")):
            for name in surface:
                assert callable(getattr(impl, name)), (
                    f"{type(impl).__name__} missing {name}"
                )
