"""Telemetry tests — schema migration, capture, rollups, scope filters.

All tests use ``tmp_path`` so the real telemetry SQLite is never
touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dev_team.telemetry import capture as capture_mod
from dev_team.telemetry import store as store_mod
from dev_team.telemetry.capture import (
    TelemetryWrappedTeam,
    capture_event,
    register_agent_hooks,
    register_team_hooks,
    task_hash,
)
from dev_team.telemetry.rollups import get_agent_metrics, get_metrics
from dev_team.telemetry.store import (
    CURRENT_SCHEMA_VERSION,
    applied_schema_versions,
    connect,
    set_db_path,
)


@pytest.fixture(autouse=True)
def isolate_db(tmp_path):
    """Each test gets a fresh telemetry DB under tmp_path."""
    set_db_path(tmp_path / "telemetry.sqlite")
    yield
    # Reset to the module default to avoid suite-wide leakage.
    from pathlib import Path

    default = (
        Path(capture_mod.__file__).resolve().parent.parent
        / "memory"
        / "store"
        / "telemetry.sqlite"
    )
    set_db_path(default)


def _event(**overrides):
    base = {
        "config_name": "default",
        "agent_name": "leader",
        "turn_index": 1,
        "input_tokens": 100,
        "output_tokens": 50,
        "total_cost_usd": 0.0123,
        "latency_ms": 250,
        "outcome": "ok",
        "output_chars": 200,
    }
    base.update(overrides)
    return base


# -- schema migration -------------------------------------------------


def test_schema_applied_on_first_capture():
    capture_event(_event())

    versions = applied_schema_versions()
    assert versions == [CURRENT_SCHEMA_VERSION]


def test_schema_idempotent_on_repeated_connect():
    # Multiple connects should leave a single schema_version row.
    with connect():
        pass
    with connect():
        pass

    versions = applied_schema_versions()
    assert versions == [CURRENT_SCHEMA_VERSION]


def test_indexes_present_after_migration():
    capture_event(_event())
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_events_%'"
        ).fetchall()
    names = sorted(r[0] for r in rows)
    assert names == ["idx_events_agent", "idx_events_project", "idx_events_timestamp"]


# -- capture_event ----------------------------------------------------


def test_capture_event_inserts_row():
    capture_event(
        _event(
            project="alpha",
            sub_team="design_review_team",
            tool_calls=[{"name": "grep", "args": {"pattern": "x"}, "latency_ms": 10}],
            task_hash="abc123",
        )
    )

    with connect() as conn:
        row = conn.execute("SELECT * FROM events").fetchone()
    assert row["agent_name"] == "leader"
    assert row["project"] == "alpha"
    assert row["sub_team"] == "design_review_team"
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50
    assert row["total_cost_usd"] == pytest.approx(0.0123)
    # tool_calls is JSON-encoded text
    assert "grep" in row["tool_calls"]
    assert row["task_hash"] == "abc123"


def test_capture_event_missing_required_raises():
    with pytest.raises(ValueError, match="missing required fields"):
        capture_event({"agent_name": "leader"})


def test_capture_event_auto_timestamps_when_missing():
    capture_event(_event())
    with connect() as conn:
        ts = conn.execute("SELECT timestamp FROM events").fetchone()[0]
    # ISO 8601 UTC has a 'T' separator and ends in +00:00 (or 'Z'-shape).
    assert "T" in ts


def test_task_hash_is_stable():
    a = task_hash("rebuild auth")
    b = task_hash("rebuild auth")
    c = task_hash("rebuild billing")
    assert a == b
    assert a != c


# -- rollups: global --------------------------------------------------


def test_get_metrics_empty_db():
    metrics = get_metrics()
    assert metrics["total_events"] == 0
    assert metrics["total_cost_usd"] == 0.0
    assert metrics["agents"] == {}


def test_get_metrics_aggregates_across_agents():
    capture_event(_event(agent_name="leader", input_tokens=100, output_tokens=50, total_cost_usd=0.01))
    capture_event(_event(agent_name="leader", input_tokens=200, output_tokens=100, total_cost_usd=0.02))
    capture_event(_event(agent_name="architect", input_tokens=50, output_tokens=25, total_cost_usd=0.005))

    metrics = get_metrics()
    assert metrics["total_events"] == 3
    assert metrics["total_input_tokens"] == 350
    assert metrics["total_output_tokens"] == 175
    assert metrics["total_cost_usd"] == pytest.approx(0.035)

    assert metrics["agents"]["leader"]["events"] == 2
    assert metrics["agents"]["leader"]["cost"] == pytest.approx(0.03)
    assert metrics["agents"]["architect"]["events"] == 1


def test_get_metrics_scope_project_filters():
    capture_event(_event(project="alpha"))
    capture_event(_event(project="alpha"))
    capture_event(_event(project="beta"))

    alpha = get_metrics(scope="alpha")
    assert alpha["total_events"] == 2

    beta = get_metrics(scope="beta")
    assert beta["total_events"] == 1


def test_get_metrics_scope_last_n_days_filters():
    # Insert one recent + one old event by setting timestamps directly.
    now = datetime.now(timezone.utc)
    recent_ts = now.isoformat()
    old_ts = (now - timedelta(days=30)).isoformat()

    capture_event(_event(timestamp=recent_ts))
    capture_event(_event(timestamp=old_ts))

    last_7 = get_metrics(scope="last_7_days")
    assert last_7["total_events"] == 1

    last_60 = get_metrics(scope="last_60_days")
    assert last_60["total_events"] == 2


# -- rollups: per-agent ----------------------------------------------


def test_get_agent_metrics_empty_db():
    out = get_agent_metrics("leader")
    assert out["agent"] == "leader"
    assert out["events"] == 0
    assert out["total_cost_usd"] == 0.0
    assert out["avg_latency_ms"] is None
    assert out["success_rate"] is None
    assert out["tool_call_distribution"] == {}


def test_get_agent_metrics_counts_and_cost():
    for i in range(3):
        capture_event(_event(agent_name="leader", latency_ms=100 + i * 100, total_cost_usd=0.01))
    capture_event(_event(agent_name="other", total_cost_usd=999.0))

    out = get_agent_metrics("leader")
    assert out["events"] == 3
    assert out["total_cost_usd"] == pytest.approx(0.03)
    assert out["avg_latency_ms"] == pytest.approx(200.0)


def test_get_agent_metrics_success_rate():
    capture_event(_event(agent_name="leader", outcome="ok"))
    capture_event(_event(agent_name="leader", outcome="ok"))
    capture_event(_event(agent_name="leader", outcome="error"))
    capture_event(_event(agent_name="leader", outcome="timeout"))

    out = get_agent_metrics("leader")
    assert out["events"] == 4
    assert out["success_rate"] == pytest.approx(0.5)


def test_get_agent_metrics_tool_call_distribution():
    capture_event(
        _event(
            agent_name="leader",
            tool_calls=[
                {"name": "grep", "args": {}, "latency_ms": 5},
                {"name": "read", "args": {}, "latency_ms": 5},
            ],
        )
    )
    capture_event(
        _event(
            agent_name="leader",
            tool_calls=[
                {"name": "grep", "args": {}, "latency_ms": 5},
            ],
        )
    )

    out = get_agent_metrics("leader")
    assert out["tool_call_distribution"] == {"grep": 2, "read": 1}


def test_get_agent_metrics_scope_last_n_days():
    now = datetime.now(timezone.utc)
    capture_event(_event(agent_name="leader", timestamp=now.isoformat()))
    capture_event(
        _event(agent_name="leader", timestamp=(now - timedelta(days=30)).isoformat())
    )

    last_7 = get_agent_metrics("leader", scope="last_7_days")
    assert last_7["events"] == 1


def test_get_agent_metrics_scope_project():
    capture_event(_event(agent_name="leader", project="alpha"))
    capture_event(_event(agent_name="leader", project="beta"))

    out = get_agent_metrics("leader", scope="alpha")
    assert out["events"] == 1


# -- agno wiring ------------------------------------------------------


class _FakeResponse:
    def __init__(self, text="hello world", inp=10, out=5, cost=0.001, tool_calls=None):
        self.content = text

        class _Metrics:
            input_tokens = inp
            output_tokens = out
            total_cost = cost

        self.metrics = _Metrics()
        self.tool_calls = tool_calls


class _FakeTeam:
    def __init__(self, response=None, raise_exc=None):
        self.response = response if response is not None else _FakeResponse()
        self.raise_exc = raise_exc
        self.run_call_count = 0

    def run(self, task, **kwargs):
        self.run_call_count += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


class _FakeAgent:
    def __init__(self, response=None):
        self.response = response if response is not None else _FakeResponse()

    def run(self, task, **kwargs):
        return self.response


def test_register_team_hooks_captures_one_event_per_run():
    team = _FakeTeam()
    wrapped = register_team_hooks(
        team, config_name="default", project="alpha", agent_name="leader"
    )

    wrapped.run("task one")
    wrapped.run("task two")

    metrics = get_metrics(scope="alpha")
    assert metrics["total_events"] == 2
    assert metrics["agents"]["leader"]["events"] == 2


def test_register_team_hooks_records_error_outcome():
    team = _FakeTeam(raise_exc=RuntimeError("boom"))
    wrapped = register_team_hooks(team, config_name="default", agent_name="leader")

    with pytest.raises(RuntimeError, match="boom"):
        wrapped.run("failing task")

    out = get_agent_metrics("leader")
    assert out["events"] == 1
    assert out["success_rate"] == 0.0


def test_register_team_hooks_forwards_attrs():
    """Wrapper must be drop-in: untouched attrs forward to the team."""
    team = _FakeTeam()
    team.name = "dev_team"
    wrapped = register_team_hooks(team, config_name="default", agent_name="leader")

    assert wrapped.name == "dev_team"


def test_register_agent_hooks_is_idempotent():
    agent = _FakeAgent()
    register_agent_hooks(agent, agent_name="architect", config_name="default")
    first = agent.run

    register_agent_hooks(agent, agent_name="architect", config_name="default")
    second = agent.run

    assert first is second


def test_register_agent_hooks_captures_per_turn():
    agent = _FakeAgent()
    register_agent_hooks(
        agent, agent_name="architect", config_name="default", project="alpha"
    )

    agent.run("design a thing")
    agent.run("design another")
    agent.run("design a third")

    out = get_agent_metrics("architect")
    assert out["events"] == 3
    assert out["input_tokens"] == 30  # 3 × 10
    assert out["output_tokens"] == 15  # 3 × 5


def test_telemetry_wrapped_team_class_directly():
    team = _FakeTeam()
    wrapped = TelemetryWrappedTeam(
        team, config_name="default", agent_name="leader", project="alpha"
    )
    wrapped.run("a task")

    out = get_agent_metrics("leader", scope="alpha")
    assert out["events"] == 1
