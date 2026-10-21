"""Hand-off notes, the lead's consent (opt-in / opt-out), timed pauses, the per-agent thread context and the
multi-agent history labels (Julia v2 A-THREAD). Real stores (Fake halves) + the real app for the routes."""
from __future__ import annotations

import json

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.channels.controles import (
    STATUS_LEAD_OPT_OUT,
    STATUS_NORMAL,
    STATUS_REENGAJAMENTO_IGNORADO,
    ParticipanteView,
    ThreadView,
    Transicao,
    aplicar_controles,
    decidir,
)
from app.channels.thread_service import alterar_estado_humano
from app.stores.agent_controles import FakeAgentControleStore
from app.stores.conversations import FakeConversationStore
from app.stores.errors import Conflict, NotFound
from app.stores.messages import FakeMessageStore
from app.stores.threads import (
    FakeThreadStore,
    HandoffDestino,
    OutroAgenteAtivo,
    SupabaseThreadStore,
    contexto_thread,
    historico_do_agente,
    rotular_historico,
)
from tests.channels.test_channel_threads_router import (  # noqa: F401 — fixtures + helpers
    STATUS_ONLY, TURN_ONLY, _code, thr,
)
from tests.channels.test_real_stores import ScriptedClient, _unique_violation

ORG = UUID(int=1)
JULIA, JURIDICO = UUID(int=11), UUID(int=12)
OWNER = UUID(int=700)
REF = {"connection_id": str(UUID(int=77)), "chat_id": "chat-1"}
AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self) -> None:
        self.conversations = FakeConversationStore()
        self.messages = FakeMessageStore()
        self.threads = FakeThreadStore(self.conversations)
        lead = self.threads.upsert_lead_ref(ORG, "contato-1")
        self.thread = self.conversations.create_channel(ORG, JULIA, "whatsapp", REF, None, lead_ref_id=lead.id)
        self.threads.add_participante(ORG, self.thread.id, JULIA)

    def handoff(self, **kw):
        return self.threads.registrar_handoff(
            ORG, self.thread.id, JULIA, para=kw.pop("para", HandoffDestino.dono_da_org()),
            motivo_codigo=kw.pop("motivo_codigo", "lead_qualificado"),
            resumo=kw.pop("resumo", "Quer comprar apto 2 quartos na zona sul."), **kw,
        )


@pytest.fixture
def w() -> World:
    return World()


# ── hand-off ───────────────────────────────────────────────────────────────


def test_a_handoff_defaults_to_the_org_owner_and_carries_the_profile_and_masked_identity(w):
    h = w.handoff(
        perfil={"estagio": "quente", "imoveis_curtidos": ["AP123"], "intencao_visita": True},
        identificacao_completa=True, identificacao_mascarada={"cpf": "***.456.789-**"},
        perguntas_abertas=["aceita financiamento?"], compromissos=[{"quem": "corretor", "o_que": "liga amanha"}],
    )
    assert (h.para.tipo, h.para.papel) == ("papel", "dono_org")
    assert h.perfil["estagio"] == "quente" and h.identificacao_completa is True
    assert h.identificacao_mascarada == {"cpf": "***.456.789-**"}
    assert h.compromissos == [{"quem": "corretor", "o_que": "liga amanha"}] and h.lead_ref_id == w.thread.lead_ref_id
    assert w.threads.get_participante(ORG, w.thread.id, JULIA).estado == "transferido"
    assert w.threads.get_handoff(ORG, h.id) == h and w.threads.get_handoff(UUID(int=2), h.id) is None


def test_the_giver_must_be_active_or_the_note_is_not_written(w):
    w.threads.transicionar(ORG, w.thread.id, JULIA, de=["ativo"], para="concluido", ator_tipo="agente")
    with pytest.raises(Conflict):
        w.handoff()
    assert w.threads.list_handoffs(ORG, w.thread.id) == []


def test_a_handoff_to_a_human_user_and_to_another_agent(w):
    h = w.handoff(para=HandoffDestino("humano", user_id=OWNER), para_estado="pausado")
    assert h.para.user_id == OWNER and w.threads.get_participante(ORG, w.thread.id, JULIA).estado == "pausado"
    w2 = World()
    h2 = w2.handoff(para=HandoffDestino("agente", agent_id=JURIDICO))
    assert w2.threads.get_participante(ORG, w2.thread.id, JURIDICO).estado == "ativo"
    assert w2.threads.ultimo_handoff(ORG, w2.thread.id, para_agent_id=JURIDICO) == h2


def test_destinations_must_name_exactly_their_own_target():
    for bad in (dict(tipo="agente"), dict(tipo="humano"), dict(tipo="papel"), dict(tipo="humano", user_id=OWNER, papel="x"),
                dict(tipo="outro", papel="x")):
        with pytest.raises(ValueError):
            HandoffDestino(**bad)


def test_a_handoff_needs_a_reason_and_a_summary(w):
    with pytest.raises(ValueError):
        w.handoff(resumo="")
    with pytest.raises(ValueError):
        w.handoff(motivo_codigo="")


def test_acceptance_is_idempotent_first_wins(w):
    h = w.handoff()
    first = w.threads.aceitar_handoff(ORG, h.id, OWNER)
    again = w.threads.aceitar_handoff(ORG, h.id, uuid4())
    assert first.aceito_por == OWNER and again.aceito_por == OWNER and again.aceito_em == first.aceito_em
    with pytest.raises(NotFound):
        w.threads.aceitar_handoff(ORG, uuid4(), OWNER)


def test_the_handoff_goes_with_its_thread_on_erasure(w):
    w.handoff()
    w.threads.purge_thread(ORG, w.thread.id)
    assert w.threads.list_handoffs(ORG, w.thread.id) == []


# ── consent ────────────────────────────────────────────────────────────────


def test_opt_out_ends_every_agents_participation_in_every_thread_and_is_idempotent(w):
    other = w.conversations.create_channel(ORG, JULIA, "whatsapp", {**REF, "chat_id": "chat-2"}, None, lead_ref_id=w.thread.lead_ref_id)
    w.threads.add_participante(ORG, other.id, JULIA)
    w.threads.transicionar(ORG, other.id, JULIA, de=["ativo"], para="pausado", ator_tipo="usuario")
    assert w.threads.registrar_opt_out(ORG, "contato-1", em=AGORA) == 2
    for t in (w.thread, other):
        p = w.threads.get_participante(ORG, t.id, JULIA)
        assert (p.estado, p.motivo) == ("encerrado", "opt_out")
    assert w.threads.registrar_opt_out(ORG, "contato-1", em=AGORA) == 0
    assert w.threads.registrar_opt_out(ORG, "desconhecido") == -1
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1").opt_out_ativo is True


def test_a_later_opt_in_lifts_the_opt_out_and_an_earlier_one_does_not(w):
    w.threads.registrar_opt_in(ORG, "contato-1", origem="lead_iniciou", em=AGORA - timedelta(days=2))
    w.threads.registrar_opt_out(ORG, "contato-1", em=AGORA - timedelta(days=1))
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1").opt_out_ativo is True
    lead = w.threads.registrar_opt_in(ORG, "contato-1", origem="formulario_meta", em=AGORA)
    assert lead.opt_out_ativo is False and lead.opt_in_origem == "formulario_meta"
    with pytest.raises(ValueError):
        w.threads.registrar_opt_in(ORG, "contato-1", origem="spam")


def test_a_lead_who_opted_out_is_recorded_but_never_answered_nor_followed_up():
    t = ThreadView(ultima_mensagem_lead_em=AGORA, lead_opt_out=True)
    p = ParticipanteView("ativo", AGORA)
    msg = decidir("ligado", t, p, "mensagem", AGORA)
    assert (msg.status, msg.persistir_inbound, msg.executar_llm) == (STATUS_LEAD_OPT_OUT, True, False)
    reeng = decidir("ligado", t, p, "reengajamento", AGORA)
    assert (reeng.status, reeng.executar_llm, reeng.persistir_inbound) == (STATUS_REENGAJAMENTO_IGNORADO, False, False)


def test_after_an_opt_out_a_message_does_not_reopen_the_thread():
    w = World()
    w.threads.registrar_opt_out(ORG, "contato-1", em=AGORA - timedelta(days=3))
    controles = FakeAgentControleStore()
    controles.set(ORG, JULIA, modo="ligado")
    res = aplicar_controles(
        org_id=ORG, agent_id=JULIA, gatilho="mensagem", channel="whatsapp", channel_ref=REF,
        controles=controles, conversations=w.conversations, threads=w.threads, agora=AGORA,
    )
    assert res.status == STATUS_LEAD_OPT_OUT and res.participante.estado == "encerrado"


# ── timed pause ────────────────────────────────────────────────────────────


def test_a_timed_pause_records_who_why_and_until_when(w):
    ate = AGORA + timedelta(hours=20)
    alterar_estado_humano(org_id=ORG, thread_id=w.thread.id, agent_id=JULIA, para="pausado",
                          ator_user_id=OWNER, motivo="cliente pediu até amanhã", threads=w.threads, ate=ate)
    p = w.threads.get_participante(ORG, w.thread.id, JULIA)
    assert p.pausado_ate == ate
    ev = w.threads.list_eventos(ORG, w.thread.id)[-1]
    assert (ev.ator_id, ev.motivo, ev.ate) == (OWNER, "cliente pediu até amanhã", ate)
    alterar_estado_humano(org_id=ORG, thread_id=w.thread.id, agent_id=JULIA, para="ativo",
                          ator_user_id=OWNER, motivo=None, threads=w.threads)
    assert w.threads.get_participante(ORG, w.thread.id, JULIA).pausado_ate is None


def test_a_pause_that_ran_out_counts_as_active_and_records_the_resume():
    ate = AGORA - timedelta(minutes=1)
    d = decidir("ligado", ThreadView(AGORA), ParticipanteView("pausado", AGORA, pausado_ate=ate), "mensagem", AGORA)
    assert (d.status, d.executar_llm) == (STATUS_NORMAL, True)
    assert d.transicao == Transicao(de=("pausado",), para="ativo", motivo="pausa_expirada")
    live = decidir("ligado", ThreadView(AGORA), ParticipanteView("pausado", AGORA, pausado_ate=AGORA + timedelta(hours=1)), "mensagem", AGORA)
    assert live.status == "conversa_pausada"
    reeng = decidir("ligado", ThreadView(AGORA), ParticipanteView("pausado", AGORA, pausado_ate=ate), "reengajamento", AGORA)
    assert reeng.status == STATUS_NORMAL  # the pause is over: the follow-up may run


def test_an_expired_pause_that_the_drain_closes_moves_from_pausado_not_ativo():
    ate = AGORA - timedelta(minutes=1)
    d = decidir("drenando", ThreadView(AGORA - timedelta(days=9)), ParticipanteView("pausado", AGORA - timedelta(days=30), pausado_ate=ate),
                "mensagem", AGORA)
    assert d.transicao == Transicao(de=("pausado",), para="encerrado", motivo="dreno_inativo")


def test_applying_an_expired_pause_resumes_the_participant_in_the_database_state():
    w = World()
    controles = FakeAgentControleStore()
    controles.set(ORG, JULIA, modo="ligado")
    w.threads.transicionar(ORG, w.thread.id, JULIA, de=["ativo"], para="pausado", ator_tipo="usuario", ate=AGORA - timedelta(minutes=5))
    res = aplicar_controles(
        org_id=ORG, agent_id=JULIA, gatilho="mensagem", channel="whatsapp", channel_ref=REF,
        controles=controles, conversations=w.conversations, threads=w.threads, agora=AGORA,
    )
    assert res.prosseguir and res.participante.estado == "ativo" and res.participante.pausado_ate is None
    assert w.threads.list_eventos(ORG, w.thread.id)[-1].motivo == "pausa_expirada"


# ── per-agent context + history labels ─────────────────────────────────────


def test_the_context_has_labelled_messages_the_latest_handoff_and_only_the_agents_own_tool_blocks(w):
    t = w.thread.id
    w.messages.add(ORG, t, "user", "Quero apartamento")
    w.messages.add(ORG, t, "assistant", "Compra ou aluguel?", agent_id=JULIA, blocks=[{"type": "tool", "name": "registrar_perfil"}])
    w.messages.add(ORG, t, "humano", "Sou o corretor", autor_user_id=OWNER)
    w.messages.add(ORG, t, "assistant", "Posso ajudar com a papelada", agent_id=JURIDICO, blocks=[{"type": "tool", "name": "segredo_juridico"}])
    w.messages.add(ORG, t, "evento", "transferido")
    h = w.handoff()
    ctx = contexto_thread(w.messages, w.threads, {JULIA: ("julia", "Julia"), JURIDICO: ("juridico", "Jurídico")}, ORG, t, JULIA, n=20)
    assert [i.origem for i in ctx.mensagens] == ["lead", "proprio", "humano", "outro_agente", "evento"]
    assert ctx.mensagens[3].agent_nome == "Jurídico" and ctx.handoff == h
    assert [b["name"] for b in ctx.blocos_proprios] == ["registrar_perfil"]  # the other agent's scratchpad stays private
    ctx_j = contexto_thread(w.messages, w.threads, {}, ORG, t, JURIDICO, n=20)
    assert [b["name"] for b in ctx_j.blocos_proprios] == ["segredo_juridico"]


def test_the_context_is_the_last_n_not_the_whole_history(w):
    for i in range(30):
        w.messages.add(ORG, w.thread.id, "user", f"m{i}")
    ctx = contexto_thread(w.messages, w.threads, {}, ORG, w.thread.id, JULIA, n=5)
    assert [i.texto for i in ctx.mensagens] == [f"m{i}" for i in range(25, 30)] and ctx.handoff is None


def test_a_handoff_to_the_agent_wins_over_a_newer_note_to_someone_else(w):
    first = w.threads.registrar_handoff(ORG, w.thread.id, JULIA, para=HandoffDestino("agente", agent_id=JURIDICO),
                                        motivo_codigo="juridico", resumo="para o juridico")
    w.threads.transicionar(ORG, w.thread.id, JURIDICO, de=["ativo"], para="transferido", ator_tipo="agente")
    ctx = contexto_thread(w.messages, w.threads, {}, ORG, w.thread.id, JURIDICO, n=5)
    assert ctx.handoff == first


def test_history_is_rendered_by_authorship_in_tagged_envelopes_never_as_typed_labels(w):
    t = w.thread.id
    w.messages.add(ORG, t, "user", "oi")
    w.messages.add(ORG, t, "assistant", "ola", agent_id=JULIA)
    w.messages.add(ORG, t, "assistant", "documentos", agent_id=JURIDICO)
    w.messages.add(ORG, t, "humano", "ligo já")
    w.messages.add(ORG, t, "evento", "visita marcada")
    w.messages.add(ORG, t, "system", "O turno falhou.")
    w.messages.add(ORG, t, "assistant", "", agent_id=JULIA)
    itens = historico_do_agente(w.messages, {JURIDICO: ("juridico", "Jurídico")}, ORG, t, JULIA, limite=50)
    linhas = rotular_historico(itens, tag="ab12cd34")
    assert [r for r, _ in linhas] == ["user", "assistant", "system", "system", "system"]
    assert linhas[0] == ("user", "oi") and linhas[1] == ("assistant", "ola")
    envs = [json.loads(x)["plataforma_ab12cd34"] for _, x in linhas[2:]]
    assert [(e["autor_tipo"], e.get("nome"), e.get("texto") or e.get("codigo")) for e in envs] == [
        ("agente", "Jurídico", "documentos"), ("humano", None, "ligo já"), ("evento", None, "visita marcada")]
    assert all("\n" not in x for _, x in linhas)  # one physical line each
    # no foreign rows -> nothing to render, and no label text is needed for them
    solo = historico_do_agente(w.messages, {}, ORG, t, JURIDICO, limite=1)
    assert rotular_historico(solo[:0], tag="ab12cd34") == []


def test_a_legacy_unauthored_assistant_row_reads_as_the_openers_own(w):
    w.messages.add(ORG, w.thread.id, "assistant", "mensagem antiga")  # written before 033 stamped agent_id
    [it] = historico_do_agente(w.messages, {}, ORG, w.thread.id, JULIA, limite=5)
    assert it.origem == "proprio"


def test_the_assistant_message_stamp_round_trips(w):
    spec, skill = uuid4(), uuid4()
    m = w.messages.add(ORG, w.thread.id, "assistant", "x", agent_id=JULIA, compiled_hash="sha256:a",
                       definition_version_id=spec, org_specs_hash="sha256:b", skill_version_ids=[skill])
    got = w.messages.list(ORG, w.thread.id)[0]
    assert (got.definition_version_id, got.compiled_hash, got.org_specs_hash, got.skill_version_ids) == (spec, "sha256:a", "sha256:b", [skill])
    legacy = w.messages.add(ORG, w.thread.id, "assistant", "y")
    assert legacy.definition_version_id is None and legacy.skill_version_ids is None and m.id != legacy.id


# ── Real store shapes ──────────────────────────────────────────────────────


def _handoff_row(org, thread, de):
    return {
        "id": str(uuid4()), "org_id": str(org), "thread_id": str(thread), "lead_ref_id": None, "de_agent_id": str(de),
        "para_tipo": "papel", "para_agent_id": None, "para_user_id": None, "para_papel": "dono_org",
        "motivo_codigo": "lead_qualificado", "resumo": "r", "perfil": {"estagio": "quente"},
        "identificacao_completa": True, "identificacao_mascarada": {"cpf": "***"}, "perguntas_abertas": [],
        "compromissos": [], "created_at": datetime.now(timezone.utc).isoformat(), "aceito_em": None, "aceito_por": None,
    }


def test_real_handoff_is_one_rpc_carrying_the_whole_note_then_a_read():
    org, thread, giver = uuid4(), uuid4(), uuid4()
    row = _handoff_row(org, thread, giver)
    client = ScriptedClient(SimpleNamespace(data=row["id"]), SimpleNamespace(data=[row]))
    rec = SupabaseThreadStore(client).registrar_handoff(
        org, thread, giver, para=HandoffDestino.dono_da_org(), motivo_codigo="lead_qualificado", resumo="r",
        perfil={"estagio": "quente"}, identificacao_completa=True, identificacao_mascarada={"cpf": "***"},
    )
    assert rec.para.papel == "dono_org" and rec.identificacao_mascarada == {"cpf": "***"}
    rpc = client.log[0][0]
    assert rpc.startswith("rpc:transferir_thread")
    for p in ("p_perfil", "p_identificacao_completa", "p_identificacao_mascarada", "p_compromissos", "p_perguntas", "p_para_papel"):
        assert p in rpc


def test_real_handoff_to_a_thread_another_agent_holds_is_the_one_active_conflict():
    with pytest.raises(OutroAgenteAtivo):
        SupabaseThreadStore(ScriptedClient(_unique_violation())).registrar_handoff(
            uuid4(), uuid4(), uuid4(), para=HandoffDestino("agente", agent_id=uuid4()), motivo_codigo="x", resumo="y")


def test_real_handoff_whose_giver_moved_surfaces_the_rolled_back_conflict():
    from postgrest.exceptions import APIError

    err = APIError({"code": "P0001", "message": "participante_estado_mudou", "details": "", "hint": ""})
    with pytest.raises(Conflict) as exc:
        SupabaseThreadStore(ScriptedClient(err)).registrar_handoff(uuid4(), uuid4(), uuid4(), para=HandoffDestino.dono_da_org(),
                                                                    motivo_codigo="x", resumo="y")
    assert not isinstance(exc.value, OutroAgenteAtivo)


def _opt_out_evento_row(org, lead_id) -> dict:
    return {"id": str(uuid4()), "org_id": str(org), "lead_ref_id": str(lead_id), "em": "2026-10-21T10:00:00+00:00",
            "origem": "integracao", "agent_id": None, "thread_id": None, "ator_user_id": None, "motivo": "nao_informado",
            "mensagem_lead": None, "participantes_encerrados": 3, "notificacao_status": "pendente",
            "notificacao_erro": None, "notificado_em": None, "created_at": "2026-10-21T10:00:00+00:00"}


def test_real_opt_out_is_one_rpc_and_opt_in_a_scoped_patch():
    org = uuid4()
    lead = {"id": str(uuid4()), "org_id": str(org), "produto": "social-wiring", "ref_externa": "c1", "crm_lead_id": None,
            "contato": None, "created_at": "2026-10-19T00:00:00+00:00", "updated_at": "2026-10-19T00:00:00+00:00"}
    evento = _opt_out_evento_row(org, UUID(lead["id"]))
    rpc_result = {"encontrado": True, "participantes_encerrados": 3, "evento_id": evento["id"], "evento_novo": True}
    client = ScriptedClient(
        SimpleNamespace(data=rpc_result), SimpleNamespace(data=[evento]), SimpleNamespace(data=[lead]),
        SimpleNamespace(data=[{**lead, "opt_in_origem": "lead_iniciou"}]))
    store = SupabaseThreadStore(client)
    assert store.registrar_opt_out(org, "c1") == 3 and client.log[0][0].startswith("rpc:registrar_opt_out")
    assert store.registrar_opt_in(org, "c1", origem="lead_iniciou").opt_in_origem == "lead_iniciou"
    with pytest.raises(ValueError):
        store.registrar_opt_in(org, "c1", origem="spam")


def test_real_transicionar_sends_the_pause_end():
    client = ScriptedClient(SimpleNamespace(data=True))
    SupabaseThreadStore(client).transicionar(uuid4(), uuid4(), uuid4(), de=["ativo"], para="pausado", ator_tipo="usuario",
                                              ate=AGORA)
    assert "p_ate" in client.log[0][0]


# ── routes ─────────────────────────────────────────────────────────────────


def test_thread_get_exposes_consent_followup_suppression_and_the_latest_handoff(thr):
    org = thr.chan.org_id
    t = thr.thread()
    body = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()
    assert body["reengajamento_suprimido"] is False and body["ultimo_handoff"] is None and body["opt_out_em"] is None
    url = f"/api/channels/threads/{t.id}/participantes/julia"
    ate = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    r = thr.call("PATCH", url, *TURN_ONLY, json={"estado": "pausado", "ator_user_id": str(OWNER), "motivo": "pediu até amanhã", "ate": ate})
    assert r.status_code == 200 and r.json()["pausado_ate"] is not None
    body = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()
    assert (body["reengajamento_suprimido"], body["reengajamento_suprimido_motivo"]) == (True, "pausado")
    thr.call("PATCH", url, *TURN_ONLY, json={"estado": "ativo", "ator_user_id": str(OWNER)})
    r = thr.call("POST", "/api/channels/leads/contato-1/opt-out", *TURN_ONLY, json={})
    assert r.status_code == 200 and r.json()["opt_out_ativo"] is True and r.json()["participantes_encerrados"] == 1
    body = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()
    assert (body["reengajamento_suprimido"], body["reengajamento_suprimido_motivo"]) == (True, "opt_out")
    assert body["participantes"][0]["estado"] == "encerrado" and body["opt_out_em"] is not None
    r = thr.call("PUT", "/api/channels/leads/contato-1/opt-in", *TURN_ONLY, json={"origem": "lead_iniciou"})
    assert r.json()["opt_out_ativo"] is False
    assert thr.store.get_lead_ref_by_externa(org, "contato-1").opt_in_origem == "lead_iniciou"


def test_a_pause_end_must_be_a_future_pause(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/participantes/julia"
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    fut = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert thr.call("PATCH", url, *TURN_ONLY, json={"estado": "pausado", "ator_user_id": str(OWNER), "ate": past}).status_code == 422
    assert thr.call("PATCH", url, *TURN_ONLY, json={"estado": "ativo", "ator_user_id": str(OWNER), "ate": fut}).status_code == 422


def test_opt_out_registers_a_lead_that_has_no_thread_yet(thr):
    r = thr.call("POST", "/api/channels/leads/novo-lead/opt-out", *TURN_ONLY, json={})
    assert r.status_code == 200 and r.json()["participantes_encerrados"] == 0 and r.json()["opt_out_ativo"] is True


def test_consent_is_org_scoped(thr):
    thr.thread()
    from tests.channels.conftest import OTHER_ORG

    thr.call("POST", "/api/channels/leads/contato-1/opt-out", *TURN_ONLY, json={}, token={"org_id": OTHER_ORG})
    assert thr.store.get_lead_ref_by_externa(thr.chan.org_id, "contato-1").opt_out_em is None


def test_sw_reads_and_renders_the_handoff_and_the_human_accepts_it(thr):
    t = thr.thread()
    h = thr.store.registrar_handoff(
        thr.chan.org_id, t.id, thr.chan.agent.id, para=HandoffDestino.dono_da_org(), motivo_codigo="lead_qualificado",
        resumo="Quer comprar", perfil={"estagio": "quente"}, identificacao_completa=True,
        identificacao_mascarada={"cpf": "***.456.789-**"}, compromissos=[{"quem": "corretor", "o_que": "liga amanha"}],
    )
    one = thr.call("GET", f"/api/channels/handoffs/{h.id}", *STATUS_ONLY).json()
    assert one["para"] == {"tipo": "papel", "agent_key": None, "user_id": None, "papel": "dono_org"}
    assert one["de_agent_key"] == "julia" and one["lead_ref"] == "contato-1" and one["perfil"] == {"estagio": "quente"}
    assert one["identificacao_mascarada"] == {"cpf": "***.456.789-**"} and one["aceito_em"] is None
    assert thr.call("GET", f"/api/channels/threads/{t.id}/handoffs", *STATUS_ONLY).json()[0]["id"] == str(h.id)
    assert thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()["ultimo_handoff"]["id"] == str(h.id)
    acc = thr.call("POST", f"/api/channels/handoffs/{h.id}/aceite", *TURN_ONLY, json={"user_id": str(OWNER)})
    assert acc.status_code == 200 and acc.json()["aceito_por"] == str(OWNER)
    other = thr.call("POST", f"/api/channels/handoffs/{h.id}/aceite", *TURN_ONLY, json={"user_id": str(uuid4())})
    assert other.json()["aceito_por"] == str(OWNER)


def test_a_handoff_is_invisible_to_another_org_and_when_unknown(thr):
    from tests.channels.conftest import OTHER_ORG

    t = thr.thread()
    h = thr.store.registrar_handoff(thr.chan.org_id, t.id, thr.chan.agent.id, para=HandoffDestino.dono_da_org(),
                                    motivo_codigo="x", resumo="y")
    r = thr.call("GET", f"/api/channels/handoffs/{h.id}", *STATUS_ONLY, token={"org_id": OTHER_ORG})
    assert r.status_code == 404 and _code(r) == "handoff_not_found"
    assert thr.call("GET", f"/api/channels/handoffs/{uuid4()}", *STATUS_ONLY).status_code == 404
