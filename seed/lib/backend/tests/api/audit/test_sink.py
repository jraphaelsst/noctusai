"""``AuditSink`` — Fake/Real/factory + the overflow/failure contract.

``RealAuditSink``'s background flush loop is exercised with a tiny
``flush_interval_s`` (the tests don't want to sleep 2 real seconds) —
timing-sensitive but bounded well under pytest's default timeout.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from noctusai_lib.api.audit.sink import (
    FakeAuditSink,
    RealAuditSink,
    log_overflow_or_failure,
    make_audit_sink,
    overflow_or_failure_count,
)
from noctusai_lib.api.audit.types import AuditActor, AuditEntry


def _entry(**overrides) -> AuditEntry:
    defaults = dict(
        product="test-product",
        method="POST",
        route_template="/api/things/{id}",
        path_params={"id": "abc"},
        status=201,
        actor_kind="user",
        client_hint="Chrome",
        correlation_id="corr-1",
        duration_ms=12.3,
        actor=AuditActor(user_id="u1", org_id="o1", role="admin"),
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


class _FakeQuery:
    """Minimal ``.schema().table().insert().execute()`` chain."""

    def __init__(self, recorder: "_FakeAdmin", *, fail: bool) -> None:
        self._recorder = recorder
        self._fail = fail

    def insert(self, rows):
        self._recorder.inserted.append(rows)
        return self

    def execute(self):
        if self._fail:
            raise RuntimeError("boom: insert failed")
        return None


class _FakeAdmin:
    """Records every schema/table it was called with, per
    ``KB § PATTERNS/backend/admin-client-schema-pinning.md``'s
    "re-derive `.schema()` per call, never cache it" rule — asserting
    on ``schema_calls`` proves ``RealAuditSink`` follows it."""

    def __init__(self, *, fail: bool = False) -> None:
        self.inserted: list[list[dict]] = []
        self.schema_calls: list[str] = []
        self._fail = fail

    def schema(self, name: str):
        self.schema_calls.append(name)
        return self

    def table(self, name: str):
        self._table_name = name
        return _FakeQuery(self, fail=self._fail)


class TestFakeAuditSink:
    @pytest.mark.asyncio
    async def test_records_in_memory(self) -> None:
        sink = FakeAuditSink()
        entry = _entry()
        await sink.record(entry)
        assert sink.entries == [entry]

    @pytest.mark.asyncio
    async def test_drain_is_a_noop(self) -> None:
        sink = FakeAuditSink()
        await sink.record(_entry())
        await sink.drain()  # must not raise, must not clear
        assert len(sink.entries) == 1


class TestMakeAuditSink:
    def test_no_admin_client_returns_fake(self) -> None:
        assert isinstance(make_audit_sink(None), FakeAuditSink)

    def test_admin_client_present_returns_real(self) -> None:
        admin = _FakeAdmin()
        sink = make_audit_sink(lambda: admin)
        assert isinstance(sink, RealAuditSink)


class TestRealAuditSinkFlush:
    @pytest.mark.asyncio
    async def test_flushes_on_drain_without_waiting_for_timer(self) -> None:
        admin = _FakeAdmin()
        sink = RealAuditSink(lambda: admin, flush_interval_s=60, batch_size=50)
        await sink.record(_entry(correlation_id="c1"))
        await sink.record(_entry(correlation_id="c2"))
        await sink.drain()

        assert admin.schema_calls == ["public", "public"] or admin.schema_calls == ["public"]
        assert len(admin.inserted) == 1
        rows = admin.inserted[0]
        assert {r["details"]["correlation_id"] for r in rows} == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_flushes_on_short_timer_without_reaching_batch_size(self) -> None:
        admin = _FakeAdmin()
        sink = RealAuditSink(lambda: admin, flush_interval_s=0.05, batch_size=50)
        await sink.record(_entry())
        await asyncio.sleep(0.2)
        assert len(admin.inserted) == 1
        assert len(admin.inserted[0]) == 1
        await sink.drain()

    @pytest.mark.asyncio
    async def test_flushes_immediately_at_batch_size_without_waiting_for_timer(self) -> None:
        admin = _FakeAdmin()
        sink = RealAuditSink(lambda: admin, flush_interval_s=60, batch_size=3)
        for _ in range(3):
            await sink.record(_entry())
        # The background loop needs one scheduling tick to run — give it
        # a moment, but nowhere near the 60s timer.
        await asyncio.sleep(0.05)
        assert len(admin.inserted) == 1
        assert len(admin.inserted[0]) == 3
        await sink.drain()

    @pytest.mark.asyncio
    async def test_never_caches_a_schema_result(self) -> None:
        """Two separate flushes must each call `.schema("public")` fresh —
        never reuse a client object that already had `.schema()` mutated
        by a concurrent cross-schema caller."""
        admin = _FakeAdmin()
        sink = RealAuditSink(lambda: admin, flush_interval_s=60, batch_size=50)
        await sink.record(_entry())
        await sink.drain()
        await sink.record(_entry())
        await sink.drain()
        assert admin.schema_calls == ["public", "public"]


class TestRealAuditSinkOverflow:
    @pytest.mark.asyncio
    async def test_queue_full_reports_via_log_overflow_or_failure_never_swallows(self, capsys) -> None:
        admin = _FakeAdmin()
        sink = RealAuditSink(lambda: admin, max_queue=1, flush_interval_s=60, batch_size=50)
        before = overflow_or_failure_count()
        await sink.record(_entry(correlation_id="kept"))
        await sink.record(_entry(correlation_id="dropped"))  # queue full — the sink never blocks the request
        assert overflow_or_failure_count() == before + 1
        out = capsys.readouterr().out
        assert "audit_fallback" in out
        assert "queue_full" in out
        await sink.drain()

    @pytest.mark.asyncio
    async def test_write_failure_reports_per_entry_never_swallows(self, capsys) -> None:
        admin = _FakeAdmin(fail=True)
        sink = RealAuditSink(lambda: admin, flush_interval_s=60, batch_size=50)
        before = overflow_or_failure_count()
        await sink.record(_entry())
        await sink.record(_entry())
        await sink.drain()
        assert overflow_or_failure_count() == before + 2  # one report PER dropped entry
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
        payload = json.loads(lines[-1])
        assert payload["audit_fallback"] == "write_failed"


def test_log_overflow_or_failure_is_never_a_bare_pass(capsys) -> None:
    before = overflow_or_failure_count()
    log_overflow_or_failure(kind="test_kind", entry={"x": 1}, exc=ValueError("nope"))
    assert overflow_or_failure_count() == before + 1
    out = capsys.readouterr().out
    row = json.loads(out.strip().splitlines()[-1])
    assert row == {"audit_fallback": "test_kind", "entry": {"x": 1}}
