"""Staff notices go out on the org's line and are PRE-WRITTEN with origem='interno' (julia-line S6 / CONTRACT B2)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import julia_envio_gate, julia_relatorio_service as rel
from app.services.julia_linha import LinhaDaOrg, SemLinha

ORG = uuid4()
CONN_ID = uuid4()


class _Redis:
    def __init__(self):
        self.ops: list = []

    def set(self, key, value, ex=None):
        self.ops.append(("set", key))

    def expire(self, key, ttl):
        self.ops.append(("expire", key))


class _Waha:
    def __init__(self, result=None):
        self.sent: list = []
        self._result = result if result is not None else {"id": "true_5511@c.us_ABC"}

    async def send_text(self, chat, text):
        self.sent.append((chat, text))
        return self._result


class _Store:
    def __init__(self):
        self.calls: list = []

    def registrar_interno_enviado(self, **kw):
        self.calls.append(kw)


class _StoreQuebrado(_Store):
    def registrar_interno_enviado(self, **kw):
        raise RuntimeError("db down")


def _conn():
    return SimpleNamespace(id=CONN_ID, org_id=ORG, base_url="https://waha.test", api_key="k", session_name="default")


def _liberacao():
    return julia_envio_gate.Liberacao(
        org_id=str(ORG), connection_id=str(CONN_ID), fluxo=julia_envio_gate.Fluxo.INTERNO, selo=julia_envio_gate._SELO)


@pytest.mark.asyncio
async def test_send_prewrites_the_interno_row_with_the_provider_id():
    waha, store, redis = _Waha(), _Store(), _Redis()
    sender = rel.InternoSender(connection=_conn(), waha=waha, redis=redis, liberacao=_liberacao(), message_store=store)
    await sender.send_reply("5511@c.us", "Relatório")
    assert waha.sent == [("5511@c.us", "Relatório")]
    assert len(store.calls) == 1
    call = store.calls[0]
    assert call["connection_id"] == CONN_ID and call["chat_id"] == "5511@c.us" and call["body"] == "Relatório"
    assert call["provider_message_id"] == "true_5511@c.us_ABC"
    assert [op for op, _ in redis.ops] == ["set", "expire"]  # in-flight flag bracketed the send


@pytest.mark.asyncio
async def test_a_failed_prewrite_does_not_fail_the_delivered_send():
    sender = rel.InternoSender(
        connection=_conn(), waha=_Waha(), redis=_Redis(), liberacao=_liberacao(), message_store=_StoreQuebrado())
    await sender.send_reply("5511@c.us", "x")  # must not raise: the notice was delivered


def test_the_deprecated_redis_own_id_shim_is_gone():
    from app.services import julia_agente_service

    assert not hasattr(julia_agente_service, "registrar_envio_proprio")


@pytest.mark.asyncio
async def test_aviso_interno_without_a_line_returns_the_named_reason():
    def sem_linha(org):
        raise SemLinha(org)

    servicos = SimpleNamespace(linha_resolver=sem_linha)
    assert await rel.enviar_aviso_interno(servicos, ORG, "+5511999990000", "oi") == "sem_linha"


@pytest.mark.asyncio
async def test_aviso_interno_sends_on_the_resolved_line(monkeypatch):
    conn = _conn()
    waha, store = _Waha(), _Store()

    async def resolve_chat_id(numero):
        return SimpleNamespace(chat_id=f"{numero.lstrip('+')}@c.us")

    waha.resolve_chat_id = resolve_chat_id
    monkeypatch.setattr(rel.julia_envio_gate, "exigir", lambda *a, **k: _liberacao())
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return waha

    servicos = SimpleNamespace(
        linha_resolver=lambda org: LinhaDaOrg(org_id=ORG, connection=conn), scoped=object(), waha_factory=factory,
        redis=_Redis(), cfg=SimpleNamespace(whatsapp_paragraph_delay_seconds=0), message_store_factory=lambda org: store)
    assert await rel.enviar_aviso_interno(servicos, ORG, "+5511999990000", "Aviso") is None
    assert seen["base_url"] == "https://waha.test" and seen["api_key"] == "k"  # credentials from the line, not the env
    assert waha.sent == [("5511999990000@c.us", "Aviso")]
    assert store.calls and store.calls[0]["provider_message_id"] == "true_5511@c.us_ABC"
