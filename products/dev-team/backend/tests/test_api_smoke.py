"""Smoke tests for the dev-team product backend.

Each route is exercised end-to-end via FastAPI TestClient against the
mocked seed database. The engine wrap-surface (`app.services.dev_team_proxy`)
is the patch boundary — we never patch `dev_team.*` internals (that would
violate the "no monkey-patching of our own code" rule).

The migration parse test reads the SQL files and confirms they at least
parse with sqlparse.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_app_imports_without_error():
    """The simplest check: importing app.main does not crash. Validates
    create_product_app wiring + router imports + dependencies.py imports."""
    from app import main as _main
    assert _main.app is not None
    # Confirm the four routers landed on the app.
    paths = {route.path for route in _main.app.routes}
    # Sample a few paths — exact set depends on standard_routers.
    assert "/api/run" in paths
    assert "/api/agents" in paths
    assert "/api/agents/{name}/metrics" in paths
    assert "/api/metrics" in paths
    assert "/api/configs" in paths
    assert "/api/configs/{name}" in paths


# --------------------------------------------------------------------------
# /api/agents
# --------------------------------------------------------------------------


def test_get_agents_returns_11_snapshot_rows(client):
    """GET /api/agents returns the canonical 11 agents with snapshot fields."""
    fake_snapshot = [
        {
            "name": name,
            "model": "claude-opus-4-7",
            "last_24h_events": 0,
            "last_24h_cost": 0.0,
            "success_rate": 0.0,
        }
        for name in (
            "leader", "product_manager", "ux_designer", "solution_architect",
            "backend_engineer", "frontend_engineer", "devops_engineer",
            "security_engineer", "qa_engineer", "code_reviewer",
            "technical_writer",
        )
    ]
    with patch(
        "app.services.dev_team_proxy.list_agents_snapshot",
        return_value=fake_snapshot,
    ):
        resp = client.get("/api/agents")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["data"]) == 11
    assert body["data"][0]["name"] == "leader"


def test_get_agents_requires_auth(client):
    """No Authorization header → 401."""
    resp = client.raw().get("/api/agents")
    assert resp.status_code == 401


def test_get_agent_metrics_unknown_agent_404(client):
    """Unknown agent name → 404 (not 500). Validates the canonical roster
    guard in the agent metrics endpoint."""
    resp = client.get("/api/agents/not_a_real_agent/metrics")
    assert resp.status_code == 404


def test_get_agent_metrics_known_agent(client):
    """Known agent name → 200 with the engine's rollup."""
    fake_metrics = {
        "agent": "leader",
        "scope": None,
        "events": 42,
        "cost": 0.123456,
        "avg_latency": 1234,
        "success_rate": 0.95,
        "tool_call_distribution": {"web_search": 5, "code_edit": 12},
        "recent_events": [],
    }
    with patch(
        "app.services.dev_team_proxy.agent_metrics",
        return_value=fake_metrics,
    ):
        resp = client.get("/api/agents/leader/metrics")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["events"] == 42


# --------------------------------------------------------------------------
# /api/metrics
# --------------------------------------------------------------------------


def test_get_global_metrics(client):
    """GET /api/metrics returns the engine's snapshot."""
    fake = {"scope": None, "total_events": 0, "per_agent": {}}
    with patch(
        "app.services.dev_team_proxy.metrics_snapshot",
        return_value=fake,
    ):
        resp = client.get("/api/metrics")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total_events"] == 0


def test_get_metrics_requires_auth(client):
    resp = client.raw().get("/api/metrics")
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# /api/run
# --------------------------------------------------------------------------


def test_run_team_switch_not_flipped_passes_through(client):
    """When the engine returns a switch-not-flipped envelope, the API
    returns 200 with the envelope verbatim — it's design, not error."""
    fake_envelope = {
        "status": "switch-not-flipped",
        "summary": "ANTHROPIC_API_KEY is not set...",
        "task": "design a thing",
    }
    with patch(
        "app.services.dev_team_proxy.run_team",
        return_value=fake_envelope,
    ):
        resp = client.post("/api/run", json={"task": "design a thing"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["status"] == "switch-not-flipped"


def test_run_team_ok_envelope(client):
    """Real LLM-call shape returns 200 with the engine's full envelope."""
    fake_envelope = {
        "status": "ok",
        "summary": "Done.",
        "task": "ship it",
        "project": "demo",
        "config": "default",
    }
    with patch(
        "app.services.dev_team_proxy.run_team",
        return_value=fake_envelope,
    ):
        resp = client.post(
            "/api/run",
            json={"task": "ship it", "project": "demo", "config": "default"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "ok"


def test_run_team_validates_task_non_empty(client):
    """Empty task → 422 from Pydantic min_length=1."""
    resp = client.post("/api/run", json={"task": ""})
    assert resp.status_code == 422


def test_run_team_rejects_unknown_field_with_422(client):
    """StrictHttpModel migration guard — unknown keys 422 (was silently dropped).

    Pre-migration (`pydantic.BaseModel`, `extra="ignore"`) silently dropped
    `bogus_field`. Post-migration (`StrictHttpModel`, `extra="forbid"`) the
    schema rejects with 422 and names the offending `loc`. Defends against
    the silent-drop misroute class (`KB § PATTERNS/pydantic-strict-http.md`).
    """
    resp = client.post(
        "/api/run",
        json={"task": "ship it", "bogus_field": "should-422"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert any(
        "bogus_field" in str(err.get("loc", ""))
        for err in body.get("detail", [])
    )


def test_run_team_requires_auth(client):
    resp = client.raw().post("/api/run", json={"task": "x"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# /api/configs
# --------------------------------------------------------------------------


def test_list_configs_returns_summaries(client):
    """GET /api/configs returns one summary per known config."""
    with patch("app.services.dev_team_proxy.list_configs", return_value=["default"]), \
         patch(
             "app.services.dev_team_proxy.load_config",
             return_value={"agents": {"leader": {"model": "x", "provider": "y"}}},
         ):
        resp = client.get("/api/configs")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"][0]["name"] == "default"
    assert resp.json()["data"][0]["agent_count"] == 1


def test_get_one_config(client):
    fake_cfg = {"agents": {"leader": {"model": "claude-opus-4-7", "provider": "anthropic"}}}
    with patch("app.services.dev_team_proxy.load_config", return_value=fake_cfg):
        resp = client.get("/api/configs/default")
    assert resp.status_code == 200, resp.text
    assert "agents" in resp.json()["data"]


def test_patch_config_requires_at_least_one_field(client):
    """Empty patch (neither model nor provider) → 400."""
    resp = client.patch(
        "/api/configs/default",
        json={"agent_name": "leader"},
    )
    assert resp.status_code == 400


def test_patch_config_happy_path(client):
    """Valid patch → 200 with updated config returned."""
    updated = {"agents": {"leader": {"model": "claude-haiku-4-5", "provider": "anthropic"}}}
    with patch(
        "app.services.dev_team_proxy.set_agent_config",
        return_value=updated,
    ):
        resp = client.patch(
            "/api/configs/default",
            json={"agent_name": "leader", "model": "claude-haiku-4-5"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["agents"]["leader"]["model"] == "claude-haiku-4-5"


def test_patch_config_engine_not_ready_503(client):
    """When the engine's save_config raises NotImplementedError (D engineer
    hasn't shipped yet), surface as 503 not 500."""
    with patch(
        "app.services.dev_team_proxy.set_agent_config",
        side_effect=NotImplementedError("save_config not wired yet"),
    ):
        resp = client.patch(
            "/api/configs/default",
            json={"agent_name": "leader", "model": "x"},
        )
    assert resp.status_code == 503


def test_configs_require_auth(client):
    for path in ("/api/configs", "/api/configs/default"):
        resp = client.raw().get(path)
        assert resp.status_code == 401, f"{path} should be 401 without auth"


# --------------------------------------------------------------------------
# Migrations parse cleanly
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Rate-limit guard on POST /api/run (LLM-spend perimeter)
# --------------------------------------------------------------------------


def test_run_team_under_limit_returns_200(client):
    """A single POST /api/run well below the 10/minute limit returns 200.

    Sanity check that the @limiter.limit("10/minute") decorator does NOT
    short-circuit healthy traffic.
    """
    fake_envelope = {
        "status": "switch-not-flipped",
        "summary": "ANTHROPIC_API_KEY is not set...",
        "task": "ping",
    }
    with patch(
        "app.services.dev_team_proxy.run_team",
        return_value=fake_envelope,
    ):
        resp = client.post("/api/run", json={"task": "ping"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "switch-not-flipped"


def test_run_team_over_limit_returns_429(client):
    """Exceeding 10 POST /api/run requests/minute returns 429 from slowapi.

    Drives 11 calls in a tight loop against the in-memory limiter (the
    TestClient hits a single IP). The 11th must trip the limit. Asserts
    on .status_code per the status-code-assertion rule.
    """
    fake_envelope = {
        "status": "switch-not-flipped",
        "summary": "ANTHROPIC_API_KEY is not set...",
        "task": "spam",
    }
    # Reset limiter state to isolate this test from any prior call within
    # this client fixture's lifetime. The limiter is module-level.
    from app.rate_limit import limiter
    limiter.reset()

    with patch(
        "app.services.dev_team_proxy.run_team",
        return_value=fake_envelope,
    ):
        statuses = []
        for _ in range(11):
            resp = client.post("/api/run", json={"task": "spam"})
            statuses.append(resp.status_code)

    # First 10 should succeed, 11th should be 429.
    assert statuses[:10] == [200] * 10, f"first 10 expected 200, got {statuses[:10]}"
    assert statuses[10] == 429, f"11th call expected 429, got {statuses[10]}"


@pytest.mark.parametrize(
    "filename",
    ["0001_init_telemetry_events.sql", "0002_init_agent_config_overrides.sql"],
)
def test_migration_sql_parses(filename):
    """Each migration file at least parses via sqlparse — catches typos
    that would 5xx during deployment. Real schema execution lives behind
    the realdb marker."""
    sqlparse = pytest.importorskip("sqlparse")
    path = Path(__file__).parent.parent / "migrations" / filename
    assert path.exists(), f"migration missing: {path}"
    sql = path.read_text(encoding="utf-8")
    statements = sqlparse.parse(sql)
    # At least one parsed statement and none of them are empty.
    assert len(statements) > 0, f"no statements parsed in {filename}"
    for stmt in statements:
        assert str(stmt).strip(), f"empty statement in {filename}"
