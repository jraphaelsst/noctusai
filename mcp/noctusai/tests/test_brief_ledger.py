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


class TestMissOutcomeDrift:
    def test_miss_writes_drift_with_resolve_when(self, tmp_ledger):
        calls = []
        def fake(**kw):
            calls.append(kw)
            return {"ok": True, "entry": {"ts": "t"}}
        r = bl.append("s1", "backend-engineer", None, "desc", outcome="miss", ai_logger=fake)
        assert r["ok"] and r["ai"]["ok"]
        assert calls[0]["kind"] == "drift" and calls[0]["agent"] == "backend-engineer"
        assert calls[0]["resolve_when"]

    def test_success_not_logged(self, tmp_ledger):
        calls = []
        bl.append("s2", "a", None, "d", outcome="landed", ai_logger=lambda **k: calls.append(k))
        bl.append("s3", "a", None, "d", ai_logger=lambda **k: calls.append(k))
        assert calls == []

    def test_logger_failure_surfaced(self, tmp_ledger):
        def boom(**kw):
            raise RuntimeError("x")
        r = bl.append("s4", "a", None, "d", outcome="rework", ai_logger=boom)
        assert r["ok"] and r["ai"]["ok"] is False and "x" in r["ai"]["error"]


class TestAppendFailureModes:
    def test_disk_failure_is_explicit_and_distinguishable(self, tmp_path, monkeypatch, caplog):
        blocker = tmp_path / "file"
        blocker.write_text("x")  # a file where a directory is needed -> OSError
        target = blocker / "sub" / "ledger.ndjson"
        monkeypatch.setattr(bl, "_ledger_path", lambda: target)
        with caplog.at_level("WARNING"):
            r = bl.append("x", "agent", None, "desc")
        assert r["ok"] is False and r["error_kind"] == "disk"
        assert str(target) in r["ledger_path"]
        assert any("disk failure" in m for m in caplog.messages)

    def test_pii_refusal_is_distinguishable_from_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bl, "_ledger_path", lambda: tmp_path / "b.ndjson")
        r = bl.append("s", "a", None, "reach me at joao.silva@gmail.com")
        assert r["ok"] is False and r["error_kind"] == "pii"
        assert "joao.silva" not in json.dumps(r)

    def test_programming_errors_propagate(self, tmp_ledger):
        with pytest.raises(TypeError):
            bl.append("s", "a", None, "d", meta=object())  # not JSON-serialisable
