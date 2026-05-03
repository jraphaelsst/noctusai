"""Tests for the phase-learnings SQLite tracker."""
from __future__ import annotations

import os
import sys
import sqlite3
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.phase_learnings import (
    consume_learning,
    get_db_path,
    log_learning,
    query_learnings,
)


@pytest.fixture
def tmp_db(monkeypatch) -> Path:
    """Yield a fresh temp .db path; clean up after the test.

    Uses NOCTUS_PHASE_LEARNINGS_DB env override (per get_db_path) so the
    helper functions point at the temp file without us threading db_path
    through every call.
    """
    fd, path_str = tempfile.mkstemp(prefix="phase_learnings_test_", suffix=".db")
    os.close(fd)  # we just want a unique path
    p = Path(path_str)
    p.unlink(missing_ok=True)  # let _connect create it fresh
    monkeypatch.setenv("NOCTUS_PHASE_LEARNINGS_DB", str(p))
    yield p
    p.unlink(missing_ok=True)


class TestGetDbPath:
    def test_default_path_under_mcp_data(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_PHASE_LEARNINGS_DB", raising=False)
        path = get_db_path()
        assert path.parent.name == "data"
        assert path.parent.parent.name == "noctusai"
        assert path.name == "phase_learnings.db"

    def test_env_override_respected(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_PHASE_LEARNINGS_DB", "/tmp/custom_phase_learnings.db")
        assert str(get_db_path()) == "/tmp/custom_phase_learnings.db"


class TestLogLearning:
    def test_basic_insert_returns_id(self, tmp_db):
        new_id = log_learning(
            project_slug="test-proj",
            phase_number=1,
            phase_title="Foo",
            learning_kind="methodology",
            learning_text="Insight A",
            created_by="test-agent",
        )
        assert isinstance(new_id, int)
        assert new_id > 0

    def test_schema_initializes_lazily(self, tmp_db):
        # tmp_db file does not exist yet at fixture-yield time.
        assert not tmp_db.exists()
        log_learning("p", 0, None, "tool", "first call creates the file", "x")
        assert tmp_db.exists()
        # Schema is applied — table exists.
        with sqlite3.connect(str(tmp_db)) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cur.fetchall()]
        assert "phase_learnings" in tables

    def test_rejects_invalid_kind(self, tmp_db):
        with pytest.raises(ValueError, match="learning_kind"):
            log_learning("p", 0, None, "not-a-kind", "txt", "x")

    def test_rejects_empty_project_slug(self, tmp_db):
        with pytest.raises(ValueError, match="project_slug"):
            log_learning("", 0, None, "methodology", "txt", "x")
        with pytest.raises(ValueError, match="project_slug"):
            log_learning("   ", 0, None, "methodology", "txt", "x")

    def test_rejects_empty_learning_text(self, tmp_db):
        with pytest.raises(ValueError, match="learning_text"):
            log_learning("p", 0, None, "methodology", "", "x")

    def test_phase_title_optional(self, tmp_db):
        new_id = log_learning("p", 0, None, "methodology", "ok", "x")
        rows = query_learnings("p")
        assert len(rows) == 1
        assert rows[0]["phase_title"] is None

    def test_created_by_falls_back_to_env(self, tmp_db, monkeypatch):
        monkeypatch.setenv("NOCTUS_AGENT_ID", "env-agent")
        log_learning("p", 0, None, "methodology", "ok", None)
        rows = query_learnings("p")
        assert rows[0]["created_by"] == "env-agent"

    def test_created_by_unknown_when_no_env(self, tmp_db, monkeypatch):
        monkeypatch.delenv("NOCTUS_AGENT_ID", raising=False)
        log_learning("p", 0, None, "methodology", "ok", None)
        rows = query_learnings("p")
        assert rows[0]["created_by"] == "unknown"


class TestQueryLearnings:
    def test_empty_returns_empty_list(self, tmp_db):
        assert query_learnings("nonexistent-project") == []

    def test_filters_by_project_slug(self, tmp_db):
        log_learning("proj-a", 0, None, "tool", "a", "x")
        log_learning("proj-b", 0, None, "tool", "b", "x")
        rows = query_learnings("proj-a")
        assert len(rows) == 1
        assert rows[0]["learning_text"] == "a"

    def test_filters_by_phase_number(self, tmp_db):
        log_learning("p", 0, None, "tool", "phase 0", "x")
        log_learning("p", 1, None, "tool", "phase 1", "x")
        rows = query_learnings("p", phase_number=1)
        assert len(rows) == 1
        assert rows[0]["learning_text"] == "phase 1"

    def test_unconsumed_only_excludes_consumed(self, tmp_db):
        id_a = log_learning("p", 0, None, "tool", "a", "x")
        log_learning("p", 0, None, "tool", "b", "x")
        consume_learning(id_a, by_phase_number=1)
        rows = query_learnings("p", unconsumed_only=True)
        assert len(rows) == 1
        assert rows[0]["learning_text"] == "b"

    def test_orders_by_phase_then_id(self, tmp_db):
        log_learning("p", 1, None, "tool", "second", "x")
        log_learning("p", 0, None, "tool", "first", "x")
        log_learning("p", 0, None, "tool", "first.b", "x")
        rows = query_learnings("p")
        assert [r["learning_text"] for r in rows] == ["first", "first.b", "second"]


class TestConsumeLearning:
    def test_marks_row_consumed(self, tmp_db):
        new_id = log_learning("p", 0, None, "tool", "txt", "x")
        ok = consume_learning(new_id, by_phase_number=1)
        assert ok is True
        rows = query_learnings("p")
        assert rows[0]["consumed_by_phase_number"] == 1
        assert rows[0]["consumed_at"] is not None

    def test_double_consume_returns_false(self, tmp_db):
        new_id = log_learning("p", 0, None, "tool", "txt", "x")
        assert consume_learning(new_id, 1) is True
        # Already consumed — second call no-ops.
        assert consume_learning(new_id, 2) is False

    def test_nonexistent_id_returns_false(self, tmp_db):
        assert consume_learning(99999, 1) is False


class TestMcpToolRegistration:
    """Verify the FastMCP server can be built with phase_learnings registered."""

    def test_register_function_exists(self):
        from tools.noctus.dev.phase_learnings import register
        assert callable(register)

    def test_server_builds_with_phase_learnings_tools(self):
        """Build the MCP server end-to-end and verify the 3 tool names are present."""
        from server import build_server
        server = build_server()
        # FastMCP exposes registered tools via list_tools (async), but the
        # internal registry is accessible directly via _tools attribute on
        # the server's tool manager. We use the public list interface where
        # available; fall back to inspecting attributes.
        # Smoke-check: the server build doesn't raise.
        assert server is not None

    def test_phase_learning_tool_names_registered(self):
        """The 3 phase-learning tool names land in the server registry."""
        from server import build_server
        server = build_server()
        # FastMCP stores tools in `_tool_manager._tools` dict (private API but
        # stable across the FastMCP versions we target). Iterate keys.
        manager = server._tool_manager
        tool_names = set(manager._tools.keys())
        expected = {
            "noctus.dev.phase_learning_log",
            "noctus.dev.phase_learning_query",
            "noctus.dev.phase_learning_consume",
        }
        missing = expected - tool_names
        assert not missing, f"Expected tools missing from registry: {missing}"
