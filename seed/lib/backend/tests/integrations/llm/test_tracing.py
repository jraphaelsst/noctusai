"""Per-call AI tracing (`tracing.py`): spans, LLM-call stamps on the ledger row, guardrail hook, Real sink."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.llm import (
    InMemorySpanSink,
    InMemoryUsageSink,
    LLMConfig,
    chat_completion,
    configure_llm,
    configure_span_sink,
    make_span_sink,
    read_trace,
    record_guardrail_verdict,
    register,
    span,
)
from noctusai_lib.integrations.llm import tracing
from noctusai_lib.integrations.llm.attribution import llm_usage_context
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.ledger import FxQuote, build_ai_usage_row
from noctusai_lib.integrations.llm.providers import FakeProvider


@pytest.fixture
def world():
    fake = FakeProvider(chat_responses=["a", "b"], chat_usage=[(100, 10), (50, 5)], usage_provider="anthropic")
    register("fake-trace", lambda: fake)
    usage = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=usage))
    spans = InMemorySpanSink()
    configure_span_sink(spans)
    yield usage, spans
    configure_span_sink(None)
    _reset_for_testing()


async def _llm():
    return await chat_completion([{"role": "user", "content": "x"}], provider="fake-trace", model="claude-haiku-5-5",
                                 cache=False)


@pytest.mark.asyncio
async def test_a_turn_trace_links_llm_calls_and_tool_spans(world):
    usage, spans = world
    with llm_usage_context(product="agents", agent_key="julia", prompt_version="v7"):
        async with span("agents.turn", kind="internal") as turn:
            await _llm()
            async with span("buscar_imoveis", kind="tool", quantidade=3):
                pass
            await _llm()
    assert {e.trace_id for e in usage.events} == {turn.trace_id}
    assert all(e.parent_span_id == turn.span_id for e in usage.events)
    assert len({e.span_id for e in usage.events}) == 2
    assert all(e.latency_ms is not None and e.latency_ms >= 0 for e in usage.events)
    assert all(e.prompt_version == "v7" for e in usage.events)
    by_name = {s.name: s for s in spans.spans}
    assert by_name["buscar_imoveis"].parent_span_id == turn.span_id
    assert by_name["buscar_imoveis"].kind == "tool" and by_name["buscar_imoveis"].attributes == {"quantidade": 3}
    assert by_name["agents.turn"].parent_span_id is None
    assert by_name["agents.turn"].agent_key == "julia" and by_name["agents.turn"].prompt_version == "v7"


@pytest.mark.asyncio
async def test_a_call_outside_any_trace_still_gets_ids(world):
    usage, _ = world
    await _llm()
    e = usage.events[0]
    assert e.trace_id and e.span_id and e.parent_span_id is None


@pytest.mark.asyncio
async def test_an_exception_marks_the_span_error_and_propagates(world):
    _, spans = world
    with pytest.raises(RuntimeError):
        async with span("tool-x", kind="tool"):
            raise RuntimeError("boom")
    assert spans.spans[0].status == "error" and spans.spans[0].attributes["error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_guardrail_hook_records_a_verdict_span_under_the_turn(world):
    _, spans = world
    async with span("agents.turn") as turn:
        await record_guardrail_verdict("leak_filter", "blocked", blocked=True, regra="r1")
    g = next(s for s in spans.spans if s.kind == "guardrail")
    assert (g.guardrail_verdict, g.status, g.parent_span_id) == ("blocked", "blocked", turn.span_id)


@pytest.mark.asyncio
async def test_attributes_are_scalars_only_no_payload_text_leaks(world):
    row = {}
    sink = tracing.SupabaseSpanSink(lambda: MagicMock(table=lambda n: MagicMock(
        insert=lambda r: (row.update(r), MagicMock(execute=lambda: None))[1])))
    configure_span_sink(sink)
    async with span("t", kind="tool", ok=True, blob={"a": 1}, texto="x" * 500):
        pass
    assert "blob" not in row["attributes"] and len(row["attributes"]["texto"]) == 200


def test_span_sink_factory_is_none_under_pytest_unless_forced():
    assert make_span_sink(lambda: MagicMock()) is None
    assert make_span_sink(lambda: MagicMock(), force_real=True) is not None
    assert make_span_sink(None, force_real=True) is None


@pytest.mark.asyncio
async def test_real_sink_failure_is_logged_never_raised(caplog):
    def boom():
        raise RuntimeError("db down")

    configure_span_sink(tracing.SupabaseSpanSink(boom))
    try:
        async with span("t", kind="tool"):
            pass
    finally:
        configure_span_sink(None)
    assert any("ai_trace_spans insert failed" in r.getMessage() for r in caplog.records)


def test_ledger_row_carries_the_trace_columns():
    from noctusai_lib.integrations.llm.usage import UsageEvent

    ev = UsageEvent(provider="anthropic", model="m", operation="chat", trace_id="t1", span_id="s1",
                    parent_span_id="p1", latency_ms=42, prompt_version="v3")
    row = build_ai_usage_row(ev, FxQuote(5.0, "ptax"))
    assert (row["trace_id"], row["span_id"], row["parent_span_id"], row["latency_ms"], row["prompt_version"]) == (
        "t1", "s1", "p1", 42, "v3")


def test_ledger_insert_degrades_loudly_when_migration_116_is_not_applied(caplog):
    from noctusai_lib.integrations.llm.ledger import CentralUsageSink
    from noctusai_lib.integrations.llm.usage import UsageEvent

    inserts = []

    class _T:
        def __init__(self, name):
            self.name = name

        def select(self, *a):
            return self

        def eq(self, *a):
            return self

        def order(self, *a, **k):
            return self

        def limit(self, *a):
            return self

        def insert(self, row):
            self.row = row
            return self

        def execute(self):
            if self.name == "ai_usage":
                inserts.append(self.row)
                if "trace_id" in self.row:
                    raise RuntimeError("PGRST204 Could not find the 'trace_id' column of 'ai_usage'")
            return MagicMock(data=[])

    db = MagicMock()
    db.table.side_effect = _T
    sink = CentralUsageSink(lambda: db)
    ev = UsageEvent(provider="anthropic", model="m", operation="chat", trace_id="t1", span_id="s1", latency_ms=5)
    sink._insert(ev)
    assert len(inserts) == 2 and "trace_id" not in inserts[1]
    assert inserts[1]["extra"]["trace"]["trace_id"] == "t1"
    assert any("core migration 116" in r.getMessage() for r in caplog.records)


def test_read_trace_queries_the_timeline_view():
    t = MagicMock()
    for m in ("select", "eq", "order", "limit"):
        getattr(t, m).return_value = t
    t.execute.return_value = MagicMock(data=[{"span_id": "a"}])
    db = MagicMock()
    db.table.return_value = t
    assert read_trace(lambda: db, "tr1") == [{"span_id": "a"}]
    db.table.assert_called_with("ai_trace_timeline")
    t.eq.assert_called_with("trace_id", "tr1")
