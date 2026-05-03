"""Tests for `noctusai_lib.domain.ai.tool_audit`.

Covers:
  - AuditRecord.to_row_kwargs round-trip
  - _safe_jsonable handles dict / non-serializable / Pydantic-like / None
  - make_audit_writer success path persists a row
  - make_audit_writer DB-failure path: logs WARNING + does NOT raise
  - make_audit_writer unknown-tool status path
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    _safe_jsonable,
    make_audit_writer,
    now_utc,
)


# ---------------------------------------------------------------------------
# Fakes — minimal SQLAlchemy-shaped stand-ins. The lib is product-agnostic;
# tests don't need a real engine.
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.added: list[Any] = []
        self.committed = 0
        self.rolled_back = 0
        self._fail_on = fail_on

    def add(self, row: Any) -> None:
        if self._fail_on == "add":
            raise RuntimeError("add boom")
        self.added.append(row)

    def commit(self) -> None:
        if self._fail_on == "commit":
            raise RuntimeError("commit boom")
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


@dataclass
class _FakeRow:
    tool_name: str
    status: str
    duration_ms: int
    started_at: datetime
    arguments: Any = None
    result: Any = None
    error: str | None = None
    correlation_id: str | None = None
    gpt_call_id: str | None = None
    tool_call_id: str | None = None
    conversation_id: str | None = None
    user_id: int | None = None


def _record(**overrides: Any) -> AuditRecord:
    base = dict(
        tool_name="echo_tool",
        status="success",
        duration_ms=12,
        started_at=datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc),
        arguments={"x": 1},
        result={"echo": {"x": 1}},
        correlation_id="corr-123",
        gpt_call_id="gpt-1",
        conversation_id="+5511999999999",
        user_id=42,
    )
    base.update(overrides)
    return AuditRecord(**base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_audit_record_to_row_kwargs_round_trip() -> None:
    rec = _record()
    kwargs = rec.to_row_kwargs()
    assert kwargs["tool_name"] == "echo_tool"
    assert kwargs["status"] == "success"
    assert kwargs["arguments"] == {"x": 1}
    assert kwargs["result"] == {"echo": {"x": 1}}
    assert kwargs["correlation_id"] == "corr-123"
    assert kwargs["user_id"] == 42


def test_safe_jsonable_dict_passes_through() -> None:
    assert _safe_jsonable({"x": 1, "y": [1, 2, 3]}) == {"x": 1, "y": [1, 2, 3]}


def test_safe_jsonable_none_passes_through() -> None:
    assert _safe_jsonable(None) is None


def test_safe_jsonable_pydantic_like_object_round_trips_via_default_str() -> None:
    # Pydantic models / dataclasses with __dict__ get coerced through
    # json.dumps(..., default=str). Plain dataclasses fall through default=str.
    class _Sentinel:
        def __repr__(self) -> str:
            return "Sentinel(value=42)"

    out = _safe_jsonable(_Sentinel())
    # default=str renders to its repr; round-trip parses to a string.
    assert out == "Sentinel(value=42)"


def test_safe_jsonable_falls_back_to_repr_for_unserializable() -> None:
    # Force a TypeError that even default=str can't fix — circular reference.
    a: dict = {}
    a["self"] = a
    out = _safe_jsonable(a)
    assert isinstance(out, dict)
    assert "_repr" in out


def test_make_audit_writer_success_path_persists_row() -> None:
    db = _FakeSession()
    writer = make_audit_writer(db, _FakeRow)

    writer(_record())

    assert len(db.added) == 1
    row = db.added[0]
    assert isinstance(row, _FakeRow)
    assert row.tool_name == "echo_tool"
    assert row.status == "success"
    assert row.arguments == {"x": 1}
    assert db.committed == 1
    assert db.rolled_back == 0


def test_make_audit_writer_failure_path_logs_and_swallows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = _FakeSession(fail_on="commit")
    writer = make_audit_writer(db, _FakeRow)

    with caplog.at_level(logging.WARNING, logger="noctusai_lib.domain.ai.tool_audit"):
        # Best-effort: this MUST NOT raise.
        writer(_record())

    assert db.rolled_back == 1
    assert any(
        "tool_call_audit write failed" in rec.message and rec.levelno == logging.WARNING
        for rec in caplog.records
    )


def test_make_audit_writer_unknown_tool_path() -> None:
    db = _FakeSession()
    writer = make_audit_writer(db, _FakeRow)

    rec = _record(
        tool_name="ghost_tool",
        status="unknown_tool",
        result=None,
        error="unknown_tool: ghost_tool",
    )
    writer(rec)

    assert len(db.added) == 1
    row = db.added[0]
    assert row.status == "unknown_tool"
    assert row.error == "unknown_tool: ghost_tool"
    assert row.result is None


def test_now_utc_returns_aware_datetime() -> None:
    n = now_utc()
    assert n.tzinfo is not None
    assert n.tzinfo.utcoffset(n) == timezone.utc.utcoffset(n)
