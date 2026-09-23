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
    _derive_resource,
    _to_row,
    log_overflow_or_failure,
    make_audit_sink,
    overflow_or_failure_count,
    running_under_pytest,
)
from noctusai_lib.api.audit.types import AuditActor, AuditEntry


def _entry(**overrides) -> AuditEntry:
    defaults = dict(
        product_slug="test-product",
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


def test_running_under_pytest_is_true_in_this_process() -> None:
    # This file only runs under pytest — the obviously-true direction.
    assert running_under_pytest() is True


class TestMakeAuditSink:
    def test_no_admin_client_returns_fake(self) -> None:
        assert isinstance(make_audit_sink(None, force_real=True), FakeAuditSink)

    def test_admin_client_present_with_force_real_returns_real(self) -> None:
        """`force_real=True` is the deliberate escape hatch THIS test
        uses — without it, the pytest-safety default below always wins."""
        admin = _FakeAdmin()
        sink = make_audit_sink(lambda: admin, force_real=True)
        assert isinstance(sink, RealAuditSink)

    def test_defaults_to_fake_under_pytest_even_with_an_admin_client(self) -> None:
        """The pytest-safety default (2026-09-23 redirect): a product's
        `app.main` builds its sink at IMPORT time, before any per-test
        `unittest.mock.patch` on `DatabaseModule.get_core_client` is
        active — `make_audit_sink` refuses to hand back a `RealAuditSink`
        at all while running under pytest, regardless of
        `get_admin_client`, so a slow test can never reach a real DB
        through this factory by omission."""
        admin = _FakeAdmin()
        sink = make_audit_sink(lambda: admin)  # this test genuinely runs under pytest
        assert isinstance(sink, FakeAuditSink)


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
        # `correlation_id` (like every other captured field) is a
        # DEDICATED column now (migration 053) — `details` carries only
        # genuine extras, which this sink has none of.
        assert {r["correlation_id"] for r in rows} == {"c1", "c2"}
        # `details` is omitted entirely — the row relies on the column's
        # own DB default ('{}'), never an explicit empty dict this sink
        # would have to keep in sync with the schema.
        assert all("details" not in r for r in rows)

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


class TestDeriveResource:
    def test_single_path_param(self) -> None:
        assert _derive_resource("/api/leads/{lead_id}", {"lead_id": "L1"}) == ("leads", "L1")

    def test_nested_sub_resource_uses_first_param_not_last(self) -> None:
        """The whole point of `_derive_resource`: a card_hub-nested route
        (`entity_path("/notas/{nota_id}")`) still resolves to the CARD's
        own resource/id, not the nested note's."""
        assert _derive_resource(
            "/api/leads/{lead_id}/notas/{nota_id}",
            {"lead_id": "L1", "nota_id": "N1"},
        ) == ("leads", "L1")

    def test_no_path_param_returns_none_none(self) -> None:
        assert _derive_resource("/api/leads", {}) == (None, None)

    def test_strips_a_fastapi_converter_from_the_param_name(self) -> None:
        assert _derive_resource("/api/leads/{lead_id:int}", {"lead_id": 42}) == ("leads", "42")

    def test_missing_value_in_path_params_returns_none_id(self) -> None:
        assert _derive_resource("/api/leads/{lead_id}", {}) == ("leads", None)


class TestToRow:
    def test_writes_dedicated_columns_not_details(self) -> None:
        entry = _entry(
            product_slug="social-wiring",
            route_template="/api/clientes/{cliente_id}",
            path_params={"cliente_id": "C1"},
            status=200,
            correlation_id="corr-9",
            duration_ms=42.7,
            actor=AuditActor(user_id="u1", org_id="o1", role="owner"),
        )
        row = _to_row(entry)
        assert row["product_slug"] == "social-wiring"
        assert row["method"] == "POST"
        assert row["route_template"] == "/api/clientes/{cliente_id}"
        assert row["path_params"] == {"cliente_id": "C1"}
        assert row["status_code"] == 200
        assert row["correlation_id"] == "corr-9"
        assert row["role"] == "owner"
        assert row["actor_kind"] == "user"
        assert row["duration_ms"] == 42  # int() truncation — column is INT
        assert "details" not in row

    def test_original_columns_derived_from_route(self) -> None:
        entry = _entry(route_template="/api/clientes/{cliente_id}", path_params={"cliente_id": "C1"})
        row = _to_row(entry)
        assert row["action"] == "POST"
        assert row["resource_type"] == "clientes"
        assert row["resource_id"] == "C1"

    def test_resource_type_falls_back_to_product_slug_when_no_path_param(self) -> None:
        entry = _entry(product_slug="social-wiring", route_template="/api/clientes", path_params={})
        row = _to_row(entry)
        assert row["resource_type"] == "social-wiring"
        assert row["resource_id"] is None


def test_log_overflow_or_failure_is_never_a_bare_pass(capsys) -> None:
    before = overflow_or_failure_count()
    log_overflow_or_failure(kind="test_kind", entry={"x": 1}, exc=ValueError("nope"))
    assert overflow_or_failure_count() == before + 1
    out = capsys.readouterr().out
    row = json.loads(out.strip().splitlines()[-1])
    assert row == {"audit_fallback": "test_kind", "entry": {"x": 1}}
