"""Regression tests for dispatch_token_log."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import dispatch_token_log as dtl  # noqa: E402


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    target = tmp_path / "project-history" / "dispatch-budget.ndjson"
    monkeypatch.setattr(dtl, "_ledger_path", lambda: target)
    return target


class TestLogCompletion:
    def test_writes_valid_entry(self, tmp_ledger):
        r = dtl.log_completion("test-slug", "backend-engineer", 10.0,
                               estimated_tokens=100_000, outcome="landed",
                               notes="clean")
        assert r["ok"]
        assert r["entry"]["slug"] == "test-slug"
        assert r["entry"]["duration_minutes"] == 10.0
        assert r["entry"]["estimated_tokens"] == 100_000
        assert r["entry"]["outcome"] == "landed"

    def test_invalid_outcome_rejected(self, tmp_ledger):
        r = dtl.log_completion("x", "agent", 1.0, outcome="not-real")
        assert r["ok"] is False
        assert "outcome must be one of" in r["error"]

    def test_empty_slug_rejected(self, tmp_ledger):
        r = dtl.log_completion("", "agent", 1.0)
        assert r["ok"] is False
        assert "slug" in r["error"]

    def test_negative_duration_rejected(self, tmp_ledger):
        r = dtl.log_completion("x", "agent", -1.0)
        assert r["ok"] is False
        assert "duration_minutes" in r["error"]


class TestSummary:
    def test_empty_returns_zeros(self, tmp_ledger):
        r = dtl.summary()
        assert r["ok"]
        assert r["total_dispatches"] == 0
        assert r["landed_rate"] == 0.0

    def test_aggregates_correctly(self, tmp_ledger):
        dtl.log_completion("a", "backend-engineer", 5.0, estimated_tokens=50_000, outcome="landed")
        dtl.log_completion("b", "backend-engineer", 10.0, estimated_tokens=100_000, outcome="landed")
        dtl.log_completion("c", "backend-engineer", 15.0, estimated_tokens=150_000, outcome="failed")
        r = dtl.summary()
        assert r["total_dispatches"] == 3
        assert r["by_outcome"]["landed"] == 2
        assert r["by_outcome"]["failed"] == 1
        assert r["landed_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert r["total_estimated_tokens"] == 300_000
        be = r["by_agent"]["backend-engineer"]
        assert be["dispatches"] == 3
        assert be["avg_minutes"] == pytest.approx(10.0)

    def test_filter_by_agent(self, tmp_ledger):
        dtl.log_completion("a", "backend-engineer", 5.0, outcome="landed")
        dtl.log_completion("b", "frontend-engineer", 5.0, outcome="landed")
        r = dtl.summary(agent="backend-engineer")
        assert r["total_dispatches"] == 1
