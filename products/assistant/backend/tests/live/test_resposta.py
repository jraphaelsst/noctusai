"""The live reply (owner decision 2026-11-12). Fakes only: FakeAgentsClient, FakeWahaClient, an in-memory registro."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from noctusai_lib.integrations.agents_channel import AgentsTimeout, FakeAgentsClient, TurnResult
from noctusai_lib.integrations.whatsapp import FakeWahaClient, parse_line_policy
from noctusai_lib.integrations.whatsapp.inbox import InboxMessage

from app.live import registro as r
from app.live.controles import CAMPO_LISTA
from app.live.resposta import LiveReplier, ReplyConfig

ORG, CONN = uuid4(), uuid4()
NUMERO = "5511988887777"
ENABLED = parse_line_policy('{"send":"enabled","mark_online":true,"full_sync":true,"auto_repair":true}')
DISABLED = parse_line_policy('{"send":"disabled","mark_online":false,"full_sync":false,"auto_repair":false}')


class Ctl(FakeAgentsClient):
    """FakeAgentsClient whose `controle` carries the allow-list field (the real client gets it from agents)."""

    def __init__(self, *a, modo="ligado", lista=(), ctl_error=None, no_list_field=False, **kw):
        super().__init__(*a, **kw)
        self.modo, self.lista, self.ctl_error, self.no_list_field = modo, tuple(lista), ctl_error, no_list_field
        self.ctl_calls = 0

    async def controle(self, agent_key):
        self.ctl_calls += 1
        if self.ctl_error:
            raise self.ctl_error
        extra = {} if self.no_list_field else {CAMPO_LISTA: self.lista}
        return SimpleNamespace(agent_key=agent_key, modo=self.modo, **extra)


class Reg:
    def __init__(self, intake="pending"):
        self.intake, self.eventos = intake, []

    def desfecho_do_intake(self, connection_id, waha_message_id):
        return self.intake

    intake_responsavel = staticmethod(r.RegistroResposta.intake_responsavel)

    def registrar(self, **kw):
        self.eventos.append(kw)
        return True


def _msg(chat=f"{NUMERO}@c.us", body="oi, tudo bem?", from_me=False, age_s=5):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat()
    return InboxMessage(id=f"m-{uuid4().hex[:6]}", chat_id=chat, from_me=from_me, body=body, type="chat",
                        media_url=None, ack=None, timestamp=ts, sender_name=None)


def _build(agents, *, reg=None, enabled=True, policy=ENABLED, waha=None, sleep=None):
    waha = waha or FakeWahaClient(line_policy=policy)
    reg = reg or Reg()

    async def waha_for(org, conn):
        return waha

    async def nosleep(_):
        return None

    rep = LiveReplier(agents=agents, waha_for=waha_for, registro=reg,
                      config=ReplyConfig(enabled=enabled, agent_key="assistente"),
                      identity_key=lambda: "k", sleep=sleep or nosleep)
    return rep, waha, reg


def run(rep, msg):
    return asyncio.run(rep.responder(ORG, CONN, msg))


def test_allowed_number_gets_turn_and_send():
    ag = Ctl(lista=[f"+{NUMERO}"])
    rep, waha, reg = _build(ag)
    msg = _msg()
    assert run(rep, msg) == r.ENVIADA
    assert len(ag.turns) == 1 and ag.turns[0].agent_key == "assistente"
    assert ag.turns[0].phone_e164 == f"+{NUMERO}"
    assert ag.turns[0].chat_id != msg.chat_id and NUMERO not in ag.turns[0].chat_id  # HMAC'd conversation key
    assert [m["chatId"] for m in waha.sent_messages] == [msg.chat_id]
    assert [e["desfecho"] for e in reg.eventos] == [r.ENVIADA]


def test_no_phone_number_reaches_the_event_row():
    rep, _, reg = _build(Ctl(lista=[NUMERO]))
    run(rep, _msg())
    assert NUMERO not in json.dumps(reg.eventos, default=str)


def test_empty_list_allows_everyone():
    rep, waha, reg = _build(Ctl(lista=[]))
    assert run(rep, _msg(chat="5521977776666@c.us")) == r.ENVIADA
    assert len(waha.sent_messages) == 1


def test_send_seam_refuses_a_number_outside_a_non_empty_list_even_when_agents_served_the_turn():
    ag = Ctl(lista=["5599900001111"])
    rep, waha, reg = _build(ag)
    assert run(rep, _msg()) == r.RECUSADA_LISTA
    assert waha.sent_messages == [] and reg.eventos[0]["motivo"] == "guarda_de_envio"


def test_agents_refusal_alone_blocks_the_send():
    refused = TurnResult(conversation_id="", partes=(), status="restrito_avaliacao")
    ag = Ctl([refused], lista=[])  # the seam would allow it: only agents refuses
    rep, waha, reg = _build(ag)
    assert run(rep, _msg()) == r.RECUSADA_LISTA
    assert waha.sent_messages == [] and ag.ctl_calls == 0


def test_agent_off_by_turn_status_sends_nothing():
    ag = Ctl([TurnResult(conversation_id="", partes=(), status="agente_desligado")])
    rep, waha, reg = _build(ag)
    assert run(rep, _msg()) == r.AGENTE_DESLIGADO
    assert waha.sent_messages == []


def test_agent_off_at_the_send_seam_sends_nothing():
    rep, waha, reg = _build(Ctl(modo="desligado"))
    assert run(rep, _msg()) == r.AGENTE_DESLIGADO
    assert waha.sent_messages == []


@pytest.mark.parametrize("kw", [{"ctl_error": AgentsTimeout()}, {"no_list_field": True}])
def test_unreadable_controls_fail_closed(kw):
    rep, waha, reg = _build(Ctl(**kw))
    assert run(rep, _msg()) == r.CONTROLE_INDISPONIVEL
    assert waha.sent_messages == []


def test_group_status_and_own_messages_do_nothing():
    ag = Ctl()
    rep, waha, reg = _build(ag)
    for m in (_msg(chat="120363000000000000@g.us"), _msg(chat="status@broadcast"), _msg(from_me=True)):
        assert run(rep, m) is None
    assert ag.turns == [] and waha.sent_messages == [] and reg.eventos == []


def test_kill_switch_off_is_a_silent_shadow():
    ag = Ctl()
    rep, waha, reg = _build(ag, enabled=False)
    assert run(rep, _msg()) is None
    assert ag.turns == [] and reg.eventos == []


@pytest.mark.parametrize("intake", ["skipped", "skipped_excluded", None])
def test_history_and_excluded_intake_rows_are_never_answered(intake):
    ag = Ctl()
    rep, waha, reg = _build(ag, reg=Reg(intake))
    assert run(rep, _msg()) is None
    assert ag.turns == [] and waha.sent_messages == []


def test_typed_agents_error_means_no_reply_and_an_event():
    ag = Ctl([AgentsTimeout()])
    rep, waha, reg = _build(ag)
    assert run(rep, _msg()) == r.ERRO_TURNO
    assert waha.sent_messages == [] and reg.eventos[0]["motivo"] == "agents_timeout"


def test_old_message_is_not_answered():
    ag = Ctl()
    rep, waha, reg = _build(ag)
    assert run(rep, _msg(age_s=3600)) == r.MENSAGEM_ANTIGA
    assert ag.turns == []


def test_one_bubble_per_paragraph():
    ag = Ctl([TurnResult(conversation_id="c", partes=("um\n\ndois", "tres"), status="respondido")])
    rep, waha, reg = _build(ag)
    assert run(rep, _msg()) == r.ENVIADA
    assert [m["text"] for m in waha.sent_messages] == ["um", "dois", "tres"]
    assert reg.eventos[0]["dados"] == {"remetente": "contato", "bolhas": 3}


def test_a_disabled_line_policy_refuses_the_send_and_records_it():
    rep, waha, reg = _build(Ctl(), policy=DISABLED)
    assert run(rep, _msg()) == r.ERRO_ENVIO
    assert waha.sent_messages == [] and reg.eventos[0]["motivo"] == "line_write_refused"


def test_partial_delivery_is_recorded_not_retried():
    class Flaky(FakeWahaClient):
        async def send_text(self, chat_id, text):
            if self.sent_messages:
                raise RuntimeError("boom")
            return await super().send_text(chat_id, text)

    ag = Ctl([TurnResult(conversation_id="c", partes=("a\n\nb",), status="respondido")])
    rep, waha, reg = _build(ag, waha=Flaky(line_policy=ENABLED))
    assert run(rep, _msg()) == r.ENVIADA_PARCIAL
    assert len(waha.sent_messages) == 1 and reg.eventos[0]["dados"] == {"remetente": "contato", "bolhas": 1, "de": 2}


def test_missing_agents_client_is_a_declared_refusal_not_a_fake():
    rep, waha, reg = _build(None)
    assert run(rep, _msg()) == r.ERRO_TURNO
    assert reg.eventos[0]["motivo"] == "agents_nao_configurado" and waha.sent_messages == []


def test_a_burst_is_one_turn_one_reply_and_one_event_per_message():
    ag = Ctl(lista=[])
    async def tick(_):
        await asyncio.sleep(0)  # a real quiet window yields: the other webhook calls land while it waits

    rep, waha, reg = _build(ag, sleep=tick)
    msgs = [_msg(body=t) for t in ("oi", "tudo bem?", "preciso de ajuda")]

    async def go():
        return await asyncio.gather(*(rep.responder(ORG, CONN, m) for m in msgs))

    outs = asyncio.run(go())
    assert sorted(o for o in outs if o) == [r.ENVIADA] and outs.count(None) == 2  # one call answers for the batch
    assert len(ag.turns) == 1 and [m.texto for m in ag.turns[0].messages] == ["oi", "tudo bem?", "preciso de ajuda"]
    assert len(waha.sent_messages) == 1
    assert [e["waha_message_id"] for e in reg.eventos] == [m.id for m in msgs]
    assert all(e["desfecho"] == r.ENVIADA and e["dados"]["lote"] == 3 for e in reg.eventos)


def test_two_bursts_apart_are_two_turns():
    ag = Ctl(lista=[])
    rep, waha, reg = _build(ag)
    run(rep, _msg(body="a"))
    run(rep, _msg(body="b"))
    assert len(ag.turns) == 2 and len(waha.sent_messages) == 2


def test_status_payload_with_the_allow_list_flows_through_the_real_parser_to_the_seam():
    import httpx
    from noctusai_lib.integrations.agents_channel import HttpAgentsClient, TurnResult

    def make(lista):
        body = {"agent_key": "assistente", "modo": "ligado", "aceita_novos_leads": True}
        if lista is not None:
            body["contatos_permitidos"] = lista
        http = HttpAgentsClient("https://agents.example.test", "pk_t", transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=body) if req.url.path.endswith("/controle")
            else httpx.Response(200, json={"conversation_id": "c", "status": "respondido", "reply": {"partes": ["oi"]}})))
        return http

    # list names the number -> sent; names someone else -> refused; field absent (older agents) -> closed
    for lista, esperado in (([f"+{NUMERO}"], r.ENVIADA), (["+5599900001111"], r.RECUSADA_LISTA), (None, r.CONTROLE_INDISPONIVEL)):
        rep, waha, reg = _build(make(lista))
        assert run(rep, _msg()) == esperado, lista
