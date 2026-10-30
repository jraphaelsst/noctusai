"""The central AI-usage ledger (D25): attribution, write-time pricing, and the
failure / partial-stream rows — every LLM call is a row, attributed and priced.

Real seams only: the FakeProvider (or a test provider class) behind the real
registry, the real `record_usage`, `InMemoryUsageSink` as the sink, and
`MockSupabaseClient` behind the Real `CentralUsageSink`.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from noctusai_lib.api.audit.types import AuditActor
from noctusai_lib.integrations.llm import (
    CentralUsageSink,
    FanOutUsageSink,
    InMemoryUsageSink,
    LLMAPIError,
    LLMConfig,
    UsageAttributionMiddleware,
    UsageEvent,
    build_ai_usage_row,
    chat_completion,
    chat_completion_stream,
    chat_with_tools,
    configure_llm,
    generate_embedding,
    llm_usage_context,
    make_central_usage_sink,
    price_usage,
    register,
    set_default_product,
)
from noctusai_lib.integrations.llm.attribution import current_attribution
from noctusai_lib.integrations.llm.catalog_overrides import (
    ModelOverride,
    clear_model_overrides,
    set_model_overrides,
)
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.ledger import FxQuote
from noctusai_lib.integrations.llm.models import models_for
from noctusai_lib.integrations.llm.providers import FakeProvider
from noctusai_lib.testing import MockSupabaseClient

ORG = "11111111-1111-4111-8111-111111111111"
USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OPUS = "claude-opus-5"  # 5 USD / 1M in, 25 USD / 1M out


@pytest.fixture
def sink():
    s = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=s))
    set_default_product("seed-test")
    yield s
    set_default_product(None)
    clear_model_overrides()
    _reset_for_testing()


def _install(provider_obj, name="ledger-test"):
    register(name, lambda: provider_obj)
    return name


# ── attribution ───────────────────────────────────────────────────────────────


def test_context_nests_and_only_overrides_what_it_names():
    set_default_product("p1")
    try:
        with llm_usage_context(feature="outer", agent_key="julia"):
            with llm_usage_context(feature="inner", conversation_id="c1"):
                attr = current_attribution()
                assert (attr.product, attr.feature, attr.agent_key, attr.conversation_id) == (
                    "p1", "inner", "julia", "c1",
                )
            assert current_attribution().feature == "outer"
        assert current_attribution().feature is None
    finally:
        set_default_product(None)


@pytest.mark.asyncio
async def test_event_carries_product_feature_and_explicit_org(sink):
    name = _install(FakeProvider(chat_responses=["oi"], chat_usage=[(1000, 100)], usage_provider="anthropic"))
    with llm_usage_context(feature="julia.reply", purpose="reply", org_id=ORG, user_id=USER):
        await chat_completion([{"role": "user", "content": "x"}], provider=name, model=OPUS, cache=False)
    ev = sink.events[-1]
    assert (ev.product, ev.feature, ev.purpose, ev.org_id, ev.user_id) == (
        "seed-test", "julia.reply", "reply", ORG, USER,
    )
    assert ev.status == "ok"


def test_request_middleware_attributes_user_org_route_and_request_id(sink):
    name = _install(FakeProvider(chat_responses=["oi"], chat_usage=[(10, 1)], usage_provider="anthropic"))
    app = FastAPI()

    @app.post("/api/docs/{doc_id}/summary")
    async def summarize(doc_id: str, request: Request):
        # What the seed auth dependency stashes (make_get_current_user_org).
        request.state.audit_actor = AuditActor(user_id=USER, org_id=ORG)
        await chat_completion([{"role": "user", "content": doc_id}], provider=name, model=OPUS, cache=False)
        return {"ok": True}

    app.add_middleware(UsageAttributionMiddleware)
    assert TestClient(app).post("/api/docs/42/summary").status_code == 200
    ev = sink.events[-1]
    assert ev.user_id == USER and ev.org_id == ORG
    assert ev.feature == "POST /api/docs/{doc_id}/summary"  # the route TEMPLATE, never the raw path
    assert ev.product == "seed-test"


# ── write-time pricing ────────────────────────────────────────────────────────


def test_price_version_is_a_catalog_hash_and_moves_with_an_override():
    cost, version = price_usage(provider="anthropic", model=OPUS, prompt_tokens=1_000_000, completion_tokens=0)
    assert cost == pytest.approx(5.0)
    assert version.startswith("catalog:")
    entry = next(m for m in models_for("anthropic") if m.id == OPUS)
    set_model_overrides([ModelOverride.from_entry(entry, cost_per_1m_input_tokens=7.0, version=3)])
    try:
        cost2, version2 = price_usage(provider="anthropic", model=OPUS, prompt_tokens=1_000_000, completion_tokens=0)
    finally:
        clear_model_overrides()
    assert (cost2, version2) == (pytest.approx(7.0), "override:v3")


def test_unknown_model_is_unpriced_not_silently_free():
    assert price_usage(provider="anthropic", model="no-such-model", prompt_tokens=10, completion_tokens=10) == (
        0.0, "unpriced",
    )


@pytest.mark.asyncio
async def test_recorded_event_is_priced_at_write_time(sink):
    name = _install(FakeProvider(chat_responses=["oi"], chat_usage=[(1_000_000, 100_000)], usage_provider="anthropic"))
    await chat_completion([{"role": "user", "content": "x"}], provider=name, model=OPUS, cache=False)
    ev = sink.events[-1]
    assert ev.cost_estimate_usd == pytest.approx(7.5)
    assert ev.price_version and ev.price_version.startswith("catalog:")


# ── failed calls are rows too ─────────────────────────────────────────────────


class _Boom(FakeProvider):
    async def chat_completion(self, messages, **kwargs):
        raise LLMAPIError("anthropic", "upstream 529")

    async def chat_with_tools(self, messages, tools, **kwargs):
        raise LLMAPIError("anthropic", "upstream 529")

    async def generate_embedding(self, text, **kwargs):
        raise LLMAPIError("openai", "upstream 500")


@pytest.mark.asyncio
async def test_a_failed_chat_records_one_error_row_with_null_tokens(sink):
    name = _install(_Boom())
    with pytest.raises(LLMAPIError):
        await chat_completion([{"role": "user", "content": "x"}], provider=name, model=OPUS, cache=False)
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.status == "error" and ev.prompt_tokens is None and ev.extra["error"] == "LLMAPIError"


@pytest.mark.asyncio
async def test_failed_tool_turn_and_embedding_are_rows(sink):
    name = _install(_Boom())
    with pytest.raises(LLMAPIError):
        await chat_with_tools([{"role": "user", "content": "x"}], [], provider=name, model=OPUS)
    with pytest.raises(LLMAPIError):
        await generate_embedding("x", provider=name, model="text-embedding-3-small")
    assert [(e.operation, e.status) for e in sink.events] == [("chat", "error"), ("embedding", "error")]


@pytest.mark.asyncio
async def test_a_local_refusal_is_not_a_row(sink):
    from noctusai_lib.integrations.llm import ProviderNotImplemented

    class _Stub(FakeProvider):
        async def generate_embedding(self, text, **kwargs):
            raise ProviderNotImplemented("stub")

    name = _install(_Stub())
    with pytest.raises(ProviderNotImplemented):
        await generate_embedding("x", provider=name, model="m")
    assert sink.events == []


@pytest.mark.asyncio
async def test_a_provider_that_recorded_before_raising_is_not_double_counted(sink):
    from noctusai_lib.integrations.llm import record_usage

    class _RecordsThenFails(FakeProvider):
        async def chat_completion(self, messages, *, model, **kwargs):
            await record_usage(provider="anthropic", model=model, operation="chat",
                               prompt_tokens=5, completion_tokens=1, total_tokens=6)
            raise LLMAPIError("anthropic", "parse failed")

    name = _install(_RecordsThenFails())
    with pytest.raises(LLMAPIError):
        await chat_completion([{"role": "user", "content": "x"}], provider=name, model=OPUS, cache=False)
    assert [e.status for e in sink.events] == ["ok"]


# ── streams cut short ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_completed_stream_adds_no_partial_row(sink):
    name = _install(FakeProvider(stream_responses=[["ab", "cd"]]))
    out = [c async for c in chat_completion_stream([{"role": "user", "content": "x"}], provider=name, model=OPUS)]
    assert out == ["ab", "cd"]
    assert sink.events == []  # the (fake) provider reports nothing; no synthetic row on success


@pytest.mark.asyncio
async def test_a_consumer_abort_records_a_partial_row_with_estimated_tokens(sink):
    name = _install(FakeProvider(stream_responses=[["a" * 40, "b" * 40, "c" * 40]]))
    stream = chat_completion_stream([{"role": "user", "content": "p" * 80}], provider=name, model=OPUS)
    first = await stream.__anext__()
    assert first == "a" * 40
    await stream.aclose()  # the client went away mid-reply
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.status == "partial"
    assert (ev.prompt_tokens, ev.completion_tokens) == (20, 10)  # 80 / 4, 40 / 4
    assert ev.extra["tokens_estimated"] is True and ev.extra["cut_reason"] == "consumer_closed"
    # The test provider's registry name has no catalog row → flagged, never billed as a guess.
    assert ev.price_version == "unpriced"


@pytest.mark.asyncio
async def test_a_partial_row_on_a_catalog_provider_is_priced(sink):
    from noctusai_lib.integrations.llm.registry import get_provider_class

    real = get_provider_class("anthropic")
    register("anthropic", lambda: FakeProvider(stream_responses=[["a" * 400, "b" * 400]]))
    try:
        stream = chat_completion_stream([{"role": "user", "content": "x"}], provider="anthropic", model=OPUS)
        await stream.__anext__()
        await stream.aclose()
    finally:
        register("anthropic", real)
    ev = sink.events[-1]
    assert ev.status == "partial" and ev.completion_tokens == 100
    assert ev.cost_estimate_usd == pytest.approx((1 * 5 + 100 * 25) / 1_000_000)
    assert ev.price_version.startswith("catalog:")


class _StreamDiesMidway(FakeProvider):
    def __init__(self, before):
        super().__init__()
        self._before = before

    async def chat_completion_stream(self, messages, **kwargs):
        for chunk in self._before:
            yield chunk
        raise LLMAPIError("anthropic", "stream reset")


@pytest.mark.asyncio
async def test_a_mid_stream_provider_error_records_partial(sink):
    name = _install(_StreamDiesMidway(["hello world!"]))
    with pytest.raises(LLMAPIError):
        async for _ in chat_completion_stream([{"role": "user", "content": "x"}], provider=name, model=OPUS):
            pass
    assert [(e.status, e.extra.get("cut_reason")) for e in sink.events] == [("partial", "LLMAPIError")]


@pytest.mark.asyncio
async def test_a_stream_that_fails_before_any_text_records_error(sink):
    name = _install(_StreamDiesMidway([]))
    with pytest.raises(LLMAPIError):
        async for _ in chat_completion_stream([{"role": "user", "content": "x"}], provider=name, model=OPUS):
            pass
    assert [e.status for e in sink.events] == ["error"]


# ── the ai_usage row + the Real sink ──────────────────────────────────────────


def _event(**kw):
    base = dict(provider="anthropic", model=OPUS, operation="chat", org_id=ORG, prompt_tokens=10,
                completion_tokens=2, cost_estimate_usd=0.5, product="social-wiring", feature="julia.reply",
                user_id=USER, status="ok", price_version="catalog:abc",
                at=datetime(2026, 10, 29, tzinfo=timezone.utc))
    base.update(kw)
    return UsageEvent(**base)


def test_row_converts_at_ptax_and_records_the_quote():
    row = build_ai_usage_row(_event(), FxQuote(5.5, "ptax", "2026-10-29"))
    assert row["cost_usd"] == 0.5 and row["fx_rate"] == 5.5 and row["cost_brl"] == pytest.approx(2.75)
    assert row["extra"]["fx_quote_date"] == "2026-10-29"
    assert (row["product"], row["feature"], row["org_id"], row["user_id"]) == ("social-wiring", "julia.reply", ORG, USER)
    assert (row["input_tokens"], row["output_tokens"]) == (10, 2)


def test_row_flags_env_fallback_unpriced_and_non_uuid_ids():
    row = build_ai_usage_row(
        _event(org_id="org-slug", user_id="legacy", product=None, price_version="unpriced"),
        FxQuote(5.0, "env_fallback"),
    )
    assert row["org_id"] is None and row["extra"]["org_ref"] == "org-slug"
    assert row["user_id"] is None and row["extra"]["user_ref"] == "legacy"
    assert row["product"] == "unattributed"
    assert row["extra"]["fx_source"] == "env_fallback" and row["extra"]["unpriced"] is True


@pytest.mark.asyncio
async def test_central_sink_inserts_into_ai_usage_with_the_latest_ptax():
    db = MockSupabaseClient()
    db.set_table_data("fx_rates", [{"pair": "USD/BRL", "quote_date": "2026-10-28", "rate": "5.40"}])
    db.set_table_data("ai_usage", [])
    sink = CentralUsageSink(lambda: db)
    await sink.record(_event())
    await sink.record(_event(status="partial"))
    rows = db.table("ai_usage").inserted_payloads
    assert len(rows) == 2
    assert rows[0]["fx_rate"] == 5.4 and rows[0]["cost_brl"] == pytest.approx(2.7)
    assert rows[1]["status"] == "partial"


@pytest.mark.asyncio
async def test_central_sink_without_a_bulletin_uses_env_and_says_so():
    db = MockSupabaseClient()
    db.set_table_data("fx_rates", [])
    db.set_table_data("ai_usage", [])
    previous = os.environ.get("LLM_USD_TO_BRL")
    os.environ["LLM_USD_TO_BRL"] = "6"
    try:
        await CentralUsageSink(lambda: db).record(_event())
    finally:
        if previous is None:
            os.environ.pop("LLM_USD_TO_BRL", None)
        else:
            os.environ["LLM_USD_TO_BRL"] = previous
    row = db.table("ai_usage").inserted_payloads[0]
    assert row["fx_rate"] == 6.0 and row["extra"]["fx_source"] == "env_fallback"


def test_factory_refuses_the_real_sink_under_pytest_unless_forced():
    assert make_central_usage_sink(lambda: None) is None
    assert make_central_usage_sink(None, force_real=True) is None
    assert isinstance(make_central_usage_sink(lambda: None, force_real=True), CentralUsageSink)


@pytest.mark.asyncio
async def test_fan_out_delivers_to_every_sink_even_if_one_fails():
    class _Broken:
        async def record(self, event):
            raise RuntimeError("down")

    good = InMemoryUsageSink()
    await FanOutUsageSink([_Broken(), good, None]).record(_event())
    assert len(good.events) == 1


def test_attribution_crosses_into_worker_threads():
    """`anyio.to_thread` / `asyncio.to_thread` copy the context — a sync helper
    run off the loop still bills to the scope that spawned it."""

    async def main():
        with llm_usage_context(feature="threaded"):
            return await asyncio.to_thread(lambda: current_attribution().feature)

    assert asyncio.run(main()) == "threaded"


def test_uuid_helper_round_trip():
    assert build_ai_usage_row(_event(org_id=str(uuid.UUID(ORG))), FxQuote(5.0, "ptax"))["org_id"] == ORG


# ── image edits are ledger rows too ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_image_edit_records_a_priced_image_edit_row(sink):
    import base64
    import types

    from noctusai_lib.integrations.image_edit.openai_adapter import OpenAIImageEditAdapter
    from noctusai_lib.integrations.image_edit.types import ImageEditRequest

    usage = types.SimpleNamespace(
        output_tokens=300, total_tokens=510,
        input_tokens_details=types.SimpleNamespace(text_tokens=10, image_tokens=200),
    )
    response = types.SimpleNamespace(
        data=[types.SimpleNamespace(b64_json=base64.b64encode(b"png").decode())], usage=usage,
    )

    class _Images:
        async def edit(self, **kwargs):
            return response

    adapter = OpenAIImageEditAdapter("", client=types.SimpleNamespace(images=_Images()))
    await adapter.edit(ImageEditRequest(images=(b"img",), prompt="céu azul", size="1024x1024"), org_id=ORG)
    ev = sink.events[-1]
    assert (ev.operation, ev.status, ev.org_id) == ("image_edit", "ok", ORG)
    assert (ev.prompt_tokens, ev.image_input_tokens, ev.image_output_tokens) == (10, 200, 300)
    assert ev.product == "seed-test"
