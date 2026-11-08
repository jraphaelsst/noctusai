"""`/api/admin/usage/ai/*` — asserts docs/ai-usage-contract.md.

Real auth (strict 401 / 403 platform_admin_required); only the trusted DB + session user come through
dependency_overrides. Data is synthetic.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.trusted_auth import get_session_user, get_trusted_db
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, make_ctx, seed_users

BASE = "/api/admin/usage/ai"
W = {"from": "2026-11-01", "to": "2026-11-08"}
FRESH = "2026-11-08T10:00:00+00:00"


def _u(day, **kw):
    row = {"day": day, "dims_key": f"{day}-{kw.get('model', 'm')}-{kw.get('workspace_id', '')}", "model": "m-a",
           "workspace_id": "", "api_key_id": "", "service_tier": "", "context_window": "", "uncached_input": 100,
           "cache_write_5m": 10, "cache_write_1h": 5, "cache_read": 1000, "output_tokens": 50,
           "web_search_requests": 1, "requests": 4, "data_refreshed_at": FRESH, "is_final": False}
    row.update(kw)
    return row


def _c(day, cents, **kw):
    row = {"day": day, "dims_key": f"{day}-{kw.get('cost_type', 't')}-{kw.get('token_type', '')}", "model": "m-a",
           "workspace_id": "", "api_key_id": "", "cost_type": "tokens", "token_type": "output_tokens",
           "amount_cents": cents, "list_amount_cents": None, "currency": "USD", "data_refreshed_at": FRESH,
           "is_final": False}
    row.update(kw)
    return row


def _tel(bucket, **kw):
    row = {"host": "mac", "bucket": bucket, "session_id": "s1", "agent_id": "", "project": "noc", "model": "opus",
           "requests": 2, "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 100, "cache_write_tokens": 50,
           "cost_usd": 1.5, "ambiente": "local", "origem": "desconhecido", "synced_at": "2026-11-08T11:00:00+00:00"}
    row.update(kw)
    return row


@pytest.fixture
def env():
    _ctx, fakes = make_ctx()
    seed_users(fakes.db)
    db = fakes.db
    state = SimpleNamespace(db=db, user=ADMIN_USER)

    async def session_user():
        return SimpleNamespace(id=state.user)

    app.dependency_overrides[get_trusted_db] = lambda: db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


def _ok_anthropic(db, **extra):
    db.set_table_data("ai_source_sync_runs", [
        {"id": 1, "source": "anthropic", "endpoint": "usage", "status": "ok", "reason_code": None,
         "finished_at": "2026-11-08T10:01:00+00:00", "data_refreshed_at": "2026-11-08T10:00:00+00:00"}])
    db.set_table_data("ai_anthropic_usage_daily", extra.get("usage", []))
    db.set_table_data("ai_anthropic_cost_daily", extra.get("cost", []))


URLS = [f"{BASE}/sources", f"{BASE}/usage?source=anthropic", f"{BASE}/cost?source=anthropic",
        f"{BASE}/spend?source=anthropic&month=2026-11", f"{BASE}/deliveries?source=ledger", f"{BASE}/rate-limits?source=anthropic"]


@pytest.mark.parametrize("url", URLS)
def test_no_token_is_strictly_401(url):
    app.dependency_overrides.clear()
    assert TestClient(app).get(url, params=W).status_code == 401


@pytest.mark.parametrize("url", URLS)
def test_non_platform_admin_is_403_platform_admin_required(env, url):
    env.user = MEMBER_USER
    r = env.client.get(url, params=W)
    # the shared dependency's body is flat (seed error shape): {"detail": <msg>, "code": "platform_admin_required"}
    assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"


@pytest.mark.parametrize("params,code", [
    ({"from": "2026-11-09", "to": "2026-11-01"}, "range_invalid"),
    ({"from": "nope", "to": "2026-11-01"}, "range_invalid"),
    ({"to": "2026-11-01"}, "range_invalid"),
    ({"from": "2026-10-01", "to": "2026-11-08"}, "range_too_long"),
    ({"from": "2025-12-20", "to": "2026-01-02"}, "range_before_coverage"),
    ({**W, "ambiente": "prod"}, "filter_not_supported_by_source"),
    ({**W, "group_by": "agent"}, "group_by_not_supported_by_source"),
])
@pytest.mark.parametrize("endpoint", ["usage", "cost"])
def test_typed_422s(env, endpoint, params, code):
    r = env.client.get(f"{BASE}/{endpoint}", params={"source": "anthropic", **params})
    assert r.status_code == 422 and r.json()["detail"]["code"] == code


def test_ledger_filter_and_group_not_supported_by_ledger(env):
    r = env.client.get(f"{BASE}/usage", params={"source": "ledger", **W, "workspace_id": "w"})
    assert r.json()["detail"]["code"] == "filter_not_supported_by_source"
    r = env.client.get(f"{BASE}/usage", params={"source": "ledger", **W, "group_by": "workspace"})
    assert r.json()["detail"]["code"] == "group_by_not_supported_by_source"
    r = env.client.get(f"{BASE}/cost", params={"source": "anthropic", **W, "group_by": "service_tier"})
    assert r.json()["detail"]["code"] == "group_by_not_supported_by_source"


def test_spend_month_validation_and_deliveries_rate_limits_source_422(env):
    assert env.client.get(f"{BASE}/spend", params={"source": "anthropic", "month": "2026-13"}).json()["detail"]["code"] == "range_invalid"
    assert env.client.get(f"{BASE}/spend", params={"source": "anthropic", "month": "2025-12"}).json()["detail"]["code"] == "range_before_coverage"
    assert env.client.get(f"{BASE}/deliveries", params={"source": "anthropic", **W}).status_code == 422
    assert env.client.get(f"{BASE}/rate-limits", params={"source": "ledger"}).json()["detail"]["code"] == "filter_not_supported_by_source"


def test_unavailable_source_is_200_with_empty_arrays_and_reason(env):
    env.db.set_table_data("ai_source_sync_runs", [
        {"id": 2, "source": "anthropic", "endpoint": "usage", "status": "unavailable", "reason_code": "individual_org",
         "finished_at": "2026-11-08T10:01:00+00:00", "data_refreshed_at": None}])
    for ep, extra in (("usage", {}), ("cost", {}), ("rate-limits", {}), ("spend", {"month": "2026-11"})):
        r = env.client.get(f"{BASE}/{ep}", params={"source": "anthropic", **W, **extra})
        assert r.status_code == 200
        body = r.json()
        assert body["source"]["status"] == "unavailable" and body["source"]["reason_code"] == "individual_org"
        assert not body.get("series") and not body.get("groups") and not body.get("limits") and not body.get("daily")
    usage = env.client.get(f"{BASE}/usage", params={"source": "anthropic", **W}).json()
    assert all(v is None for v in usage["totals"].values())  # null, never 0
    cost = env.client.get(f"{BASE}/cost", params={"source": "anthropic", **W}).json()
    assert cost["totals"] == {"amount_usd": None, "list_amount_usd": None}
    assert env.client.get(f"{BASE}/spend", params={"source": "anthropic", "month": "2026-11"}).json()["derived_spend_usd"] is None


def test_no_runs_and_no_key_reads_no_admin_key():
    # key unset in the test settings: nothing ever synced -> unavailable / no_admin_key
    _ctx, fakes = make_ctx()
    seed_users(fakes.db)
    app.dependency_overrides[get_trusted_db] = lambda: fakes.db

    async def su():
        return SimpleNamespace(id=ADMIN_USER)

    app.dependency_overrides[get_session_user] = su
    try:
        body = TestClient(app).get(f"{BASE}/sources").json()
    finally:
        app.dependency_overrides.clear()
    assert body["anthropic"]["status"] == "unavailable" and body["anthropic"]["reason_code"] == "no_admin_key"
    assert body["ledger"]["status"] == "unavailable" and body["ledger"]["is_estimate"] is True


def test_stale_anthropic_and_ledger(env):
    env.db.set_table_data("ai_source_sync_runs", [
        {"id": 1, "source": "anthropic", "endpoint": "usage", "status": "ok", "reason_code": None,
         "finished_at": "2026-11-01T10:01:00+00:00", "data_refreshed_at": "2026-11-01T10:00:00+00:00"}])
    env.db.set_table_data("ai_anthropic_usage_daily", [_u("2026-11-01")])
    env.db.set_table_data("dev_telemetry_claude", [_tel("2026-11-01T10:00:00+00:00", synced_at="2026-11-01T11:00:00+00:00")])
    body = env.client.get(f"{BASE}/sources").json()
    assert body["anthropic"]["status"] == "stale" and body["ledger"]["status"] == "stale"
    assert body["anthropic"]["coverage_from"] == "2026-11-01" and body["anthropic"]["is_estimate"] is False


def test_error_run_reports_error_with_reason(env):
    env.db.set_table_data("ai_source_sync_runs", [
        {"id": 3, "source": "anthropic", "endpoint": "cost", "status": "error", "reason_code": "http_5xx",
         "finished_at": "2026-11-08T10:01:00+00:00", "data_refreshed_at": None}])
    body = env.client.get(f"{BASE}/sources").json()["anthropic"]
    assert body["status"] == "error" and body["reason_code"] == "http_5xx"


def test_usage_anthropic_totals_series_groups_and_empty_buckets_omitted(env):
    _ok_anthropic(env.db, usage=[
        _u("2026-11-02", model="m-a"), _u("2026-11-02", model="m-b", uncached_input=1, cache_write_5m=0, cache_write_1h=0,
                                          cache_read=0, output_tokens=1, requests=None, web_search_requests=None,
                                          dims_key="x2"),
        _u("2026-11-04", model="m-a"),
    ])
    body = env.client.get(f"{BASE}/usage", params={"source": "anthropic", **W, "group_by": "model"}).json()
    assert body["source"]["status"] == "ok" and body["window"] == {"from": "2026-11-01", "to": "2026-11-08", "days": 8}
    t = body["totals"]
    assert t["uncached_input_tokens"] == 201 and t["cache_write_tokens"] == 30 and t["cache_read_tokens"] == 2000
    assert t["input_tokens"] == 201 + 30 + 2000 and t["output_tokens"] == 101 and t["requests"] == 8
    assert {s["bucket_start"] for s in body["series"]} == {"2026-11-02", "2026-11-04"}  # empty days omitted
    groups = {g["key"]: g for g in body["groups"]}
    assert set(groups) == {"m-a", "m-b"} and groups["m-a"]["output_tokens"] == 100
    assert groups["m-b"]["requests"] is None and groups["m-b"]["web_search_requests"] is None  # null, not 0


def test_usage_week_bucket_and_token_type_group(env):
    _ok_anthropic(env.db, usage=[_u("2026-11-02"), _u("2026-11-04")])
    wk = env.client.get(f"{BASE}/usage", params={"source": "anthropic", **W, "bucket": "week"}).json()
    assert [s["bucket_start"] for s in wk["series"]] == ["2026-11-02"] and wk["series"][0]["output_tokens"] == 100
    tt = env.client.get(f"{BASE}/usage", params={"source": "anthropic", **W, "group_by": "token_type"}).json()
    g = {x["key"]: x for x in tt["groups"]}
    assert set(g) == {"uncached_input", "cache_write_5m", "cache_write_1h", "cache_read", "output"}
    assert g["cache_read"]["cache_read_tokens"] == 2000 and g["cache_read"]["output_tokens"] is None


def test_usage_ledger_records_no_web_search_and_main_agent(env):
    env.db.set_table_data("dev_telemetry_claude", [
        _tel("2026-11-02T10:00:00+00:00"), _tel("2026-11-02T10:05:00+00:00", agent_id="a1", session_id="s2")])
    body = env.client.get(f"{BASE}/usage", params={"source": "ledger", **W, "group_by": "agent"}).json()
    assert body["source"]["is_estimate"] is True and body["totals"]["web_search_requests"] is None
    assert {g["key"] for g in body["groups"]} == {"main", "a1"}
    assert body["totals"]["requests"] == 4 and body["totals"]["cache_write_tokens"] == 100
    only_main = env.client.get(f"{BASE}/usage", params={"source": "ledger", **W, "agent": "main"}).json()
    assert only_main["totals"]["requests"] == 2


def test_cost_converts_cents_to_usd_and_keeps_null_list(env):
    _ok_anthropic(env.db, cost=[_c("2026-11-02", "1250.5", list_amount_cents="1500"), _c("2026-11-03", "49.5", token_type="input")])
    body = env.client.get(f"{BASE}/cost", params={"source": "anthropic", **W, "group_by": "token_type"}).json()
    assert body["totals"]["amount_usd"] == pytest.approx(13.0) and body["totals"]["list_amount_usd"] == pytest.approx(15.0)
    g = {x["key"]: x for x in body["groups"]}
    assert g["output_tokens"]["amount_usd"] == pytest.approx(12.505) and g["input"]["list_amount_usd"] is None
    by_type = env.client.get(f"{BASE}/cost", params={"source": "anthropic", **W, "group_by": "cost_type"}).json()
    assert [x["key"] for x in by_type["groups"]] == ["tokens"]


def test_spend_derived_and_finality(env):
    _ok_anthropic(env.db, cost=[_c("2026-10-02", "1000", is_final=True), _c("2026-10-03", "500", is_final=True, dims_key="b")])
    body = env.client.get(f"{BASE}/spend", params={"source": "anthropic", "month": "2026-10"}).json()
    assert body["derived_spend_usd"] == pytest.approx(15.0) and body["is_final"] is True
    assert [d["day"] for d in body["daily"]] == ["2026-10-02", "2026-10-03"]
    assert body["spend_limit"] is None and body["credit_balance"] is None
    assert body["unavailable_fields"] == ["spend_limit", "credit_balance", "invoices"]
    empty = env.client.get(f"{BASE}/spend", params={"source": "anthropic", "month": "2026-09"}).json()
    assert empty["derived_spend_usd"] is None and empty["is_final"] is False and empty["daily"] == []


def _delivery(i, model, ts, **kw):
    row = {"line_hash": f"h{i}", "slug": f"s{i}", "agent": "backend-engineer", "model": model, "ts": ts,
           "q_weighted": 4.0, "first_pass": True, "rework_commits": 0, "tokens": None, "cost_usd": None,
           "wall_s_measured": None, "wall_s_self_reported": 120, "duration_minutes": 10, "outcome": "merged",
           "ambiente": "local", "ingested_at": "2026-11-08T11:00:00+00:00"}
    row.update(kw)
    return row


def test_deliveries_compare_trend_rows_and_small_sample(env):
    env.db.set_table_data("dev_telemetry_claude", [_tel("2026-11-02T10:00:00+00:00")])
    env.db.set_table_data("dev_deliveries", [
        _delivery(1, "opus", "2026-11-02T10:00:00+00:00", cost_usd=2.0, first_pass=False, q_weighted=3.0),
        _delivery(2, "opus", "2026-11-03T10:00:00+00:00", cost_usd=4.0),
        _delivery(3, "sonnet", "2026-11-10T10:00:00+00:00", wall_s_measured=30),
    ])
    body = env.client.get(f"{BASE}/deliveries", params={"source": "ledger", "from": "2026-11-01", "to": "2026-11-30"}).json()
    comp = {c["model"]: c for c in body["compare"]}
    assert comp["opus"]["n"] == 2 and comp["opus"]["small_sample"] is True and comp["opus"]["cost_is_estimate"] is True
    assert comp["opus"]["q_weighted_mean"] == pytest.approx(3.5) and comp["opus"]["first_pass_rate"] == pytest.approx(0.5)
    assert comp["opus"]["cost_usd_median"] == pytest.approx(3.0) and comp["sonnet"]["cost_usd_median"] is None
    assert comp["sonnet"]["wall_s_median"] == 30 and comp["opus"]["wall_s_median"] == 120
    assert {(t["week_start"], t["model"]) for t in body["trend"]} == {("2026-11-02", "opus"), ("2026-11-09", "sonnet")}
    assert [r["slug"] for r in body["rows"]] == ["s3", "s2", "s1"] and body["rows"][0]["tokens"] is None
    flt = env.client.get(f"{BASE}/deliveries", params={"source": "ledger", "from": "2026-11-01", "to": "2026-11-30", "model": "sonnet"}).json()
    assert [c["model"] for c in flt["compare"]] == ["sonnet"]


def test_rate_limits_org_scope_null_workspace(env):
    _ok_anthropic(env.db)
    env.db.set_table_data("ai_anthropic_rate_limits", [
        {"scope": "org", "workspace_id_key": "", "model_group": "g", "metric": "requests_per_minute", "limit_value": 50},
        {"scope": "workspace", "workspace_id_key": "wrkspc_x", "model_group": "g", "metric": "requests_per_minute", "limit_value": 10}])
    body = env.client.get(f"{BASE}/rate-limits", params={"source": "anthropic"}).json()
    assert body["peak_pct"] is None
    assert {(l["scope"], l["workspace_id"], l["limit"]) for l in body["limits"]} == {("org", None, 50), ("workspace", "wrkspc_x", 10)}
