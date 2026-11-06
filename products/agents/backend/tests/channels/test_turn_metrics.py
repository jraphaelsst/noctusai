"""Per-turn metrics recording (``agents.turn_metrics``, migration 066): success, error, a failing metrics write, the
sum of priced ledger events, and the eval tag. The recorder is exercised through the REAL channel turn route."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

from noctusai_lib.integrations.llm import FakeProvider
from noctusai_lib.integrations.llm.usage import UsageEvent, record_usage

from app.channels import metricas
from app.main import app
from app.dependencies import get_turn_metrics_store_dep
from app.stores.turn_metrics import FakeTurnMetricsStore
from tests.channels.conftest import turn_body
from tests.channels.test_julia_v2_e2e import say


class _Pricing(FakeProvider):
    """A scripted provider that books a priced ledger event per call, like the real providers do."""

    async def chat_with_tools(self, *a, **kw):
        await record_usage(
            provider="anthropic", model="claude-haiku-4-5", operation="chat", prompt_tokens=100, completion_tokens=20,
            total_tokens=120, cache_read_input_tokens=900, cache_creation_input_tokens=50)
        return await super().chat_with_tools(*a, **kw)


class _Falha(_Pricing):
    async def chat_with_tools(self, *a, **kw):
        await super().chat_with_tools(*a, **kw)
        raise RuntimeError("provider exploded")


class _Quebrada(FakeTurnMetricsStore):
    def registrar(self, row):
        raise RuntimeError("db down")


def test_a_channel_turn_books_one_row_with_cost_speed_and_size(chan):
    chan.seed_agent()
    chan.use_provider(_Pricing(tool_responses=[say("Oi! Tudo bem?")]))
    resp = chan.turn(turn_body("Oi", ids=["m1"]))
    assert resp.status_code == 200
    [row] = chan.metricas.rows
    assert row["origem"] == "canal" and row["status"] == "ok" and row["erro_classe"] is None
    assert row["llm_calls"] == 1
    assert (row["tokens_entrada"], row["tokens_saida"]) == (1050, 20)  # prompt + cache read + cache write
    assert (row["tokens_cache_leitura"], row["tokens_cache_escrita"]) == (900, 50)
    assert row["custo_usd"] > 0 and row["modelos"] == ["claude-haiku-4-5"] and row["price_versions"]
    assert row["reply_bytes"] == len("Oi! Tudo bem?".encode()) and row["inbound_bytes"] == len("Oi".encode())
    assert row["prompt_bytes"] > 0 and row["db_bytes"] >= row["reply_bytes"] + row["inbound_bytes"]
    assert row["turno_ms"] >= row["llm_ms"] >= 0 and row["thread_id"] and row["reply_message_id"]
    assert row["inbound_message_id"] and row["media_bytes"] is None and row["handoff"] is False


def test_the_row_cost_is_the_sum_of_the_priced_events_never_repriced():
    ev = [
        UsageEvent(provider="anthropic", model="m", operation="chat", prompt_tokens=10, completion_tokens=5,
                   cost_estimate_usd=0.0123456, price_version="catalog:a"),
        UsageEvent(provider="anthropic", model="m", operation="chat", prompt_tokens=1, completion_tokens=1,
                   cache_read_input_tokens=7, cost_estimate_usd=0.0000014, price_version="catalog:a"),
    ]
    row = metricas.montar_registro(
        org_id=uuid4(), agent=SimpleNamespace(id=uuid4(), key="julia"), versao_id=None, compiled_hash="h", thread_id=None,
        mensagem_entrada_id=None, mensagem_resposta_id=None, origem="canal", gatilho="mensagem", eventos=ev,
        medida={"llm_ms": 5, "tool_ms": 2, "prompt_bytes": 9}, turno_ms=9, intake_ms=None, inbound_bytes=1, reply_bytes=2,
        db_bytes=3, status="ok")
    assert row["custo_usd"] == round(0.0123456 + 0.0000014, 6)
    assert row["tokens_entrada"] == 10 + 1 + 7 and row["price_versions"] == ["catalog:a"]


def test_an_error_turn_still_books_its_row_the_error_class_and_what_it_spent(chan):
    chan.seed_agent()
    chan.use_provider(_Falha(tool_responses=[say("x")]))
    resp = chan.turn(turn_body("Oi", ids=["e1"]))
    assert resp.status_code == 503
    [row] = chan.metricas.rows
    assert row["status"] == "erro" and row["erro_classe"] and row["erro_classe"] != "NoneType"
    assert row["reply_message_id"] is None and row["reply_bytes"] == 0
    assert row["tokens_entrada"] == 1050 and row["custo_usd"] > 0  # a failed turn still books its spend


def test_a_failing_metrics_write_never_fails_the_turn_and_is_logged(chan, caplog):
    chan.seed_agent()
    chan.use_provider(FakeProvider(tool_responses=[say("Oi!")]))
    app.dependency_overrides[get_turn_metrics_store_dep] = lambda: _Quebrada()
    try:
        with caplog.at_level(logging.ERROR):
            resp = chan.turn(turn_body("Oi", ids=["f1"]))
    finally:
        app.dependency_overrides[get_turn_metrics_store_dep] = lambda: chan.metricas
    assert resp.status_code == 200 and resp.json()["reply"]["partes"] == ["Oi!"]
    assert any("turn_metrics.registro_falhou" in r.message and r.exc_info for r in caplog.records)


def test_registrar_turno_without_a_store_is_a_noop():
    metricas.registrar_turno(None, {"agent_key": "x"})
