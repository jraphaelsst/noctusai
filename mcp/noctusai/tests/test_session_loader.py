"""Adapter tests for `mcp/noctusai/session_loader.py`.

Hand-built JSONL strings rather than recorded sessions. Fixture files
written to `tmp_path` per test — no monkey-patching of our own modules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from session_loader import (
    ToolResult,
    ToolUse,
    latest_session_path,
    load_session,
)


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def _assistant(*tool_uses: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(tool_uses)}}


def _user_tool_result(tool_use_id: str, content: str = "ok", is_error: bool = False) -> dict:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }
            ]
        },
    }


def _tu(tu_id: str, name: str, **inputs) -> dict:
    return {"type": "tool_use", "id": tu_id, "name": name, "input": inputs}


class TestLoadSession:
    def test_empty_file_returns_empty(self, tmp_path):
        p = _write_jsonl(tmp_path / "s.jsonl", [])
        assert load_session(p) == []

    def test_skips_non_assistant_user_records(self, tmp_path):
        records = [
            {"type": "permission-mode", "mode": "acceptEdits"},
            {"type": "system", "message": "hi"},
            {"type": "ai-title", "title": "x"},
            {"type": "queue-operation", "op": "drain"},
            {"type": "file-history-snapshot", "files": []},
        ]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        assert events == []

    def test_extracts_tool_use_from_assistant(self, tmp_path):
        records = [_assistant(_tu("toolu_1", "Read", file_path="/repo/x.py"))]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, ToolUse)
        assert e.id == "toolu_1"
        assert e.name == "Read"
        assert e.input == {"file_path": "/repo/x.py"}
        assert e.line_no == 1

    def test_extracts_tool_result_from_user(self, tmp_path):
        records = [_user_tool_result("toolu_1", content="hello world")]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, ToolResult)
        assert e.tool_use_id == "toolu_1"
        assert e.content_size == len("hello world")
        assert e.is_error is False

    def test_pairing_round_trip(self, tmp_path):
        records = [
            _assistant(_tu("toolu_a", "Bash", command="ls")),
            _user_tool_result("toolu_a", content="x" * 42),
            _assistant(_tu("toolu_b", "Edit", file_path="/repo/y.py", old_string="a", new_string="b")),
            _user_tool_result("toolu_b", content="ok"),
        ]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        uses = [e for e in events if isinstance(e, ToolUse)]
        results = [e for e in events if isinstance(e, ToolResult)]
        assert {u.id for u in uses} == {"toolu_a", "toolu_b"}
        assert {r.tool_use_id for r in results} == {"toolu_a", "toolu_b"}

    def test_records_order_preserved(self, tmp_path):
        records = [
            _assistant(_tu("toolu_1", "Read", file_path="/repo/a.py")),
            _user_tool_result("toolu_1"),
            _assistant(_tu("toolu_2", "Edit", file_path="/repo/a.py", old_string="x", new_string="y")),
            _user_tool_result("toolu_2"),
        ]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        line_nos = [e.line_no for e in events]
        assert line_nos == sorted(line_nos)

    def test_handles_list_content_in_tool_result(self, tmp_path):
        records = [
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": [{"type": "text", "text": "foo"}, {"type": "text", "text": "barbaz"}],
                            "is_error": False,
                        }
                    ]
                },
            }
        ]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        assert len(events) == 1
        assert events[0].content_size == len("foo") + len("barbaz")

    def test_is_error_flag_carries_through(self, tmp_path):
        records = [_user_tool_result("toolu_1", is_error=True)]
        events = load_session(_write_jsonl(tmp_path / "s.jsonl", records))
        assert events[0].is_error is True

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_session(tmp_path / "nope.jsonl")

    def test_malformed_jsonl_raises(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text("not json at all\n", encoding="utf-8")
        with pytest.raises(ValueError) as exc:
            load_session(p)
        assert "malformed JSONL" in str(exc.value)

    def test_session_with_only_metadata(self, tmp_path):
        records = [
            {"type": "permission-mode"},
            {"type": "system"},
            {"type": "ai-title"},
        ]
        assert load_session(_write_jsonl(tmp_path / "s.jsonl", records)) == []


class TestLatestSessionPath:
    def test_returns_newest_jsonl(self, tmp_path):
        old = tmp_path / "old.jsonl"
        new = tmp_path / "new.jsonl"
        old.write_text("{}\n")
        new.write_text("{}\n")
        # Make `old` actually older than `new`
        import os, time
        old_mtime = time.time() - 100
        os.utime(old, (old_mtime, old_mtime))
        assert latest_session_path(tmp_path) == new

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            latest_session_path(tmp_path / "missing")

    def test_empty_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            latest_session_path(tmp_path)
