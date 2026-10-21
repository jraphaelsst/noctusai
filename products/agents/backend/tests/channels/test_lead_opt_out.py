"""A lead that asks to stop is never dropped silently (owner decision 2026-10-21): the model's ``encerrar``
(``lead_pediu_parar``) and the API record a LEAD-level opt-out that stops every agent, leave an event (who / why /
what the lead said) and notify the org's owners/admins. Real route + real tool handlers over the Fake stores and the
Fake notification sink; a notification failure never undoes the opt-out."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.channels.controles import STATUS_LEAD_OPT_OUT, ParticipanteView, ThreadView, decidir
from app.channels.opt_out import KIND_LEAD_OPT_OUT, OptOutService, dedup_key
from app.notifications import FakeNotificationSink
from app.stores.threads import FakeThreadStore
from tests.channels.conftest import BOTH, turn_body
from tests.channels.test_channel_threads_router import STATUS_ONLY, TURN_ONLY, thr  # noqa: F401 — fixtures
from tests.channels.test_julia_v2_controles_limites import model_calls
from tests.channels.test_julia_v2_e2e import call, say, step

ADMIN = str(UUID(int=0xA11CE))
PEDIDO = "Chega, não me mande mais mensagens, por favor"
AGORA = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def _parar(motivo_texto: str | None = "O lead pediu para parar de receber mensagens") -> object:
    args: dict = {"motivo": "lead_pediu_parar", "trecho": "não me mande mais mensagens"}
    if motivo_texto is not None:
        args["motivo_texto"] = motivo_texto
    return step(call("encerrar", **args))


@pytest.fixture
def on(chan):
    chan.seed_agent()
    return chan


def _eventos(chan) -> list:
    return chan.threads._opt_out_eventos


# ── the tool ────────────────────────────────────────────────────────────────


class TestEncerrarLeadPediuParar:
    def _turno_que_pede_para_parar(self, on, **kw):
        on.use_provider(FakeProvider(tool_responses=[_parar(**kw), say("Entendido, não envio mais mensagens."),
                                                     *[say(f"R{i}?") for i in range(5)]]))
        return on.turn(turn_body(PEDIDO, ids=["a"])).json()

    def test_every_participation_of_the_lead_is_ended_in_the_same_call(self, on):
        # two participations before the opt-out: Julia (turn 1 of the lead), another agent paused in thread 2
        on.use_provider(FakeProvider(tool_responses=[say("Olá, em que posso ajudar?"), _parar(),
                                                     say("Entendido."), *[say(f"R{i}?") for i in range(5)]]))
        primeiro = on.turn(turn_body("Oi", ids=["a"])).json()
        lead = on.lead_ref()
        outro = uuid4()
        t2 = on.rt.stores.conversations.create_channel(
            on.org_id, outro, "whatsapp", {"connection_id": str(UUID(int=5)), "chat_id": "chat-2"}, None,
            lead_ref_id=lead.id)
        on.threads.add_participante(on.org_id, t2.id, outro)
        on.threads.transicionar(on.org_id, t2.id, outro, de=("ativo",), para="pausado", ator_tipo="usuario")
        body = on.turn(turn_body(PEDIDO, ids=["b"])).json()
        assert [a["type"] for a in body["actions"]] == ["encerrar"] and body["actions"][0]["lead_opt_out"] is True
        assert on.threads.get_participante(on.org_id, UUID(primeiro["thread_id"]), on.agent.id).estado == "encerrado"
        assert on.threads.get_participante(on.org_id, t2.id, outro).estado == "encerrado"
        [ev] = _eventos(on)
        assert ev.participantes_encerrados == 1  # the other agent: this one was already moved by the tool itself

    def test_the_event_records_who_why_and_what_the_lead_said(self, on):
        first = self._turno_que_pede_para_parar(on)
        [ev] = _eventos(on)
        assert ev.origem == "agente" and ev.agent_id == on.agent.id and ev.thread_id == UUID(first["thread_id"])
        assert ev.motivo == "O lead pediu para parar de receber mensagens"
        assert ev.mensagem_lead == PEDIDO
        assert ev.lead_ref_id == on.lead_ref().id and ev.ator_user_id is None

    def test_the_owner_is_notified_once_and_the_status_is_recorded(self, on):
        self._turno_que_pede_para_parar(on)
        [ev] = _eventos(on)
        assert (ev.notificacao_status, ev.notificacao_erro) == ("enviada", None) and ev.notificado_em is not None
        [n] = on.notificacoes.sent
        assert n["user_id"] == ADMIN and n["kind"] == KIND_LEAD_OPT_OUT and n["org_id"] == on.org_id
        assert n["title"] == "Lead pediu para não ser mais contatado"
        assert "Fulano" in n["message"] or "contato-1" in n["message"]
        assert "O lead pediu para parar" in n["message"]
        assert n["metadata"]["evento_id"] == str(ev.id) and n["metadata"]["dedup_key"] == dedup_key(ev.id)
        assert n["metadata"]["lead_ref"] == "contato-1" and n["metadata"]["thread_id"] == str(ev.thread_id)

    def test_the_motivo_texto_is_required_for_this_motive(self, on):
        on.use_provider(FakeProvider(tool_responses=[_parar(motivo_texto=None), say("Ok"), *[say("R?")] * 5]))
        body = on.turn(turn_body(PEDIDO, ids=["a"])).json()
        assert body["actions"] == [] and _eventos(on) == [] and on.notificacoes.sent == []
        assert on.lead_ref().opt_out_ativo is False
        [p] = on.threads.list_participantes(on.org_id, UUID(body["thread_id"]))
        assert p.estado == "ativo"  # nothing moved: a refused call changes nothing

    def test_a_lead_with_an_opt_out_is_refused_by_the_controls_for_every_agent(self, on):
        self._turno_que_pede_para_parar(on)
        calls = model_calls(on)
        body = on.turn(turn_body("Alguém aí?", ids=["b"])).json()
        assert body["status"] == STATUS_LEAD_OPT_OUT and body["reply"]["partes"] == [] and model_calls(on) == calls
        view = ThreadView(lead_opt_out=on.lead_ref().opt_out_ativo, ultima_mensagem_lead_em=AGORA)
        for participante in (None, ParticipanteView("ativo", AGORA), ParticipanteView("pausado", AGORA),
                             ParticipanteView("encerrado", AGORA), ParticipanteView("transferido", AGORA)):
            for modo in ("ligado", "drenando"):
                d = decidir(modo, view, participante, "mensagem", AGORA)
                assert d.status == STATUS_LEAD_OPT_OUT and not d.executar_llm, (participante, modo)

    def test_another_encerrar_motive_is_not_an_opt_out(self, on):
        on.use_provider(FakeProvider(tool_responses=[step(call("encerrar", motivo="sem_interesse")), say("Ok"),
                                                     *[say("R?")] * 5]))
        body = on.turn(turn_body("Sem interesse, obrigado", ids=["a"])).json()
        assert body["actions"][0] == {"type": "encerrar", "motivo": "sem_interesse", "lead_opt_out": False, "seq": 1}
        assert on.lead_ref().opt_out_ativo is False and _eventos(on) == [] and on.notificacoes.sent == []

    def test_an_earlier_encerrar_does_not_swallow_the_request_to_stop(self, on):
        on.use_provider(FakeProvider(tool_responses=[
            step(call("encerrar", motivo="sem_interesse")), step(call("encerrar", motivo="lead_pediu_parar",
                                                                       motivo_texto="Pediu para parar",
                                                                       trecho="não me mande mais mensagens")),
            say("Ok"), *[say("R?")] * 5]))
        body = on.turn(turn_body(PEDIDO, ids=["a"])).json()
        assert body["actions"] == [{"type": "encerrar", "motivo": "lead_pediu_parar", "lead_opt_out": True, "seq": 1}]
        assert on.lead_ref().opt_out_ativo is True and len(_eventos(on)) == 1 and len(on.notificacoes.sent) == 1


# ── the notification can fail; the opt-out cannot be undone by it ───────────


class TestNotificationFailureNeverBlocksTheOptOut:
    def test_a_failing_sink_marks_the_event_falhou_logs_an_error_and_keeps_the_opt_out(self, on, caplog):
        on.notificacoes.fail_with = RuntimeError("core down")
        on.use_provider(FakeProvider(tool_responses=[_parar(), say("Entendido."), *[say("R?")] * 5]))
        with caplog.at_level("ERROR"):
            body = on.turn(turn_body(PEDIDO, ids=["a"])).json()
        assert body["actions"][0]["lead_opt_out"] is True
        assert on.lead_ref().opt_out_ativo is True
        [ev] = _eventos(on)
        assert ev.notificacao_status == "falhou" and "core down" in (ev.notificacao_erro or "")
        assert any("notificacao_falhou" in r.getMessage() and r.levelname == "ERROR" for r in caplog.records)

    def test_an_org_without_an_owner_or_admin_is_a_failed_notification_not_a_skipped_one(self, on):
        on.notificacoes.org_admins = {}
        on.use_provider(FakeProvider(tool_responses=[_parar(), say("Entendido."), *[say("R?")] * 5]))
        on.turn(turn_body(PEDIDO, ids=["a"]))
        [ev] = _eventos(on)
        assert ev.notificacao_status == "falhou" and "no owner/admin" in (ev.notificacao_erro or "")
        assert on.lead_ref().opt_out_ativo is True and on.notificacoes.sent == []


# ── the service on its own ──────────────────────────────────────────────────


def test_the_service_without_a_sink_records_a_failed_notification():
    threads = FakeThreadStore()
    org = uuid4()
    threads.upsert_lead_ref(org, "l1")
    res = OptOutService(threads, None).registrar(org, "l1", origem="operador", motivo="a pedido", ator_user_id=uuid4())
    assert res.evento.notificacao_status == "falhou" and "not configured" in res.evento.notificacao_erro
    assert res.evento.origem == "operador" and threads.get_lead_ref_by_externa(org, "l1").opt_out_ativo


def test_a_repeat_while_in_force_records_no_second_event_and_notifies_nobody_again():
    threads, sink, org = FakeThreadStore(), None, uuid4()
    sink = FakeNotificationSink(org_admins={org: ["u1", "u2"]})
    svc = OptOutService(threads, sink)
    a = svc.registrar(org, "l1", origem="integracao", motivo="parar")
    b = svc.registrar(org, "l1", origem="integracao", motivo="parar de novo")
    assert a.evento_novo and not b.evento_novo and a.evento.id == b.evento.id
    assert len(threads._opt_out_eventos) == 1 and len(sink.sent) == 2  # one per admin, once


def test_an_opt_in_lifts_it_and_a_new_opt_out_is_a_new_event_and_notice():
    threads, org = FakeThreadStore(), uuid4()
    sink = FakeNotificationSink(org_admins={org: ["u1"]})
    svc = OptOutService(threads, sink)
    first = svc.registrar(org, "l1", origem="integracao", em=AGORA)
    lead = threads.registrar_opt_in(org, "l1", origem="lead_iniciou", em=AGORA.replace(hour=13))
    assert lead.opt_out_ativo is False
    second = svc.registrar(org, "l1", origem="integracao", em=AGORA.replace(hour=14))
    assert second.evento_novo and second.evento.id != first.evento.id
    assert threads.get_lead_ref_by_externa(org, "l1").opt_out_ativo is True and len(sink.sent) == 2


def test_the_caps_and_the_default_motive():
    threads, org = FakeThreadStore(), uuid4()
    svc = OptOutService(threads, FakeNotificationSink(org_admins={org: ["u1"]}))
    ev = svc.registrar(org, "l1", origem="integracao", motivo="  ", mensagem_lead="x" * 5000).evento
    assert ev.motivo == "nao_informado" and len(ev.mensagem_lead) == 1000


def test_the_fake_store_rejects_an_unknown_origin():
    with pytest.raises(ValueError):
        FakeThreadStore().registrar_opt_out_evento(uuid4(), "l1", origem="telepatia")


# ── the API ─────────────────────────────────────────────────────────────────

ROTA = "/api/channels/leads/contato-1/opt-out"
REATIVAR = "/api/channels/leads/contato-1/reativar"
OPERADOR = str(UUID(int=0x0BE7))


def _lista(thr, qs: str = ""):
    return thr.call("GET", "/api/channels/opt-outs" + qs, *STATUS_ONLY)


def _notificar(thr, eid, *scopes, **body):
    return thr.call("POST", f"/api/channels/opt-outs/{eid}/notificar", *(scopes or TURN_ONLY),
                    json=body if body else {"ator_user_id": OPERADOR})


class TestApi:
    def test_the_post_is_exactly_401_without_credentials_and_the_list_too(self, thr):
        raw = thr.chan.client.raw()
        assert raw.request("POST", ROTA, json={}).status_code == 401
        assert raw.request("GET", "/api/channels/opt-outs").status_code == 401

    def test_post_records_the_event_with_the_given_origin_and_returns_its_id(self, thr):
        thr.thread()
        op = uuid4()
        r = thr.call("POST", ROTA, *TURN_ONLY, json={
            "origem": "operador", "motivo": "Cliente ligou pedindo para sair", "mensagem_lead": "pare",
            "ator_user_id": str(op)})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["opt_out_ativo"] is True and body["participantes_encerrados"] == 1 and body["evento_id"]
        ev = body["opt_out_evento"]
        assert ev["id"] == body["evento_id"] and ev["origem"] == "operador" and ev["ator_user_id"] == str(op)
        assert ev["motivo"] == "Cliente ligou pedindo para sair" and ev["mensagem_lead"] == "pare"
        assert ev["notificacao_status"] == "enviada" and ev["lead_nome"] == "Fulano" and ev["lead_ref"] == "contato-1"
        assert len(thr.chan.notificacoes.sent) == 1

    def test_the_defaults_are_integracao_and_nao_informado_and_a_repeat_is_idempotent(self, thr):
        thr.thread()
        a = thr.call("POST", ROTA, *TURN_ONLY, json={}).json()
        b = thr.call("POST", ROTA, *TURN_ONLY, json={}).json()
        assert a["opt_out_evento"]["origem"] == "integracao" and a["opt_out_evento"]["motivo"] == "nao_informado"
        assert b["evento_id"] == a["evento_id"] and b["participantes_encerrados"] == 0
        assert len(thr.chan.notificacoes.sent) == 1 and len(thr.store._opt_out_eventos) == 1

    @pytest.mark.parametrize("body", [{"origem": "telepatia"}, {"motivo": "x" * 501}, {"mensagem_lead": "x" * 1001},
                                      {"nada": 1}])
    def test_the_body_is_strict(self, thr, body):
        assert thr.call("POST", ROTA, *TURN_ONLY, json=body).status_code == 422

    def test_a_failed_notification_still_answers_200_and_shows_the_failure(self, thr):
        thr.thread()
        thr.chan.notificacoes.fail_with = RuntimeError("boom")
        r = thr.call("POST", ROTA, *TURN_ONLY, json={})
        assert r.status_code == 200 and r.json()["opt_out_ativo"] is True
        assert r.json()["opt_out_evento"]["notificacao_status"] == "falhou"

    def test_the_list_is_newest_first_org_scoped_and_paged(self, thr):
        for ref, hora in (("c-a", 10), ("c-b", 11), ("c-c", 12)):
            thr.store.upsert_lead_ref(thr.chan.org_id, ref, contato={"nome": f"Nome {ref}", "telefone_e164": "+5511"})
            thr.call("POST", f"/api/channels/leads/{ref}/opt-out", *TURN_ONLY,
                     json={"em": f"2026-10-21T{hora}:00:00+00:00", "motivo": f"m-{ref}"})
        outra = uuid4()
        thr.store.upsert_lead_ref(outra, "alheio")
        thr.store.registrar_opt_out_evento(outra, "alheio", motivo="de outra org")
        page = _lista(thr, "?limit=2").json()
        assert [e["lead_ref"] for e in page["items"]] == ["c-c", "c-b"] and page["next_cursor"]
        assert page["items"][0]["lead_nome"] == "Nome c-c" and page["items"][0]["lead_telefone"] == "+5511"
        rest = _lista(thr, f"?limit=2&cursor={page['next_cursor']}").json()
        assert [e["lead_ref"] for e in rest["items"]] == ["c-a"] and rest["next_cursor"] is None
        assert _lista(thr, "?cursor=lixo").status_code == 422

    def test_the_thread_detail_exposes_the_latest_event(self, thr):
        t = thr.thread()
        assert thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()["opt_out_evento"] is None
        thr.call("POST", ROTA, *TURN_ONLY, json={"motivo": "pediu"})
        body = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()
        assert body["opt_out_evento"]["motivo"] == "pediu" and body["opt_out_evento"]["lead_ref"] == "contato-1"

    def test_opt_in_lifts_it_and_the_response_still_names_the_last_event(self, thr):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={"em": "2026-10-21T10:00:00+00:00", "motivo": "pediu"})
        r = thr.call("PUT", "/api/channels/leads/contato-1/opt-in", *TURN_ONLY,
                     json={"origem": "lead_iniciou", "em": "2026-10-21T11:00:00+00:00"})
        assert r.status_code == 200 and r.json()["opt_out_ativo"] is False
        assert r.json()["opt_out_evento"]["motivo"] == "pediu"


class TestConsentimento:
    """``GET /api/channels/leads/{ref}/consentimento``: the consent state + latest event, independent of threads."""

    URL = "/api/channels/leads/contato-1/consentimento"

    def test_an_unknown_lead_is_404_lead_desconhecido(self, thr):
        r = thr.call("GET", "/api/channels/leads/nunca-visto/consentimento", *STATUS_ONLY)
        assert r.status_code == 404 and r.json()["code"] == "lead_desconhecido"

    def test_a_lead_without_opt_out_reads_clean(self, thr):
        thr.thread()
        body = thr.call("GET", self.URL, *STATUS_ONLY).json()
        assert body["lead_ref"] == "contato-1" and body["opt_out_ativo"] is False and body["opt_out_evento"] is None

    def test_it_names_the_event_even_when_the_lead_has_no_thread(self, thr):
        thr.call("POST", "/api/channels/leads/sem-thread/opt-out", *TURN_ONLY, json={"motivo": "pediu"})
        body = thr.call("GET", "/api/channels/leads/sem-thread/consentimento", *STATUS_ONLY).json()
        assert body["opt_out_ativo"] is True and body["opt_out_evento"]["motivo"] == "pediu"
        assert body["opt_out_evento"]["lead_ref"] == "sem-thread" and body["opt_out_evento"]["thread_id"] is None

    def test_it_is_org_scoped_and_token_only(self, thr):
        outra = uuid4()
        thr.store.upsert_lead_ref(outra, "alheio")
        assert thr.call("GET", "/api/channels/leads/alheio/consentimento", *STATUS_ONLY).status_code == 404
        thr.thread()
        assert thr.call("GET", self.URL, *TURN_ONLY).status_code == 403
        assert thr.chan.client.get(self.URL).status_code == 403  # a human session is not a channel token
        assert thr.chan.client.raw().get(self.URL).status_code == 401


class TestRenotificar:
    """``POST /api/channels/opt-outs/{id}/notificar`` (token): re-send a failed notice."""

    def _falhou(self, thr) -> str:
        thr.thread()
        thr.chan.notificacoes.fail_with = RuntimeError("boom")
        ev = thr.call("POST", ROTA, *TURN_ONLY, json={}).json()["opt_out_evento"]
        assert ev["notificacao_status"] == "falhou" and "boom" in ev["notificacao_erro"]
        thr.chan.notificacoes.fail_with = None
        return ev["id"]

    def test_a_failed_notice_is_resent_and_the_status_updated(self, thr):
        thr.chan.notificacoes.org_admins[thr.chan.org_id] = [ADMIN]
        eid = self._falhou(thr)
        r = _notificar(thr, eid)
        assert r.status_code == 200, r.text
        assert r.json()["notificacao_status"] == "enviada" and r.json()["notificacao_erro"] is None
        assert r.json()["tipo"] == "opt_out"
        assert len(thr.chan.notificacoes.sent) == 1
        meta = thr.chan.notificacoes.sent[0]["metadata"]
        assert meta["link"] == f"/julia/opt-outs?evento={eid}" and meta["product"] == "social-wiring"
        # idempotent: an already-sent event sends nothing more
        again = _notificar(thr, eid)
        assert again.status_code == 200 and again.json()["notificacao_status"] == "enviada"
        assert len(thr.chan.notificacoes.sent) == 1

    def test_a_resend_that_fails_again_stays_falhou_with_the_error(self, thr):
        eid = self._falhou(thr)
        thr.chan.notificacoes.fail_with = RuntimeError("ainda fora")
        r = _notificar(thr, eid)
        assert r.status_code == 200 and r.json()["notificacao_status"] == "falhou"
        assert "ainda fora" in r.json()["notificacao_erro"]

    def test_unknown_event_and_other_org_are_404(self, thr):
        assert _notificar(thr, uuid4()).status_code == 404
        outra = uuid4()
        thr.store.upsert_lead_ref(outra, "alheio")
        ev = thr.store.registrar_opt_out_evento(outra, "alheio", motivo="x").evento
        assert _notificar(thr, ev.id).status_code == 404

    def test_auth_is_strict(self, thr):
        eid = self._falhou(thr)
        url = f"/api/channels/opt-outs/{eid}/notificar"
        assert thr.chan.client.raw().post(url, json={"ator_user_id": OPERADOR}).status_code == 401
        assert thr.call("POST", url, *STATUS_ONLY, json={"ator_user_id": OPERADOR}).status_code == 403  # needs turn scope
        assert thr.chan.client.post(url, json={"ator_user_id": OPERADOR}).status_code == 403  # a human session

    @pytest.mark.parametrize("body", [{}, {"ator_user_id": "nao-uuid"}, {"ator_user_id": OPERADOR, "x": 1}])
    def test_the_body_is_strict(self, thr, body):
        eid = self._falhou(thr)
        assert thr.call("POST", f"/api/channels/opt-outs/{eid}/notificar", *TURN_ONLY, json=body).status_code == 422


class TestListaDoCanal:
    """``GET /api/channels/opt-outs``: both tipos, ``lead_ref`` filter, token only."""

    def test_it_lists_opt_outs_and_reactivations_and_filters_by_lead(self, thr):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={"motivo": "pediu", "em": "2026-10-21T10:00:00+00:00"})
        thr.call("POST", "/api/channels/leads/outro/opt-out", *TURN_ONLY, json={"motivo": "outro"})
        thr.call("POST", REATIVAR, *TURN_ONLY, json={"ator_user_id": OPERADOR, "motivo": "voltou"})
        todos = _lista(thr).json()["items"]
        assert [(e["lead_ref"], e["tipo"]) for e in todos] == [
            ("contato-1", "reativacao"), ("outro", "opt_out"), ("contato-1", "opt_out")]
        so_um = _lista(thr, "?lead_ref=contato-1").json()["items"]
        assert [e["tipo"] for e in so_um] == ["reativacao", "opt_out"]
        assert _lista(thr, "?lead_ref=desconhecido").json() == {"items": [], "next_cursor": None}

    def test_limit_is_bounded_and_the_route_is_token_only(self, thr):
        assert _lista(thr, "?limit=0").status_code == 422 and _lista(thr, "?limit=101").status_code == 422
        assert thr.call("GET", "/api/channels/opt-outs", *TURN_ONLY).status_code == 403
        assert thr.chan.client.get("/api/channels/opt-outs").status_code == 403  # a human session


class TestReativar:
    """``POST /api/channels/leads/{ref}/reativar``: lift the opt-out on the record, tell the owner."""

    CORPO = {"ator_user_id": OPERADOR, "motivo": "Cliente ligou pedindo para voltar"}

    def test_it_lifts_the_opt_out_and_records_the_event(self, thr):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={"em": "2026-10-21T10:00:00+00:00", "motivo": "pediu"})
        thr.chan.notificacoes.labels[OPERADOR] = "ana@imobiliaria.com"
        r = thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["opt_out_ativo"] is False and body["opt_in_origem"] == "reativacao_manual" and body["opt_in_em"]
        ev = body["evento"]
        assert (ev["tipo"], ev["origem"], ev["ator_user_id"]) == ("reativacao", "operador", OPERADOR)
        assert ev["motivo"] == self.CORPO["motivo"] and ev["notificacao_status"] == "enviada"
        assert body["opt_out_evento"]["id"] == ev["id"]
        lead = thr.store.get_lead_ref_by_externa(thr.chan.org_id, "contato-1")
        assert lead.opt_out_ativo is False
        _opt, noticia = thr.chan.notificacoes.sent
        assert noticia["message"] == "Atendimento reativado para Fulano por ana@imobiliaria.com — Cliente ligou pedindo para voltar"
        assert noticia["title"] == "Atendimento reativado" and noticia["kind"] == "agents.lead_reativacao"
        assert noticia["metadata"]["product"] == "social-wiring"
        assert noticia["metadata"]["link"] == f"/julia/opt-outs?evento={ev['id']}"

    def test_the_consent_read_names_the_reactivation_and_a_new_opt_out_works_again(self, thr):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={"em": "2026-10-21T10:00:00+00:00"})
        thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO)
        c = thr.call("GET", "/api/channels/leads/contato-1/consentimento", *STATUS_ONLY).json()
        assert c["opt_out_ativo"] is False and c["opt_out_evento"]["tipo"] == "reativacao"
        again = thr.call("POST", ROTA, *TURN_ONLY, json={"motivo": "de novo"}).json()
        assert again["opt_out_ativo"] is True and again["opt_out_evento"]["tipo"] == "opt_out"
        assert again["opt_out_evento"]["motivo"] == "de novo"  # a NEW event, not the reactivation mistaken for it

    def test_the_operator_label_failing_still_sends_the_notice(self, thr, caplog):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={})
        thr.chan.notificacoes.label_fail_with = RuntimeError("core down")
        r = thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO)
        assert r.status_code == 200 and r.json()["evento"]["notificacao_status"] == "enviada"
        assert "por um operador" in thr.chan.notificacoes.sent[-1]["message"]
        assert "ator_nao_resolvido" in caplog.text

    def test_a_failed_notice_is_recorded_and_the_reactivation_stands(self, thr):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={})
        thr.chan.notificacoes.fail_with = RuntimeError("boom")
        r = thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO)
        assert r.status_code == 200 and r.json()["opt_out_ativo"] is False
        assert r.json()["evento"]["notificacao_status"] == "falhou" and "boom" in r.json()["evento"]["notificacao_erro"]

    def test_no_active_opt_out_is_409_and_nothing_is_written(self, thr):
        thr.thread()
        r = thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO)
        assert r.status_code == 409 and r.json()["code"] == "sem_opt_out_ativo"
        thr.call("POST", ROTA, *TURN_ONLY, json={})
        thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO)
        n = len(thr.store._opt_out_eventos)
        assert thr.call("POST", REATIVAR, *TURN_ONLY, json=self.CORPO).status_code == 409  # already lifted
        assert len(thr.store._opt_out_eventos) == n

    def test_an_unknown_lead_and_another_orgs_lead_are_404(self, thr):
        r = thr.call("POST", "/api/channels/leads/nunca-visto/reativar", *TURN_ONLY, json=self.CORPO)
        assert r.status_code == 404 and r.json()["code"] == "lead_desconhecido"
        outra = uuid4()
        thr.store.upsert_lead_ref(outra, "alheio")
        thr.store.registrar_opt_out_evento(outra, "alheio")
        assert thr.call("POST", "/api/channels/leads/alheio/reativar", *TURN_ONLY, json=self.CORPO).status_code == 404
        assert thr.store.get_lead_ref_by_externa(outra, "alheio").opt_out_ativo is True

    @pytest.mark.parametrize("body", [
        {}, {"motivo": "x"}, {"ator_user_id": OPERADOR}, {"ator_user_id": OPERADOR, "motivo": ""},
        {"ator_user_id": OPERADOR, "motivo": "   "}, {"ator_user_id": OPERADOR, "motivo": "x" * 501},
        {"ator_user_id": "nao-uuid", "motivo": "x"}, {"ator_user_id": OPERADOR, "motivo": "x", "extra": 1},
    ])
    def test_the_body_is_strict_and_actor_and_reason_are_required(self, thr, body):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={})
        assert thr.call("POST", REATIVAR, *TURN_ONLY, json=body).status_code == 422
        assert thr.store.get_lead_ref_by_externa(thr.chan.org_id, "contato-1").opt_out_ativo is True

    def test_auth_is_strict(self, thr):
        thr.thread()
        thr.call("POST", ROTA, *TURN_ONLY, json={})
        assert thr.chan.client.raw().post(REATIVAR, json=self.CORPO).status_code == 401
        assert thr.call("POST", REATIVAR, *STATUS_ONLY, json=self.CORPO).status_code == 403
        assert thr.chan.client.post(REATIVAR, json=self.CORPO).status_code == 403  # a human session


class TestReativacaoVoltaAoFluxo:
    """After a reactivation the lead is back in the agents flow: the agent that owns the line serves the next
    inbound, although its participation was ended with motivo ``opt_out``."""

    def test_opt_out_then_inbound_refused_then_reactivate_then_inbound_served(self, on):
        on.use_provider(FakeProvider(tool_responses=[
            _parar(), say("Entendido, não envio mais mensagens."), *[say(f"R{i}?") for i in range(8)]]))
        primeiro = on.turn(turn_body(PEDIDO, ids=["a"])).json()
        thread_id = UUID(primeiro["thread_id"])
        assert on.threads.get_participante(on.org_id, thread_id, on.agent.id).estado == "encerrado"

        calls = model_calls(on)
        recusado = on.turn(turn_body("Alguém aí?", ids=["b"])).json()
        assert recusado["status"] == STATUS_LEAD_OPT_OUT and model_calls(on) == calls

        with on.as_token(*BOTH):
            r = on.request("POST", REATIVAR, json={"ator_user_id": OPERADOR, "motivo": "Cliente pediu para voltar"})
        assert r.status_code == 200 and r.json()["opt_out_ativo"] is False

        servido = on.turn(turn_body("Oi, pode me atender?", ids=["c"])).json()
        assert servido["status"] != STATUS_LEAD_OPT_OUT and servido["reply"]["partes"]
        assert model_calls(on) > calls
        p = on.threads.get_participante(on.org_id, thread_id, on.agent.id)
        assert p.estado == "ativo"  # the encerrado participation was reopened by the lead's message


# ── the real store (PostgREST shapes) ──────────────────────────────────────


class TestSupabaseStore:
    def _row(self, org, lead, **over):
        base = {"id": str(uuid4()), "org_id": str(org), "lead_ref_id": str(lead), "em": "2026-10-21T10:00:00+00:00",
                "origem": "agente", "agent_id": str(uuid4()), "thread_id": str(uuid4()), "ator_user_id": None,
                "motivo": "m", "mensagem_lead": "pare", "participantes_encerrados": 2,
                "notificacao_status": "pendente", "notificacao_erro": None, "notificado_em": None,
                "created_at": "2026-10-21T10:00:00+00:00"}
        return {**base, **over}

    def test_the_rpc_carries_every_new_parameter_and_returns_the_event(self):
        from types import SimpleNamespace

        from app.stores.threads import SupabaseThreadStore
        from tests.channels.test_real_stores import ScriptedClient

        org, lead, agent = uuid4(), uuid4(), uuid4()
        row = self._row(org, lead, agent_id=str(agent))
        client = ScriptedClient(
            SimpleNamespace(data={"encontrado": True, "participantes_encerrados": 2, "evento_id": row["id"],
                                  "evento_novo": True}),
            SimpleNamespace(data=[row]))
        r = SupabaseThreadStore(client).registrar_opt_out_evento(
            org, "c1", origem="agente", motivo="m", mensagem_lead="pare", agent_id=agent, thread_id=uuid4())
        rpc = client.log[0][0]
        for p in ("p_origem", "p_motivo", "p_mensagem_lead", "p_agent_id", "p_thread_id", "p_ator_user_id"):
            assert p in rpc
        assert r.evento_novo and r.participantes_encerrados == 2 and str(r.evento.id) == row["id"]
        assert r.evento.agent_id == agent and r.evento.em.tzinfo is not None

    def test_an_unknown_lead_is_not_found(self):
        from types import SimpleNamespace

        from app.stores.threads import SupabaseThreadStore
        from tests.channels.test_real_stores import ScriptedClient

        client = ScriptedClient(SimpleNamespace(
            data={"encontrado": False, "participantes_encerrados": 0, "evento_id": None, "evento_novo": False}))
        r = SupabaseThreadStore(client).registrar_opt_out_evento(uuid4(), "nada")
        assert not r.encontrado and r.evento is None
        assert SupabaseThreadStore(ScriptedClient(SimpleNamespace(
            data={"encontrado": False}))).registrar_opt_out(uuid4(), "nada") == -1

    def test_reativar_lead_calls_the_rpc_and_reads_the_event_back(self):
        from types import SimpleNamespace

        from app.stores.threads import SupabaseThreadStore
        from tests.channels.test_real_stores import ScriptedClient

        org, lead, op = uuid4(), uuid4(), uuid4()
        row = self._row(org, lead, tipo="reativacao", origem="operador", ator_user_id=str(op), motivo="voltou")
        client = ScriptedClient(
            SimpleNamespace(data={"encontrado": True, "reativado": True, "evento_id": row["id"]}),
            SimpleNamespace(data=[row]))
        r = SupabaseThreadStore(client).reativar_lead(org, "c1", ator_user_id=op, motivo="voltou")
        rpc = client.log[0][0]
        for p in ("p_org_id", "p_ref_externa", "p_ator_user_id", "p_motivo", "p_em"):
            assert p in rpc
        assert r.reativado and r.evento.tipo == "reativacao" and r.evento.ator_user_id == op

    def test_reativar_lead_reports_unknown_and_nothing_to_lift(self):
        from types import SimpleNamespace

        from app.stores.threads import SupabaseThreadStore
        from tests.channels.test_real_stores import ScriptedClient

        desconhecido = SupabaseThreadStore(ScriptedClient(SimpleNamespace(data={"encontrado": False})))
        assert not desconhecido.reativar_lead(uuid4(), "x", ator_user_id=uuid4(), motivo="m").encontrado
        sem = SupabaseThreadStore(ScriptedClient(SimpleNamespace(data={"encontrado": True, "reativado": False})))
        r = sem.reativar_lead(uuid4(), "x", ator_user_id=uuid4(), motivo="m")
        assert r.encontrado and not r.reativado and r.evento is None

    def test_marking_the_notification_writes_status_error_and_time(self):
        from types import SimpleNamespace

        from app.stores.threads import SupabaseThreadStore
        from tests.channels.test_real_stores import ScriptedClient

        org, lead = uuid4(), uuid4()
        failed = self._row(org, lead, notificacao_status="falhou", notificacao_erro="boom")
        client = ScriptedClient(SimpleNamespace(data=[failed]))
        out = SupabaseThreadStore(client).marcar_notificacao_opt_out(org, UUID(failed["id"]), status="falhou", erro="boom")
        assert out.notificacao_status == "falhou" and out.notificacao_erro == "boom" and client.log[0][0] == "lead_opt_out_eventos"
        with pytest.raises(ValueError):
            SupabaseThreadStore(client).marcar_notificacao_opt_out(org, uuid4(), status="talvez")


class TestSupabaseSinkOrgAdmins:
    def test_it_reads_active_owner_admin_memberships_plus_the_home_org_rows_and_writes_org_scoped(self):
        from app.notifications import SupabaseNotificationSink

        org = uuid4()
        tabelas = {"org_memberships": [{"id": 1, "user_id": "u-m"}], "noctus_users": [{"id": "u-h"}, {"id": "u-m"}]}
        writes: list = []

        class Q:
            def __init__(self, nome):
                self.nome, self.f = nome, []

            def __getattr__(self, n):
                def chain(*a, **k):
                    self.f.append((n, a))
                    return self
                return chain

            def execute(self):
                from types import SimpleNamespace

                if any(n == "insert" for n, _ in self.f):
                    writes.append(self.f[0][1][0])
                    return SimpleNamespace(data=None)
                rows = tabelas[self.nome]
                rng = next((a for n, a in self.f if n == "range"), None)
                return SimpleNamespace(data=rows[rng[0]:rng[1] + 1] if rng else rows)

        class Core:
            def table(self, nome):
                return Q(nome)

        sink = SupabaseNotificationSink(Core)
        assert sink.org_admin_ids(org) == ["u-h", "u-m"]
        sink.send("u-h", kind=KIND_LEAD_OPT_OUT, title="t", message="m", metadata={"dedup_key": "k"}, org_id=org)
        [[row]] = writes
        assert row["user_id"] == "u-h" and row["org_id"] == str(org) and row["metadata"]["tipo"] == KIND_LEAD_OPT_OUT

    def test_a_participation_ended_with_motivo_opt_out_by_the_api_is_reopened_too(self, on):
        on.use_provider(FakeProvider(tool_responses=[say("Olá!"), say("Bem-vindo de volta."), *[say(f"R{i}?") for i in range(8)]]))
        thread_id = UUID(on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"])
        with on.as_token(*BOTH):
            assert on.request("POST", ROTA, json={"motivo": "pediu"}).status_code == 200
        p = on.threads.get_participante(on.org_id, thread_id, on.agent.id)
        assert (p.estado, p.motivo) == ("encerrado", "opt_out")
        assert on.turn(turn_body("Alô?", ids=["b"])).json()["status"] == STATUS_LEAD_OPT_OUT
        with on.as_token(*BOTH):
            assert on.request("POST", REATIVAR, json={"ator_user_id": OPERADOR, "motivo": "voltou"}).status_code == 200
        servido = on.turn(turn_body("Oi de novo", ids=["c"])).json()
        assert servido["status"] != STATUS_LEAD_OPT_OUT and servido["reply"]["partes"]
        assert on.threads.get_participante(on.org_id, thread_id, on.agent.id).estado == "ativo"
