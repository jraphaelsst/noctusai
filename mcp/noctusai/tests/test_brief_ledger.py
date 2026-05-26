"""Regression tests for brief_ledger."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import brief_ledger as bl  # noqa: E402


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    target = tmp_path / ".claude" / "cache" / "brief-ledger.ndjson"
    monkeypatch.setattr(bl, "_ledger_path", lambda: target)
    return target


class TestAppend:
    def test_writes_to_ledger(self, tmp_ledger):
        r = bl.append("w2-e3-test", "backend-engineer",
                      ["mcp/foo.py"], "test brief", full_brief="full content")
        assert r["ok"]
        lines = tmp_ledger.read_text().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["slug"] == "w2-e3-test"
        assert entry["agent"] == "backend-engineer"
        assert entry["target_files"] == ["mcp/foo.py"]
        assert entry["content_hash"]
        assert "full_brief_excerpt" in entry

    def test_silent_on_failure_returns_error(self, tmp_path, monkeypatch):
        # Point at an unwritable location (root + read-only).
        unwritable = Path("/this/path/does/not/exist/cache.ndjson")
        monkeypatch.setattr(bl, "_ledger_path", lambda: unwritable)
        r = bl.append("x", "agent", None, "desc")
        # Should NOT crash; returns ok=False.
        assert r["ok"] is False


class TestQuery:
    def test_empty_ledger_returns_empty(self, tmp_ledger):
        assert bl.query() == []

    def test_filters_by_agent(self, tmp_ledger):
        bl.append("a", "backend-engineer", None, "x")
        bl.append("b", "frontend-engineer", None, "y")
        results = bl.query(agent="backend-engineer")
        assert len(results) == 1
        assert results[0]["agent"] == "backend-engineer"

    def test_filters_by_slug_substring(self, tmp_ledger):
        bl.append("backend-thing", "backend-engineer", None, "x")
        bl.append("frontend-thing", "frontend-engineer", None, "y")
        results = bl.query(slug_substring="backend")
        assert len(results) == 1
        assert "backend" in results[0]["slug"]

    def test_returns_newest_first(self, tmp_ledger):
        bl.append("a", "agent", None, "first")
        time.sleep(0.01)
        bl.append("b", "agent", None, "second")
        results = bl.query()
        assert results[0]["slug"] == "b"
        assert results[1]["slug"] == "a"


class TestListRecent:
    def test_limit_caps(self, tmp_ledger):
        for i in range(15):
            bl.append(f"s{i}", "agent", None, f"d{i}")
        assert len(bl.list_recent(limit=5)) == 5
