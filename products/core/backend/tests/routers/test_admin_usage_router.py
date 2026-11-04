"""`/api/admin/usage/{dev,machine,jobs,fx}` -- platform-admin reads of public.dev_telemetry_* + fx_rates.

Real auth (strict 401 / 403); only the trusted DB + session user come through dependency_overrides.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.trusted_auth import get_session_user, get_trusted_db
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, make_ctx, seed_users

P = {"from": "2026-11-01T00:00:00+00:00", "to": "2026-11-02T00:00:00+00:00"}
URLS = ["/api/admin/usage/dev", "/api/admin/usage/machine", "/api/admin/usage/jobs", "/api/admin/usage/fx"]


def _claude(bucket, session, agent, model, cost, **kw):
    return {
        "host": "mac", "bucket": bucket, "session_id": session, "agent_id": agent, "project": "noc", "model": model,
        "requests": 2, "input_tokens": 10, "output_tokens": 5, "thinking_tokens": 1, "cache_read_tokens": 100,
        "cache_write_tokens": 50, "cost_usd": cost, "prompt_chars": 7, "output_chars": 9, "tool_result_chars": 3,
        "tool_calls": 1, **kw,
    }


def _job(ts, job, event, phase, dur, exit_code=0, **kw):
    kind, target = job.split(":")
    return {
        "host": "mac", "ts": ts, "job": job, "kind": kind, "target": target, "event": event, "phase": phase,
        "admitted": event == "ran", "waited_s": 1.0, "duration_s": dur, "children_peak_rss_mb": 500.0,
        "exit_code": exit_code, "metrics": kw.get("metrics", {}),
    }


@pytest.fixture
def env():
    _ctx, fakes = make_ctx()
    seed_users(fakes.db)
    db = fakes.db
    db.set_table_data("dev_telemetry_claude", [
        _claude("2026-11-01T10:00:00+00:00", "s1", "", "opus", 1.0),
        _claude("2026-11-01T10:05:00+00:00", "s1", "a1", "sonnet", 0.5),
        _claude("2026-11-01T11:00:00+00:00", "s2", "", "opus", 3.0, project="other"),
    ])
    db.set_table_data("dev_telemetry_os", [
        {"host": "mac", "ts": "2026-11-01T10:00:00+00:00", "phase": "build", "overloaded": False, "busy_slots": 1,
         "cpu_idle_pct": 60.0, "reclaimable_mb": 1000, "swapout_per_s": 0.0, "load_1m": 2.0, "claude_sessions": 2},
        {"host": "mac", "ts": "2026-11-01T10:00:30+00:00", "phase": "build", "overloaded": True, "busy_slots": 2,
         "cpu_idle_pct": 40.0, "reclaimable_mb": 500, "swapout_per_s": None, "load_1m": 4.0, "claude_sessions": 2},
        {"host": "mac", "ts": "2026-11-01T12:00:00+00:00", "phase": "trial", "overloaded": None, "busy_slots": None,
         "cpu_idle_pct": None, "reclaimable_mb": None, "swapout_per_s": None, "load_1m": None, "claude_sessions": None},
    ])
    db.set_table_data("dev_telemetry_marks", [
        {"host": "mac", "ts": "2026-11-01T11:30:00+00:00", "kind": "phase_change", "label": "trial", "payload": {"a": 1}},
    ])
    db.set_table_data("dev_telemetry_jobs", [
        _job("2026-11-01T10:00:00+00:00", "pytest:core", "ran", "build", 100.0, metrics={"false_red_count": 1}),
        _job("2026-11-01T10:10:00+00:00", "pytest:core", "ran", "build", 120.0),
        _job("2026-11-01T12:00:00+00:00", "pytest:core", "ran", "trial", 220.0, exit_code=1,
             metrics={"false_red_count": 2, "real_red_count": 1}),
        _job("2026-11-01T12:30:00+00:00", "vite:core", "not_admitted", "trial", None, exit_code=None),
    ])
    db.set_table_data("fx_rates", [
        {"pair": "USD/BRL", "quote_date": "2026-10-30", "rate": 5.4, "created_at": "2026-10-30T20:00:00+00:00"},
        {"pair": "USD/BRL", "quote_date": "2026-11-03", "rate": 5.5, "created_at": "2026-11-03T20:00:00+00:00"},
    ])
    state = SimpleNamespace(db=db, user=ADMIN_USER)

    async def session_user():
        return SimpleNamespace(id=state.user)

    app.dependency_overrides[get_trusted_db] = lambda: db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


@pytest.mark.parametrize("url", URLS)
def test_no_token_is_strictly_401(url):
    app.dependency_overrides.clear()
    assert TestClient(app).get(url).status_code == 401


@pytest.mark.parametrize("url", URLS)
def test_non_platform_admin_is_strictly_403(env, url):
    env.user = MEMBER_USER
    assert env.client.get(url, params=P).status_code == 403


@pytest.mark.parametrize("url", URLS)
def test_inverted_window_is_400(env, url):
    assert env.client.get(url, params={"from": P["to"], "to": P["from"]}).status_code == 400


def test_dev_shapes_and_totals(env):
    body = env.client.get(URLS[0], params=P).json()
    assert body["window"]["hours"] == pytest.approx(24)
    assert body["freshness"]["dev_telemetry_claude"] is None or isinstance(body["freshness"]["dev_telemetry_claude"], str)
    t = body["totals"]
    assert t["requests"] == 6 and t["cost_usd"] == pytest.approx(4.5)
    assert t["cost_usd_per_hour"] == pytest.approx(4.5 / 24, abs=1e-3)
    assert [s["session_id"] for s in body["per_session"]] == ["s2", "s1"]  # cost desc
    s1 = body["per_session"][1]
    assert s1["subagents"] == 1 and s1["first"] <= s1["last"] and s1["cost_usd"] == pytest.approx(1.5)
    assert {(a["session_id"], a["agent_id"]) for a in body["per_agent"]} == {("s1", ""), ("s1", "a1"), ("s2", "")}
    assert [m["model"] for m in body["per_model"]] == ["opus", "sonnet"]
    assert [p["requests"] for p in body["series"]] == [4, 2]
    assert len(body["series"]) == 2
    assert body["filters_available"] == {"hosts": ["mac"], "projects": ["noc", "other"], "models": ["opus", "sonnet"]}


def test_dev_filters_and_main_agent(env):
    main = env.client.get(URLS[0], params={**P, "agent_id": "main"}).json()
    assert main["totals"]["cost_usd"] == pytest.approx(4.0)
    sub = env.client.get(URLS[0], params={**P, "agent_id": "a1"}).json()
    assert sub["totals"]["cost_usd"] == pytest.approx(0.5)
    one = env.client.get(URLS[0], params={**P, "session_id": "s1", "model": "opus"}).json()
    assert one["totals"]["cost_usd"] == pytest.approx(1.0)
    assert one["filters_available"]["models"] == ["opus", "sonnet"]  # dropdowns stay full


def test_dev_empty_is_null_not_zero(env):
    body = env.client.get(URLS[0], params={**P, "host": "nope"}).json()
    assert body["totals"]["cost_usd"] is None and body["totals"]["requests"] is None
    assert body["per_session"] == [] and body["series"] == []


def test_machine_series_nulls_and_marks(env):
    body = env.client.get(URLS[1], params=P).json()
    assert len(body["series"]) <= 720
    first = body["series"][0]
    assert first["cpu_idle_pct"] == pytest.approx(50.0) and first["overloaded"] is True and first["phase"] == "build"
    assert first["swapout_per_s"] == 0.0  # a null sample is ignored, not zeroed
    last = body["series"][-1]
    assert last["cpu_idle_pct"] is None and last["overloaded"] is None and last["phase"] == "trial"
    assert body["marks"] == [{"ts": "2026-11-01T11:30:00+00:00", "kind": "phase_change", "label": "trial", "payload": {"a": 1}}]
    assert body["filters_available"] == {"hosts": ["mac"], "phases": ["build", "trial"]}
    only = env.client.get(URLS[1], params={**P, "phase": "trial"}).json()
    assert len(only["series"]) == 1


def test_machine_caps_points(env):
    big = [{"host": "mac", "ts": f"2026-11-01T{h:02d}:{m:02d}:00+00:00", "phase": "build", "overloaded": False,
            "busy_slots": 0, "cpu_idle_pct": 50.0, "reclaimable_mb": 1, "swapout_per_s": 0.0, "load_1m": 1.0,
            "claude_sessions": 1} for h in range(24) for m in range(0, 60, 1)]
    env.db.set_table_data("dev_telemetry_os", big)
    assert len(env.client.get(URLS[1], params=P).json()["series"]) <= 720


def test_jobs_report_maths(env):
    body = env.client.get(URLS[2], params=P).json()
    assert [j["ts"] for j in body["jobs"]] == sorted((j["ts"] for j in body["jobs"]), reverse=True)
    failing = next(j for j in body["jobs"] if j["exit_code"] == 1)
    assert failing["false_red_count"] == 2 and failing["real_red_count"] == 1 and failing["peak_rss_mb"] == 500.0
    plain = next(j for j in body["jobs"] if j["duration_s"] == 120.0)
    assert plain["false_red_count"] is None and plain["real_red_count"] is None  # absent key = null
    phases = {p["phase"]: p for p in body["per_phase"]}
    assert phases["build"]["runs"] == 2 and phases["build"]["mean_duration_s"] == 110.0
    assert phases["build"]["fail_rate"] == 0.0 and phases["build"]["false_red_total"] == 1
    assert phases["trial"]["runs"] == 1 and phases["trial"]["not_admitted"] == 1
    assert phases["trial"]["fail_rate"] == 1.0 and phases["trial"]["false_red_total"] == 2
    assert phases["build"]["jobs_per_hour"] is not None
    sd = body["slowdown"]
    assert sd == [{"kind_target": "pytest:core", "phase": "trial", "mean_duration_s": 220.0,
                   "baseline_phase": "build", "baseline_mean_s": 110.0, "factor": 2.0}]
    assert body["filters_available"] == {"hosts": ["mac"], "phases": ["build", "trial"], "kinds": ["pytest", "vite"]}


def test_jobs_filters(env):
    only = env.client.get(URLS[2], params={**P, "event": "not_admitted"}).json()
    assert [j["job"] for j in only["jobs"]] == ["vite:core"]
    assert env.client.get(URLS[2], params={**P, "phase": "build", "kind": "pytest", "target": "core"}).json()["jobs"].__len__() == 2


def test_fx_latest_and_missing(env):
    body = env.client.get(URLS[3]).json()
    assert body["usd_brl"] == 5.5 and body["date"] == "2026-11-03"
    assert body["freshness"]["fx_rates"] == "2026-11-03T20:00:00+00:00"
    env.db.set_table_data("fx_rates", [])
    empty = env.client.get(URLS[3]).json()
    assert empty["usd_brl"] is None and empty["date"] is None
