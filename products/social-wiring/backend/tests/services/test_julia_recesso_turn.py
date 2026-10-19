"""Julia wave 1: the deterministic recesso message on the first turn of an interacao inside the period
(through the real lead worker; every seam is a Fake)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.clients.agents import FakeAgentsClient, TurnResult
from app.services import julia_conhecimento_service as conhecimento
from app.services.julia_lead_turn_service import process_lead_batch

from tests.support.julia_world import LEAD_CHAT, ORG_ID, World, buffer_lead

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    return w


def _recesso(world: World, *, ativo: bool, mensagem: str = "Estamos em recesso, voltamos logo.") -> None:
    hoje = date.today()
    dados = conhecimento.validar("recesso", {
        "ativo": ativo, "inicio": (hoje - timedelta(days=1)).isoformat(),
        "fim": (hoje + timedelta(days=1)).isoformat(), "mensagem": mensagem})
    world.sw.table(conhecimento.TABLE).insert(
        {"org_id": str(ORG_ID), "secao": "recesso", "dados": dados, "versao": 1}).execute()


def _ok(*partes: str, cid: str = "11111111-1111-4111-8111-111111111111") -> TurnResult:
    return TurnResult(conversation_id=cid, partes=tuple(partes), status="respondido", actions=())


async def _run(world: World, key: str) -> None:
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps())


async def test_first_turn_sends_disclosure_then_recesso_then_the_reply(world):
    _recesso(world, ativo=True)
    world.agents = FakeAgentsClient([_ok("Olá!")])
    await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"]))
    texts = world.sent_texts()
    assert texts[0].startswith("Oi! Eu sou a Julia")
    assert texts[1:] == ["Estamos em recesso, voltamos logo.", "Olá!"]


async def test_second_turn_of_the_same_interacao_has_no_recesso_message(world):
    _recesso(world, ativo=True)
    world.agents = FakeAgentsClient([_ok("um"), _ok("dois")])
    k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
    await _run(world, k)
    buffer_lead(world, LEAD_CHAT, ["quero comprar"], ids=["m2"])
    await _run(world, k)
    assert sum("recesso" in t for t in world.sent_texts()) == 1
    assert world.sent_texts()[-1] == "dois"


async def test_inactive_recesso_adds_nothing(world):
    _recesso(world, ativo=False)
    world.agents = FakeAgentsClient([_ok("Olá!")])
    await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"]))
    assert not any("recesso" in t for t in world.sent_texts())
