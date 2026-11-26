"""Seed Meta ad-analytics engine: `MetaAdapter.ad_account_insights` (Real +
Fake, parity), the `ad_analytics_row_from_body` mapper (one live-shaped test
per field family) and the pure `ads_kpis` module.

Golden tests feed rows from `fixtures/meta/ads_insights_golden.json` — real
Graph v27 insights rows of two properties (ONE10449, ONE10341) with synthetic
ids, neutral campaign names, the presenter's name replaced and action lists
trimmed. The expected numbers are the ones the validated dev script
`products/social-wiring/projects/meta-ads-snapshots/kpi_pack.py` printed for
the same runs on 2026-11-26 (ONE10449 run #3, ONE10341 run #4).

External boundary only: `httpx.get` is patched for the Real adapter. No
`noctusai_lib` code is monkey-patched.
"""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from noctusai_lib.integrations.meta import (
    ActionValue,
    AdAnalyticsRow,
    FakeMetaAdapter,
    MetaAdapter,
    MetaGraphError,
    ad_analytics_row_from_body,
)
from noctusai_lib.integrations.meta import ads_kpis as K
from noctusai_lib.integrations.meta._meta_api import DEFAULT_GRAPH_VERSION
from noctusai_lib.integrations.meta.mappers import AD_ANALYTICS_VIDEO_FIELDS
from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter

FX = json.loads((Path(__file__).parents[2] / "fixtures" / "meta" / "ads_insights_golden.json").read_text())
P49 = FX["ONE10449"]
P41 = FX["ONE10341"]


def _ad(rows, name):
    return next(r for r in rows if r["ad_name"] == name)


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return json.dumps(self._payload)


_PERM_ERR = {"error": {"message": "(#200) ads_read permission required", "code": 200, "type": "OAuthException"}}


# ─── Graph version pin ─────────────────────────────────────────────────────


def test_default_graph_version_is_v25():
    # Meta already served the old v21 calls as v25 (expired versions are
    # silently upgraded), so this pin is behaviour-preserving.
    assert DEFAULT_GRAPH_VERSION == "v25.0"
    assert MetaOAuthAdapter(system_user_token="X")._version == "v25.0"


# ─── mapper: one live-shaped test per field family ────────────────────────


class TestAdAnalyticsMapper:
    def test_delivery_and_link_family(self):
        r = ad_analytics_row_from_body(_ad(P49["lifetime_ad"], "ONE10449 Host v2"), level="ad")
        assert r.level == "ad" and r.object_id == r.ad_id and r.object_name == "ONE10449 Host v2"
        assert r.spend == 103.98 and r.impressions == 780 and r.reach == 620
        assert r.frequency == pytest.approx(1.258065) and r.cpm == pytest.approx(133.307692)
        assert r.clicks == 18 and r.inline_link_clicks == 5
        assert r.inline_link_click_ctr == pytest.approx(0.641026)
        assert r.cost_per_inline_link_click == pytest.approx(20.796)
        assert r.objective == "OUTCOME_LEADS" and r.optimization_goal == "QUALITY_LEAD"
        assert r.date_start == "2026-07-27" and r.date_stop == "2026-11-26"
        assert r.raw["ad_name"] == "ONE10449 Host v2"

    def test_actions_keep_every_attribution_window(self):
        r = ad_analytics_row_from_body(_ad(P49["lifetime_ad"], "ONE10449 Host v2"), level="ad")
        vv = r.actions["video_view"]
        assert vv == ActionValue("video_view", 267.0, {"1d_view": 266.0, "7d_click": 1.0})
        assert r.action("onsite_conversion.lead_grouped") == 1.0
        assert r.action("video_view", window="1d_view") == 266.0
        assert r.cost_per_action_type["onsite_conversion.lead_grouped"].value == 103.98
        assert r.unique_actions["link_click"].value == 5.0

    def test_action_without_own_window_value_is_none_not_zero(self):
        r = ad_analytics_row_from_body(
            {"ad_id": "1", "actions": [{"action_type": "lead", "1d_view": "2"}]}, level="ad"
        )
        assert r.actions["lead"].value is None
        assert r.actions["lead"].windows == {"1d_view": 2.0}

    def test_results_family_prefers_default_window(self):
        row = _ad(P41["lifetime_ad"], "ONE10341 - Golden November")
        r = ad_analytics_row_from_body(row, level="ad")
        assert r.result.indicator == "conversion_leads:conversion_lead"
        assert r.result.value == 48.0
        assert r.result.values_by_window == {"7d_click": 48.0, "default": 48.0}
        assert r.result.cost == pytest.approx(24.01604167)
        synthetic = ad_analytics_row_from_body({"ad_id": "1", "results": [{
            "indicator": "x", "values": [
                {"value": "3", "attribution_windows": ["7d_click"]},
                {"value": "5", "attribution_windows": ["default"]},
            ]}]}, level="ad")
        assert synthetic.result.value == 5.0

    def test_results_absent_for_lead_ads_is_none(self):
        r = ad_analytics_row_from_body(_ad(P49["lifetime_ad"], "ONE10449 Host v2"), level="ad")
        assert r.result is None

    def test_video_family(self):
        v = ad_analytics_row_from_body(_ad(P49["lifetime_ad"], "ONE10449 Host v2"), level="ad").video
        assert v.views_3s == 267 and v.plays == 682 and v.thruplay == 72
        assert (v.p25, v.p50, v.p75, v.p95, v.p100) == (54, 34, 24, 13, 9)
        assert v.avg_time_s == 8 and v.views_30s == 47
        assert v.views_6s is None  # omitted by Graph for this row
        assert v.cost_per_thruplay == pytest.approx(1.444167)
        assert v.play_curve[:6] == (100, 86, 55, 40, 31, 27) and len(v.play_curve) == 22

    def test_outbound_clicks_list_is_summed(self):
        r = ad_analytics_row_from_body({"ad_id": "1", "outbound_clicks": [
            {"action_type": "outbound_click", "value": "7"}]}, level="ad")
        assert r.outbound_clicks == 7.0

    def test_rankings_family(self):
        r = ad_analytics_row_from_body(_ad(P41["lifetime_ad"], "ONE10341 - Golden November"), level="ad")
        assert r.quality_ranking == "ABOVE_AVERAGE"
        assert r.engagement_rate_ranking == "UNKNOWN"

    def test_breakdown_dims_from_combined_string(self):
        row = P49["breakdowns"]["age,gender"][0]
        r = ad_analytics_row_from_body(row, level="ad", breakdown_keys=["age,gender"])
        assert set(r.breakdown) == {"age", "gender"}

    def test_absent_fields_stay_none(self):
        r = ad_analytics_row_from_body({"ad_id": "1", "spend": ""}, level="ad")
        assert r.spend is None and r.impressions is None and r.video.play_curve is None
        assert r.result is None and r.actions == {}


# ─── Real adapter ─────────────────────────────────────────────────────────


class TestRealAdAccountInsights:
    def _call(self, pages, **kw):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        seen = []

        def _get(url, params=None, **_):
            seen.append((url, params))
            return _Resp(pages[len(seen) - 1])

        with patch.object(httpx, "get", side_effect=_get):
            rows = a.ad_account_insights("873", **kw)
        return rows, seen

    def test_request_shape_and_typed_rows(self):
        rows, seen = self._call(
            [{"data": P41["lifetime_ad"], "paging": {}}],
            object_ids=["a1", "a2"],
            name_contains="10341",
        )
        url, params = seen[0]
        assert url == f"https://graph.facebook.com/{DEFAULT_GRAPH_VERSION}/act_873/insights"
        assert params["level"] == "ad" and params["date_preset"] == "maximum"
        assert params["time_increment"] == "all_days"
        assert json.loads(params["filtering"]) == [
            {"field": "ad.id", "operator": "IN", "value": ["a1", "a2"]},
            {"field": "ad.name", "operator": "CONTAIN", "value": "10341"},
        ]
        assert json.loads(params["action_attribution_windows"]) == ["7d_click", "1d_view"]
        fields = params["fields"].split(",")
        assert "video_play_curve_actions" in fields and "results" in fields
        assert "video_continuous_2_sec_watched_actions" not in fields
        assert all(isinstance(r, AdAnalyticsRow) for r in rows) and len(rows) == 4

    def test_time_range_daily_and_breakdowns(self):
        _, seen = self._call(
            [{"data": [], "paging": {}}],
            level="adset",
            time_range=(date(2026, 10, 27), date(2026, 11, 26)),
            time_increment=1,
            breakdowns=["publisher_platform", "platform_position"],
        )
        params = seen[0][1]
        assert "date_preset" not in params
        assert json.loads(params["time_range"]) == {"since": "2026-10-27", "until": "2026-11-26"}
        assert params["time_increment"] == "1"
        assert params["breakdowns"] == "publisher_platform,platform_position"
        assert params["level"] == "adset"

    def test_hourly_breakdown_drops_video_fields(self):
        _, seen = self._call(
            [{"data": [], "paging": {}}],
            breakdowns=["hourly_stats_aggregated_by_advertiser_time_zone"],
        )
        fields = seen[0][1]["fields"].split(",")
        assert not set(AD_ANALYTICS_VIDEO_FIELDS) & set(fields)
        assert "spend" in fields

    def test_paginates(self):
        daily = P41["daily_ad"]
        rows, seen = self._call([
            {"data": daily[:20], "paging": {"next": "https://graph.facebook.com/v25.0/act_873/insights?after=C"}},
            {"data": daily[20:], "paging": {}},
        ], time_increment=1)
        assert len(rows) == len(daily) and len(seen) == 2

    def test_breakdown_rows_carry_dims(self):
        rows, _ = self._call(
            [{"data": P49["breakdowns"]["age,gender"], "paging": {}}], breakdowns=["age,gender"]
        )
        assert all(set(r.breakdown) == {"age", "gender"} for r in rows)

    @pytest.mark.parametrize("kw", [
        {"level": "account"},
        {"time_range": (date(2026, 1, 1), date(2026, 1, 2)), "date_preset": "last_7d"},
    ])
    def test_invalid_args_refused(self, kw):
        with pytest.raises(ValueError):
            MetaOAuthAdapter(system_user_token="X").ad_account_insights("1", **kw)

    def test_permission_error_surfaces(self):
        with patch.object(httpx, "get", return_value=_Resp(_PERM_ERR)):
            with pytest.raises(MetaGraphError) as exc:
                MetaOAuthAdapter(system_user_token="X").ad_account_insights("1")
        assert exc.value.requires_app_review is True


# ─── Fake adapter + parity ────────────────────────────────────────────────


class TestFakeAdAccountInsights:
    def _fake(self):
        life = [ad_analytics_row_from_body(r, level="ad") for r in P49["lifetime_ad"]]
        bd = [ad_analytics_row_from_body(r, level="ad", breakdown_keys=["age,gender"])
              for r in P49["breakdowns"]["age,gender"]]
        return FakeMetaAdapter().seed(ad_account_insights={"act_1": life + bd}), life

    def test_serves_seeded_rows_with_filters(self):
        fake, life = self._fake()
        assert len(fake.ad_account_insights("1")) == 9
        assert len(fake.ad_account_insights("act_1", name_contains="host")) == 2
        one = life[0].ad_id
        assert [r.ad_id for r in fake.ad_account_insights("1", object_ids=[one])] == [one]
        assert fake.ad_account_insights("1", level="adset") == []
        bd = fake.ad_account_insights("1", breakdowns=["age", "gender"])
        assert bd and all(set(r.breakdown) == {"age", "gender"} for r in bd)
        assert fake.ad_account_insights("unknown") == []

    def test_same_validation_as_real(self):
        with pytest.raises(ValueError):
            FakeMetaAdapter().ad_account_insights("1", level="account")

    def test_signature_parity_protocol_real_fake(self):
        names = [
            list(inspect.signature(getattr(c, "ad_account_insights")).parameters)
            for c in (MetaAdapter, MetaOAuthAdapter, FakeMetaAdapter)
        ]
        assert names[0] == names[1] == names[2]


# ─── ads_kpis golden: ONE10449 ────────────────────────────────────────────


class TestGoldenOne10449:
    def test_host_v2_per_ad(self):
        k = K.ad_kpis(_ad(P49["lifetime_ad"], "ONE10449 Host v2"))
        assert k.property_code == "ONE10449" and k.variant == "Host v2"
        assert k.spend == 103.98 and k.form_leads == 1 and k.cpl == pytest.approx(103.98)
        assert k.frequency == pytest.approx(1.26, abs=0.005)
        assert k.cpm == pytest.approx(133.31, abs=0.005)
        assert k.link_ctr_pct == pytest.approx(0.64, abs=0.005)
        assert k.cost_per_link_click == pytest.approx(20.80, abs=0.005)
        assert k.click_to_lead_pct == pytest.approx(20.0)
        assert k.qualified is None and k.cost_per_qualified is None
        v = k.video
        assert v.hook_rate_pct == pytest.approx(34.23, abs=0.005)
        assert v.hold_rate_pct == pytest.approx(26.97, abs=0.005)
        assert v.six_to_three_pct is None
        assert v.curve_points == {"1": 86, "3": 40, "5": 27, "10": 17, "14": 11}
        assert v.avg_watch_s == 8
        assert v.quartiles == {"p25": 54, "p50": 34, "p75": 24, "p95": 13, "p100": 9}

    def test_host_per_ad(self):
        k = K.ad_kpis(_ad(P49["lifetime_ad"], "ONE10449 Host"))
        assert k.spend == 695.38 and k.form_leads == 4
        assert k.cpl == pytest.approx(173.84, abs=0.005)
        assert k.click_to_lead_pct == pytest.approx(2.80, abs=0.005)
        assert k.video.hook_rate_pct == pytest.approx(26.79, abs=0.005)
        assert k.video.hold_rate_pct == pytest.approx(18.79, abs=0.005)
        assert k.video.curve_points["1"] == 69

    def test_traffic_ad_other_result(self):
        k = K.ad_kpis(_ad(P49["lifetime_ad"], "ONE10449"))
        assert k.result["indicator"] == "profile_visit_view" and k.result["value"] == 1740
        assert k.link_ctr_pct == pytest.approx(6.13, abs=0.005)

    def test_objective_rollup_uses_campaign_objective(self):
        out = {o.objective: o for o in K.objective_rollup(
            P49["lifetime_ad"], campaign_objectives=P49["campaign_objectives"])}
        leads, traffic = out["OUTCOME_LEADS"], out["OUTCOME_TRAFFIC"]
        assert leads.spend == pytest.approx(2009.86) and leads.form_leads == 8
        assert leads.cpl == pytest.approx(251.23, abs=0.005)
        assert leads.impressions == 34102 and leads.link_clicks == 407
        assert leads.link_ctr_pct == pytest.approx(1.19, abs=0.005)
        assert leads.qualified is None and leads.ads == 8
        assert traffic.spend == pytest.approx(303.39) and traffic.form_leads == 1
        assert traffic.other_results == 1740 and traffic.link_clicks == 1802
        assert traffic.link_ctr_pct == pytest.approx(6.13, abs=0.005)

    def test_insights_objective_is_legacy_without_campaign_map(self):
        # Trap: the insights row says LINK_CLICKS for an OUTCOME_TRAFFIC campaign.
        assert {o.objective for o in K.objective_rollup(P49["lifetime_ad"])} == {
            "LINK_CLICKS", "OUTCOME_LEADS"}

    def test_daily_series_reconciles_to_lifetime(self):
        host_v2 = [r for r in P49["daily_ad"] if r["ad_name"] == "ONE10449 Host v2"]
        days = K.daily_series(host_v2)
        assert [d.date for d in days] == ["2026-11-23", "2026-11-24", "2026-11-25"]
        assert sum(d.spend for d in days) == pytest.approx(103.98)
        assert sum(d.form_leads for d in days) == 1

    def test_dict_and_typed_inputs_give_identical_numbers(self):
        row = _ad(P49["lifetime_ad"], "ONE10449 Host v2")
        typed = ad_analytics_row_from_body(row, level="ad")
        assert K.ad_kpis(row).to_dict() == K.ad_kpis(typed).to_dict()


# ─── ads_kpis golden: ONE10341 ────────────────────────────────────────────


class TestGoldenOne10341:
    def test_lifetime_funnel_with_qualified(self):
        (o,) = K.objective_rollup(P41["lifetime_ad"], campaign_objectives=P41["campaign_objectives"])
        assert o.objective == "OUTCOME_LEADS" and o.ads == 4
        assert o.spend == pytest.approx(1794.71) and o.form_leads == 66 and o.qualified == 53
        assert o.cpl == pytest.approx(27.19, abs=0.005)
        assert o.cost_per_qualified == pytest.approx(33.86, abs=0.005)
        assert o.impressions == 57140 and o.link_clicks == 1538

    def test_per_ad_golden_november(self):
        k = K.ad_kpis(_ad(P41["lifetime_ad"], "ONE10341 - Golden November"))
        assert k.form_leads == 50 and k.qualified == 48
        assert k.cpl == pytest.approx(23.06, abs=0.005)
        assert k.click_to_lead_pct == pytest.approx(4.30, abs=0.005)
        assert k.rankings["quality"] == "ABOVE_AVERAGE"

    def test_window_funnel_qualified_49_of_51(self):
        (w,) = K.window_funnel(P41["daily_ad"], P41["window_since"],
                               campaign_objectives=P41["campaign_objectives"])
        assert w.ads == 2
        assert w.spend == pytest.approx(1212.84) and w.impressions == 38007
        assert w.cpm == pytest.approx(31.91, abs=0.005)
        assert w.link_clicks == 1229 and w.link_ctr_pct == pytest.approx(3.23, abs=0.005)
        assert w.form_leads == 51 and w.qualified == 49
        assert w.click_to_lead_pct == pytest.approx(4.15, abs=0.005)
        assert w.cpl == pytest.approx(23.78, abs=0.005)
        assert w.cost_per_qualified == pytest.approx(24.75, abs=0.005)
        assert round(w.qualified_share_pct) == 96

    def test_window_placement_breakdown(self):
        rep = K.build_property_report(
            P41["lifetime_ad"], P41["daily_ad"], property_code="ONE10341",
            window_since=P41["window_since"], breakdown_rows=P41["breakdowns_window"],
            campaign_objectives=P41["campaign_objectives"],
        )
        b = {x.bucket: x for x in rep.breakdowns["publisher_platform,platform_position"]}
        st = b["instagram|instagram_stories"]
        assert st.spend == pytest.approx(1017.50, abs=0.005) and round(st.share_pct) == 84
        assert st.impressions == 32416 and st.link_clicks == 1045 and st.form_leads == 48
        assert st.cpm == pytest.approx(31.39, abs=0.005)
        assert b["instagram|instagram_reels"].spend == pytest.approx(163.85, abs=0.005)
        assert b["instagram|instagram_reels"].form_leads == 3
        assert b["instagram|feed"].spend == pytest.approx(31.46, abs=0.005) and b["instagram|feed"].form_leads == 0

    def test_pools_are_shared(self):
        rep = K.build_property_report(P41["lifetime_ad"], property_code="ONE10341",
                                      adset_siblings=P41["adset_siblings"])
        assert rep.pools and all(p.kind == "shared" for p in rep.pools.values())
        assert all(p.other_ads > 0 for p in rep.pools.values())


# ─── ads_kpis units ───────────────────────────────────────────────────────


class TestPropertyCode:
    def test_exact_code_token(self):
        assert K.parse_property("ONE10449 Larissa v2") == ("ONE10449", "Larissa v2")
        assert K.parse_property("one10647") == ("ONE10647", None)
        assert K.parse_property_code("ONE104490 x") == "ONE104490"
        assert K.parse_property_code("Público One") is None

    def test_filter_property_rows_drops_contain_false_positives(self):
        rows = [{"ad_id": "1", "ad_name": "ONE10449 a"}, {"ad_id": "2", "ad_name": "ONE104490 b"}]
        assert [r.ad_id for r in K.filter_property_rows(rows, "one10449")] == ["1"]


class TestPoolStatus:
    def test_exclusive_shared_unknown(self):
        assert K.pool_status("ONE101", [{"name": "ONE101 a"}, {"name": "ONE101 b"}]).kind == "exclusive"
        s = K.pool_status("ONE101", [{"name": "ONE101"}, {"name": "ONE102", "effective_status": "ACTIVE"},
                                   {"name": "ONE103", "effective_status": "PAUSED"}])
        assert (s.kind, s.ads, s.other_ads, s.other_active) == ("shared", 3, 2, 1)
        assert K.pool_status("ONE101", None).kind == "unknown"
        assert K.pool_status("ONE101", []).kind == "unknown"

    def test_prefix_code_is_not_the_same_property(self):
        assert K.pool_status("ONE1044", [{"name": "ONE10449"}]).kind == "shared"


class TestCurve:
    def test_bucket_labels_cover_22_points(self):
        assert len(K.CURVE_BUCKET_LABELS) == 22
        assert K.CURVE_BUCKET_LABELS[14] == "14s" and K.CURVE_BUCKET_LABELS[15] == "15-20s"
        assert K.CURVE_BUCKET_LABELS[18] == "30-40s" and K.CURVE_BUCKET_LABELS[21] == ">60s"

    def test_curve_points_none_without_curve(self):
        assert K.curve_points(None) is None


def _day(d, impr, reach, lc, spend, leads=0):
    return {"ad_id": "A", "ad_name": "ONE1 x", "date_start": d, "date_stop": d, "spend": str(spend),
            "impressions": str(impr), "reach": str(reach), "inline_link_clicks": str(lc),
            "actions": [{"action_type": K.LEAD_ACTION, "value": str(leads)}] if leads else []}


class TestFatigue:
    def test_signals_fire_on_a_fatiguing_series(self):
        rows = [_day(f"2026-11-{i:02d}", 1000, 900, 20, 30, 2) for i in range(1, 8)]
        rows += [_day(f"2026-11-{i:02d}", 1000, 500, 8, 60, 1) for i in range(20, 27)]
        (f,) = K.fatigue(rows)
        assert f.sufficient_history is True
        assert set(f.signals) == {"frequency_up", "link_ctr_down", "cpm_up", "cpl_up"}
        assert f.baseline.start == "2026-11-01" and f.baseline.end == "2026-11-07"
        assert f.recent.start == "2026-11-20" and f.recent.end == "2026-11-26"
        assert f.change_pct["cpm"] == pytest.approx(100.0)

    def test_short_history_gives_no_signals(self):
        host_v2 = [r for r in P49["daily_ad"] if r["ad_name"] == "ONE10449 Host v2"]
        (f,) = K.fatigue(host_v2)
        assert f.sufficient_history is False and f.signals == ()

    def test_stable_series_has_no_signals(self):
        rows = [_day(f"2026-11-{i:02d}", 1000, 900, 20, 30, 2) for i in range(1, 27)]
        assert K.fatigue(rows)[0].signals == ()


class TestBreakdownAggregate:
    def test_share_over_all_buckets_and_min_spend_hides_only(self):
        rows = [{"ad_id": "1", "age": "25-34", "spend": "9", "impressions": "100"},
                {"ad_id": "1", "age": "35-44", "spend": "1", "impressions": "50"},
                {"ad_id": "2", "age": "25-34", "spend": "5", "impressions": "10"}]
        out = K.breakdown_aggregate(rows, ["age"], ad_ids=["1"], min_spend=2)
        assert [(b.bucket, b.share_pct) for b in out] == [("25-34", 90.0)]


# ─── the to_dict() contract ───────────────────────────────────────────────


class TestContract:
    def test_report_to_dict_is_json_and_matches_documented_keys(self):
        rep = K.build_property_report(
            P41["lifetime_ad"], P41["daily_ad"], property_code="ONE10341",
            window_since=P41["window_since"], breakdown_rows=P41["breakdowns_window"],
            adset_siblings=P41["adset_siblings"], campaign_objectives=P41["campaign_objectives"],
        )
        d = json.loads(json.dumps(rep.to_dict()))
        assert d["schema"] == "noctus.meta-ads-kpis/v1"
        assert set(d) == {"schema", "property_code", "window", "ads", "objectives_lifetime",
                          "objectives_window", "daily", "breakdowns", "fatigue", "pools"}
        assert d["window"] == {"since": "2026-10-27", "until": None}
        assert set(d["ads"][0]) == {
            "ad_id", "ad_name", "property_code", "variant", "campaign_id", "adset_id", "objective",
            "date_start", "date_stop", "spend", "impressions", "reach", "frequency", "cpm", "clicks",
            "ctr_pct", "link_clicks", "link_ctr_pct", "cost_per_link_click", "outbound_clicks",
            "form_leads", "cpl", "click_to_lead_pct", "qualified", "cost_per_qualified", "result",
            "rankings", "video"}
        assert d["ads"][0]["ad_name"] == "ONE10341 - Golden November"  # spend desc
        assert set(d["ads"][0]["video"]) == {
            "views_3s", "plays", "thruplay", "views_6s", "views_30s", "hook_rate_pct", "hold_rate_pct",
            "six_to_three_pct", "avg_watch_s", "cost_per_thruplay", "quartiles", "curve_points", "curve"}
        assert set(d["objectives_window"][0]) == {
            "objective", "ads", "spend", "impressions", "cpm", "link_clicks", "link_ctr_pct",
            "form_leads", "cpl", "click_to_lead_pct", "qualified", "cost_per_qualified",
            "qualified_share_pct", "other_results"}
        assert set(d["daily"][0]) == {"date", "spend", "impressions", "link_clicks", "form_leads", "cpm"}
        assert set(next(iter(d["breakdowns"].values()))[0]) == {
            "bucket", "dims", "spend", "share_pct", "impressions", "link_clicks", "form_leads", "cpm"}
        f = d["fatigue"][0]
        assert set(f) == {"ad_id", "ad_name", "sufficient_history", "baseline", "recent", "change_pct", "signals"}
        assert set(f["baseline"]) == {"start", "end", "days_with_delivery", "spend", "impressions",
                                      "frequency", "link_ctr_pct", "cpm", "form_leads", "cpl"}
        assert set(next(iter(d["pools"].values()))) == {"kind", "ads", "other_ads", "other_active"}
