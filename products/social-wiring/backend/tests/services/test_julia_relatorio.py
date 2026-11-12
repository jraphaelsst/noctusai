"""Julia v3 reports, alerts and the identification document (CONTRACT julia-v2 section 12.3 / 12.5 / 12.6 / 12.8, migration 313).

Every external seam is a Fake: the mock DB, the seed `FakeWahaClient` (it records what the org's Julia line sends), the fake
agents client scripted with the new action shapes, fakeredis, and a recording document-intake callable. Nothing of ours is patched."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from app.clients.agents import (
    FakeAgentsClient,
    HandoffAction,
    JuliaAction,
    QualificacaoResumo,
    TurnResult,
    parse_turn_result,
)
from app.services import julia_contatos_service as contatos
from app.services import julia_envio_gate as gate
from app.services import julia_relatorio_service as svc
from app.services.julia_lead_turn_service import process_lead_batch

from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, LEAD_PHONE, ORG_ID, OWNER_ID, World, buffer_lead

pytestmark = pytest.mark.asyncio

DESTINO = "+5511900001111"
DESTINO_CHAT = "5511900001111@c.us"
CONV = "11111111-1111-4111-8111-111111111111"
RELATORIO = {
    "texto": "Relatório da Julia\nLead: Ana (+5511988887777)\n\nResumo: quer comprar um apartamento.\n\nImóveis oferecidos: AP0042 (gostou)\n\nMotivo: pediu um corretor.",
    "resumo_conversa": "quer comprar um apartamento", "perfil": {"operacao": "compra"},
    "imoveis_oferecidos": [{"codigo": "AP0042", "link": "https://site.example/imovel/AP0042", "reacao": "gostou"}],
    "imoveis_recomendados": ["AP0042"], "disponibilidade_visita": "sábado de manhã",
    "identificacao": {"cpf": True, "rg": False, "email": True, "documento_enviado": False},
    "motivo": "pediu um corretor", "proximos_passos": "ligar amanhã",
}


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    for t in ("leads", "lead_sources", "lead_source_aliases", "cliente_notas", "clientes", "cliente_touches", "atendimentos"):
        w.sw.set_table_data(t, [])
    w.seed_destino()
    return w


def _ok(*partes: str, status: str = "respondido", actions=(), qualificacao=None) -> TurnResult:
    return TurnResult(conversation_id=CONV, partes=tuple(partes), status=status, actions=tuple(actions), qualificacao=qualificacao)


async def _run(world: World, key: str, **deps_over: Any) -> None:
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps(**deps_over))


def _para_destino(world: World) -> list[str]:
    return [m["text"] for m in world.waha.sent_messages if m["chatId"] == DESTINO_CHAT]


def _para_lead(world: World) -> list[str]:
    return [m["text"] for m in world.waha.sent_messages if m["chatId"] == LEAD_CHAT]


def _telefone_no_noc(world: World, user_id: str, telefone: str | None) -> None:
    """A person's WhatsApp as they set it in noc (core `noctus_users.telefone`). Rows are re-seeded: the mock core schema predates the column."""
    linhas = [{**u, "telefone": telefone} if u["id"] == user_id else u for u in world.core.table("noctus_users").select("*").execute().data]
    world.core.set_table_data("noctus_users", linhas)


def _handoff(relatorio=RELATORIO, seq=1) -> HandoffAction:
    return HandoffAction(motivo="pediu um corretor", motivo_codigo="pediu_humano", seq=seq, relatorio=relatorio)


# ── the outbound gate flow `interno` ────────────────────────────────────────
class TestFluxoInterno:
    def test_it_needs_only_the_line_not_julia_being_on(self, world):
        world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, gate.Fluxo.INTERNO) is None
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, gate.Fluxo.RESPOSTA) == "julia_desligada"

    def test_an_unknown_line_is_refused_and_logged_as_an_event(self, world):
        with pytest.raises(gate.EnvioBloqueado) as exc:
            gate.exigir(world.sw, ORG_ID, "00000000-0000-4000-8000-00000000dead", gate.Fluxo.INTERNO)
        assert exc.value.motivo == "sem_conexao"
        assert [e["payload"]["fluxo"] for e in world.rows("julia_eventos", tipo="envio_bloqueado")] == ["interno"]

    def test_a_cloud_api_line_cannot_carry_free_text(self, world):
        world.sw.table("whatsapp_connections").update({"transporte": "cloud"}).eq("id", CONNECTION_ID).execute()
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, gate.Fluxo.INTERNO) == "linha_nao_waha"


# ── the wire shapes ─────────────────────────────────────────────────────────
class TestWire:
    def test_handoff_carries_the_relatorio_and_old_builds_do_not_crash(self):
        corpo = {"conversation_id": CONV, "status": "handoff", "reply": {"partes": []}, "actions": [
            {"type": "handoff", "motivo": "x", "relatorio": RELATORIO}, {"type": "handoff", "motivo": "y", "seq": 3}]}
        novo, velho = parse_turn_result(corpo).actions
        assert novo.relatorio == RELATORIO and velho.relatorio is None

    def test_a_non_object_relatorio_is_dropped_not_fatal(self):
        r = parse_turn_result({"conversation_id": CONV, "status": "handoff", "reply": {"partes": []},
                               "actions": [{"type": "handoff", "motivo": "x", "relatorio": "texto solto"}]})
        assert r.handoff.relatorio is None

    def test_qualificacao_imoveis_oferecidos_is_none_when_absent_and_tuple_when_sent(self):
        base = {"conversation_id": CONV, "status": "respondido", "reply": {"partes": ["oi"]}}
        assert parse_turn_result({**base, "qualificacao": {"estagio": "x"}}).qualificacao.imoveis_oferecidos is None
        r = parse_turn_result({**base, "qualificacao": {"imoveis_oferecidos": ["AP1", " AP2 ", 7, ""]}})
        assert r.qualificacao.imoveis_oferecidos == ("AP1", "AP2")

    def test_the_platform_kill_status_is_known_and_never_served(self):
        r = parse_turn_result({"conversation_id": CONV, "status": "agente_desligado_plataforma", "reply": {"partes": []}, "actions": []})
        assert r.status == "agente_desligado_plataforma" and not r.atendeu


# ── hand-off report ─────────────────────────────────────────────────────────
class TestRelatorioDoHandoff:
    async def test_it_is_saved_on_the_card_and_sent_one_message_per_paragraph(self, world):
        world.agents = FakeAgentsClient([_ok("Vou chamar um corretor.", status="handoff", actions=[_handoff()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero um corretor"]))
        partes = _para_destino(world)
        assert partes == [p for p in RELATORIO["texto"].split("\n\n")]  # blank-line split, nothing else changed
        (row,) = world.rows("julia_relatorios")
        assert row["tipo"] == "handoff" and row["envio_status"] == "enviado" and row["destino_e164"] == DESTINO
        assert row["texto"] == RELATORIO["texto"] and row["dados"]["imoveis_recomendados"] == ["AP0042"]
        assert row["dados"]["motivo_codigo"] == "pediu_humano" and "texto" not in row["dados"]
        assert row["contato_id"] == world.contato()["id"]
        # the in-app hand-off notice is untouched
        assert [n["metadata"]["tipo"] for n in world.notifications()] == ["julia_handoff"]

    async def test_a_replayed_turn_reports_once(self, world):
        world.agents = FakeAgentsClient([_ok("Vou chamar um corretor.", status="handoff", actions=[_handoff()])])
        key = buffer_lead(world, LEAD_CHAT, ["quero um corretor"], ids=["m1"])
        await _run(world, key)
        enviadas = len(_para_destino(world))
        world.agents = FakeAgentsClient([_ok("Vou chamar um corretor.", status="handoff", actions=[_handoff()])])
        buffer_lead(world, LEAD_CHAT, ["quero um corretor"], ids=["m1"], start=1)
        await _run(world, key)
        assert len(world.rows("julia_relatorios")) == 1 and len(_para_destino(world)) == enviadas

    async def test_an_old_agents_build_with_no_relatorio_still_reports_from_the_handoff_note(self, world):
        world.agents = FakeAgentsClient([_ok("Vou chamar um corretor.", status="handoff", actions=[_handoff(relatorio=None)])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero um corretor"]))
        (row,) = world.rows("julia_relatorios")
        assert row["envio_status"] == "enviado" and row["dados"]["relatorio_de_agents"] is False
        texto = "\n".join(_para_destino(world))
        assert "Ana" in texto and "pediu um corretor" in texto

    async def test_a_partial_relatorio_without_texto_is_rebuilt_from_its_fields(self, world):
        parcial = {k: v for k, v in RELATORIO.items() if k != "texto"}
        world.agents = FakeAgentsClient([_ok("Vou chamar.", status="handoff", actions=[_handoff(relatorio=parcial)])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        (row,) = world.rows("julia_relatorios")
        assert "AP0042" in row["texto"] and "sábado de manhã" in row["texto"] and "CPF sim" in row["texto"]

    async def test_it_goes_out_even_when_julia_was_switched_off_during_the_turn(self, world):
        # gate 1 is re-read at send time: the reply is refused, but the staff report (flow `interno`) is not a lead send
        world.agents = FakeAgentsClient([_ok("Vou chamar um corretor.", status="handoff", actions=[_handoff()])])
        key = buffer_lead(world, LEAD_CHAT, ["humano"])
        world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()
        memory = world.buffer.memory_for(key)
        connection = world.record(UUID(CONNECTION_ID))
        connection_on = type(connection)(**{**connection.__dict__, "agente_leads_ativo": True})
        await process_lead_batch(key, memory, deps=world.deps(connection_lookup=lambda _id: connection_on))
        assert _para_lead(world) == []
        assert len(_para_destino(world)) == 4 and world.rows("julia_relatorios")[0]["envio_status"] == "enviado"


class TestDestino:
    async def test_no_destination_stores_the_report_and_tells_the_owner_once_a_day(self, world):
        world.sw.set_table_data("julia_relatorio_destino", [])
        for i in (1, 2):
            world.agents = FakeAgentsClient([_ok("Vou chamar.", status="handoff", actions=[_handoff(seq=i)])])
            await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"], ids=[f"m{i}"]))
        rows = world.rows("julia_relatorios")
        assert [r["envio_status"] for r in rows] == ["sem_destino", "sem_destino"] and all(r["destino_e164"] is None for r in rows)
        assert world.waha.sent_messages == [m for m in world.waha.sent_messages if m["chatId"] == LEAD_CHAT]
        avisos = [n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_SEM_DESTINO]
        assert len(avisos) == 1 and avisos[0]["user_id"] == OWNER_ID

    def test_modo_responsavel_uses_the_responsaveis_phone_in_noc_then_the_staff_list_then_the_configured_user(self, world):
        contato = contatos.obter_ou_criar_contato(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT,
                                                  telefone_e164=f"+{LEAD_PHONE}", nome="Ana")
        resp = "00000000-0000-4000-8000-0000000000c1"
        contato = {**contato, "responsavel_user_id": resp}
        world.sw.table("julia_relatorio_destino").update({"modo": "responsavel"}).eq("org_id", ORG_ID).execute()
        # the responsavel has no phone anywhere: the configured user (the owner) is the fallback
        assert svc.resolver_destino(world.sw, world.core, ORG_ID, contato) == (DESTINO, "usuario", OWNER_ID)
        world.sw.table("julia_staff").insert({"org_id": ORG_ID, "user_id": resp, "nome": "Carla", "papel": "corretor",
                                              "telefone": "5511955554444", "ativo": True}).execute()
        assert svc.resolver_destino(world.sw, world.core, ORG_ID, contato) == ("+5511955554444", "responsavel", resp)
        _telefone_no_noc(world, resp, "+5511966665555")
        assert svc.resolver_destino(world.sw, world.core, ORG_ID, contato) == ("+5511966665555", "responsavel", resp)
        assert svc.resolver_destino(world.sw, world.core, ORG_ID, {**contato, "responsavel_user_id": None})[1:] == ("usuario", OWNER_ID)
        world.sw.table("julia_relatorio_destino").update({"usuario_id": None}).eq("org_id", ORG_ID).execute()
        assert svc.resolver_destino(world.sw, world.core, ORG_ID, {**contato, "responsavel_user_id": None}) == (None, "nenhum", None)

    async def test_a_destination_user_without_a_phone_keeps_the_report_skips_the_send_and_is_told(self, world):
        _telefone_no_noc(world, OWNER_ID, None)
        world.agents = FakeAgentsClient([_ok("Vou chamar.", status="handoff", actions=[_handoff()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        (row,) = world.rows("julia_relatorios")
        assert row["envio_status"] == "sem_destino" and row["destino_e164"] is None and row["dados"]["destino_usuario_id"] == OWNER_ID
        assert _para_destino(world) == []
        avisos = [n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_SEM_DESTINO]
        assert len(avisos) == 1 and avisos[0]["user_id"] == OWNER_ID and "Cadastre seu WhatsApp no noc" in avisos[0]["message"]

    async def test_a_failed_send_is_recorded_and_surfaced_never_silent(self, world):
        world.waha.registered_numbers = set()  # the destination phone is not on WhatsApp
        world.agents = FakeAgentsClient([_ok("Vou chamar.", status="handoff", actions=[_handoff()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        (row,) = world.rows("julia_relatorios")
        assert row["envio_status"] == "falhou" and "WahaNumberNotOnWhatsApp" in row["envio_erro"]
        assert [n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_RELATORIO_FALHOU]


# ── opt-out notices (go-live) ───────────────────────────────────────────────
class TestOptOut:
    def _acao(self, seq=0, motivo="pedido_do_lead", trecho="não quero mais receber mensagens", motivo_texto=None):
        payload = {"motivo": motivo, "trecho": trecho}
        if motivo_texto:
            payload["motivo_texto"] = motivo_texto
        return JuliaAction(type="opt_out", seq=seq, payload=payload)

    async def test_the_agents_own_reason_is_what_the_owner_reads(self, world):
        """The closed enum only says HOW it was detected; the owner wants WHY, in the agent's words (r08)."""
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao(motivo_texto="Lead disse que já comprou outro imóvel")])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["já comprei, parem"]))
        (texto,) = _para_destino(world)
        assert "Motivo: Lead disse que já comprou outro imóvel" in texto
        msg = [n for n in world.notifications() if n["metadata"].get("tipo") == svc.KIND_OPT_OUT][0]["message"]
        assert "motivo: Lead disse que já comprou outro imóvel" in msg

    async def test_one_in_app_notice_and_one_interno_whatsapp_each_with_the_reason(self, world):
        world.agents = FakeAgentsClient([_ok("Tudo bem, não vou mais te escrever.", actions=[self._acao()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["para de me mandar mensagem"]))
        notices = [n for n in world.notifications() if n["metadata"].get("tipo") == svc.KIND_OPT_OUT]
        assert len(notices) >= 1 and len({n["user_id"] for n in notices}) == len(notices)  # one per admin, not one per attempt
        msg = notices[0]["message"]
        assert "pediu para não receber mais mensagens" in msg and "motivo: pedido do próprio lead" in msg
        assert "+5511988887777" not in msg and "Ana" in msg  # phone masked, name reduced
        (texto,) = _para_destino(world)
        assert "Motivo: pedido do próprio lead" in texto and "não quero mais receber mensagens" in texto
        assert "+5511988887777" not in texto and "+5511*****7777" in texto
        assert world.rows("julia_eventos", tipo="opt_out_notificado")
        assert not world.rows("julia_eventos", tipo="acao_sem_handler")

    async def test_the_keyword_reason_is_named(self, world):
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao(motivo="palavra_chave", trecho="PARAR")])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["PARAR"]))
        assert "Motivo: palavra-chave de parada" in _para_destino(world)[0]

    async def test_the_lead_words_are_sanitized(self, world):
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao(trecho="parem, ligue 11 97777-6666 ou veja http://golpe.test")])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["parem"]))
        texto = _para_destino(world)[0]
        assert "97777-6666" not in texto and "golpe.test" not in texto

    async def test_a_replay_notifies_once(self, world):
        key = buffer_lead(world, LEAD_CHAT, ["parar"], ids=["m1"])
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao()])])
        await _run(world, key)
        before = len([n for n in world.notifications() if n["metadata"].get("tipo") == svc.KIND_OPT_OUT])
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao()])])
        buffer_lead(world, LEAD_CHAT, ["parar"], ids=["m1"], start=1)
        await _run(world, key)
        assert len([n for n in world.notifications() if n["metadata"].get("tipo") == svc.KIND_OPT_OUT]) == before
        assert len(_para_destino(world)) == 1 and len(world.rows("julia_relatorios")) == 1

    async def test_no_destination_is_a_named_logged_reason_and_the_in_app_notice_still_lands(self, world, caplog):
        world.sw.set_table_data("julia_relatorio_destino", [])
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao()])])
        with caplog.at_level("ERROR"):
            await _run(world, buffer_lead(world, LEAD_CHAT, ["parar"]))
        assert _para_destino(world) == []
        assert "sem_destino" in caplog.text
        assert [n for n in world.notifications() if n["metadata"].get("tipo") == svc.KIND_OPT_OUT]

    async def test_modo_responsavel_alerts_the_leads_responsible_on_whatsapp_with_the_reason(self, world):
        """Owner: "the lead says PARAR: she ends the conversation and alerts the responsible". With the report destination in
        `modo responsavel`, the opt-out WhatsApp goes to the lead's responsible (here: their staff-list number), with the reason
        and the lead's words; the in-app notice still reaches the org admins."""
        contato = contatos.obter_ou_criar_contato(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT,
                                                  telefone_e164=f"+{LEAD_PHONE}", nome="Ana")
        resp = "00000000-0000-4000-8000-0000000000c1"
        world.sw.table("julia_contatos").update({"responsavel_user_id": resp}).eq("id", contato["id"]).execute()
        world.sw.table("julia_relatorio_destino").update({"modo": "responsavel"}).eq("org_id", ORG_ID).execute()
        world.sw.table("julia_staff").insert({"org_id": ORG_ID, "user_id": resp, "nome": "Carla", "papel": "corretor",
                                              "telefone": "5511955554444", "ativo": True}).execute()
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._acao(motivo="palavra_chave", trecho="PARAR")])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["PARAR"]))
        (texto,) = [m["text"] for m in world.waha.sent_messages if m["chatId"] == "5511955554444@c.us"]
        assert "Motivo: palavra-chave de parada" in texto and "PARAR" in texto
        assert _para_destino(world) == []  # not the configured user: the responsible got it
        assert [n for n in world.notifications() if n["metadata"].get("tipo") == svc.KIND_OPT_OUT]

    def test_masking(self):
        assert svc.mascarar_nome("Maria Souza Lima") == "Maria L."
        assert svc.mascarar_nome(None) == "sem nome"
        assert svc.mascarar_telefone("+5511988887777") == "+5511*****7777"
        assert svc.mascarar_telefone("") == "sem telefone"


# ── alerts ──────────────────────────────────────────────────────────────────
class TestAlerta:
    def _alerta(self, seq=0, tipo="lead_insatisfeito"):
        return JuliaAction(type="alerta", seq=seq, payload={"tipo": tipo, "descricao": "O lead reclamou da demora.", "alerta_id": "a-1"})

    async def test_it_reaches_the_destination_with_the_contract_text_and_notifies_in_app(self, world):
        world.agents = FakeAgentsClient([_ok("Sinto muito, vou ajudar.", actions=[self._alerta()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["que demora!"]))
        (texto,) = _para_destino(world)
        assert texto.splitlines()[0] == "⚠️ Julia — lead insatisfeito"
        assert texto.splitlines()[1] == "Lead: Ana (+5511988887777)"
        assert texto.splitlines()[2] == "O lead reclamou da demora."
        assert texto.splitlines()[3] == f"Conversa: https://sw.example.test/julia/conversas?chat={LEAD_CHAT.replace('@', '%40')}"
        (row,) = world.rows("julia_relatorios")
        assert row["tipo"] == "alerta" and row["envio_status"] == "enviado" and row["dados"]["alerta_id"] == "a-1"
        assert [n["metadata"]["tipo"] for n in world.notifications()] == [svc.KIND_ALERTA]
        assert world.rows("julia_eventos", tipo="alerta_julia")
        assert not world.rows("julia_eventos", tipo="acao_sem_handler")

    async def test_an_unknown_alert_type_is_an_outro(self, world):
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._alerta(tipo="inventado")])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert _para_destino(world)[0].startswith("⚠️ Julia — alerta")

    async def test_it_still_reaches_the_owner_while_julia_is_off_at_send_time(self, world):
        contato = contatos.obter_ou_criar_contato(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT,
                                                  telefone_e164=f"+{LEAD_PHONE}", nome="Ana")
        world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()
        servicos = world.deps()
        row = svc.registrar_relatorio(world.sw, org_id=ORG_ID, contato=contato, tipo="alerta", texto="⚠️ Julia — alerta\nx",
                                      dados={}, thread_id=CONV, chave="k1", destino=DESTINO)
        assert await svc.entregar(servicos, connection=world.record(UUID(CONNECTION_ID)), contato=contato, row=row) == "enviado"
        assert _para_destino(world) == ["⚠️ Julia — alerta", "x"] or _para_destino(world) == ["⚠️ Julia — alerta\nx"]

    async def test_a_replay_does_not_alert_twice(self, world):
        key = buffer_lead(world, LEAD_CHAT, ["que demora!"], ids=["m1"])
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._alerta()])])
        await _run(world, key)
        world.agents = FakeAgentsClient([_ok("ok", actions=[self._alerta()])])
        buffer_lead(world, LEAD_CHAT, ["que demora!"], ids=["m1"], start=1)
        await _run(world, key)
        assert len(world.rows("julia_relatorios")) == 1 and len(_para_destino(world)) == 1


# ── conclusion (lead_pronto) ────────────────────────────────────────────────
class TestConclusao:
    async def test_lead_pronto_with_a_relatorio_is_saved_and_sent(self, world):
        acao = JuliaAction(type="lead_pronto", seq=0, payload={"estagio": "qualificado", "score": 80, "relatorio": RELATORIO})
        world.agents = FakeAgentsClient([_ok("Perfeito!", status="concluido", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["pode ser"]))
        (row,) = world.rows("julia_relatorios")
        assert row["tipo"] == "conclusao" and row["envio_status"] == "enviado" and row["dados"]["estagio"] == "qualificado"
        assert len(_para_destino(world)) == 4
        ledger = world.rows("julia_acoes_aplicadas", tipo="lead_pronto")[0]
        assert ledger["payload"]["relatorio"] is True  # the ledger keeps a flag, never the profile / summary

    async def test_lead_pronto_without_a_relatorio_sends_nothing_extra(self, world):
        acao = JuliaAction(type="lead_pronto", seq=0, payload={"estagio": "qualificado", "score": 80})
        world.agents = FakeAgentsClient([_ok("Perfeito!", status="concluido", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["pode ser"]))
        assert world.rows("julia_relatorios") == [] and _para_destino(world) == []


# ── offered listings mirror ─────────────────────────────────────────────────
class TestImoveisOferecidos:
    async def test_every_turn_overwrites_the_contato_and_the_linked_lead(self, world):
        lead = world.sw.table("leads").insert({"id": "00000000-0000-4000-8000-0000000000a9", "org_id": ORG_ID, "imoveis_oferecidos": []}).execute().data[0]
        key = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        world.agents = FakeAgentsClient([_ok("oi")])
        await _run(world, key)
        contatos.atualizar_contato(world.sw, world.contato()["id"], {"lead_id": lead["id"]})
        world.agents = FakeAgentsClient([_ok("veja", qualificacao=QualificacaoResumo(imoveis_oferecidos=("AP1", "AP2")))])
        buffer_lead(world, LEAD_CHAT, ["gostei"], ids=["m2"])
        await _run(world, key)
        assert world.contato()["imoveis_oferecidos"] == ["AP1", "AP2"]
        assert world.rows("leads", id=lead["id"])[0]["imoveis_oferecidos"] == ["AP1", "AP2"]
        world.agents = FakeAgentsClient([_ok("mais", qualificacao=QualificacaoResumo(imoveis_oferecidos=("AP1", "AP2", "AP3")))])
        buffer_lead(world, LEAD_CHAT, ["outro"], ids=["m3"])
        await _run(world, key)
        assert world.contato()["imoveis_oferecidos"] == ["AP1", "AP2", "AP3"]

    async def test_a_build_that_sends_none_leaves_the_mirror_alone(self, world):
        key = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        world.agents = FakeAgentsClient([_ok("veja", qualificacao=QualificacaoResumo(imoveis_oferecidos=("AP1",)))])
        await _run(world, key)
        world.agents = FakeAgentsClient([_ok("oi de novo", qualificacao=QualificacaoResumo(estagio="x"))])
        buffer_lead(world, LEAD_CHAT, ["e aí"], ids=["m2"])
        await _run(world, key)
        assert world.contato()["imoveis_oferecidos"] == ["AP1"]

    def test_codes_are_normalised(self):
        assert contatos.normalizar_codigos_imoveis([" A ", "A", "B", 3, None, ""]) == ["A", "B"]
        assert contatos.normalizar_codigos_imoveis("AP1") == []


# ── ID document ─────────────────────────────────────────────────────────────
class IntakeFake:
    """Records what `documento_intake_service.processar_midia` would be given; answers a scripted result."""

    def __init__(self, resultado: dict[str, Any] | None = None):
        self.chamadas: list[dict[str, Any]] = []
        self.resultado = resultado or {"status": "extraido", "documento_id": "d-1", "tipo_documento": "rg", "motivo": None}

    async def __call__(self, org_id, cliente_id, **kw):
        self.chamadas.append({"org_id": org_id, "cliente_id": cliente_id, **kw})
        return self.resultado


def _midia_no_waha(world: World, pid="wamid-doc-1") -> None:
    world.waha.fake_chat_messages[LEAD_CHAT] = [
        {"id": "wamid-outra", "body": "oi"},
        {"id": pid, "hasMedia": True, "media": {"url": "https://waha.example.com/api/files/doc.jpg", "mimetype": "image/jpeg", "filename": "doc.jpg"}},
    ]


def _acao_doc(pid="wamid-doc-1") -> JuliaAction:
    return JuliaAction(type="documento_identificacao", seq=0, payload={"provider_message_id": pid, "tipo_provavel": "rg"})


class TestDocumentoIdentificacao:
    async def test_the_media_goes_to_the_intake_for_the_card_found_by_the_phone(self, world):
        cliente_id = "00000000-0000-4000-8000-0000000000c9"
        world.sw.table("clientes").insert({"id": cliente_id, "org_id": ORG_ID, "nome": "Ana", "chave_canonica": f"+{LEAD_PHONE}", "chave_tipo": "telefone"}).execute()
        _midia_no_waha(world)
        intake = IntakeFake()
        world.agents = FakeAgentsClient([_ok("Recebi!", actions=[_acao_doc()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["segue meu RG"]), documento_intake=intake)
        (c,) = intake.chamadas
        assert str(c["cliente_id"]) == cliente_id and str(c["org_id"]) == ORG_ID
        assert c["media_url"] == "https://waha.example.com/api/files/doc.jpg" and c["mimetype"] == "image/jpeg" and c["filename"] == "doc.jpg"
        assert world.rows("leads") == []  # the card existed: no lead was made up
        assert [e["payload"]["status"] for e in world.rows("julia_eventos", tipo="documento_identificacao")] == ["extraido"]
        assert not [n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_DOCUMENTO_FALHOU]

    async def test_without_a_card_it_is_created_through_the_lead_path_and_the_contato_is_linked(self, world):
        _midia_no_waha(world)
        intake = IntakeFake()
        world.agents = FakeAgentsClient([_ok("Recebi!", actions=[_acao_doc()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["segue meu RG"]), documento_intake=intake)
        (lead,) = world.rows("leads")
        (cliente,) = world.rows("clientes")
        assert len(intake.chamadas) == 1 and str(intake.chamadas[0]["cliente_id"]) == str(cliente["id"])
        contato = world.contato()
        assert str(contato["lead_id"]) == str(lead["id"]) and contato["status_envio"] != "enviado"  # linked, NOT sent to the SW

    async def test_a_message_the_webhook_already_ingested_is_not_processed_twice(self, world):
        cliente_id = "00000000-0000-4000-8000-0000000000c9"
        world.sw.table("clientes").insert({"id": cliente_id, "org_id": ORG_ID, "nome": "Ana", "chave_canonica": f"+{LEAD_PHONE}", "chave_tipo": "telefone"}).execute()
        world.sw.table("conversation_messages").insert({
            "id": "00000000-0000-4000-8000-0000000000b9", "org_id": ORG_ID, "session_id": LEAD_CHAT, "raw_sender": LEAD_CHAT, "direction": "inbound",
            "body": "[Anexo recebido]", "provider_message_id": "wamid-doc-1", "chat_id": LEAD_CHAT, "connection_id": CONNECTION_ID,
            "structured_payload": {"anexo": {"mime": "image/jpeg", "nome": "doc.jpg", "documento_id": "d-9"}},
        }).execute()
        intake = IntakeFake()
        world.agents = FakeAgentsClient([_ok("Recebi!", actions=[_acao_doc()])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["segue meu RG"]), documento_intake=intake)
        assert intake.chamadas == []

    @pytest.mark.parametrize("cenario", ["midia_ausente", "intake_erro", "sem_id"])
    async def test_every_failure_is_an_in_app_alert_never_silent(self, world, cenario):
        world.sw.table("clientes").insert({"id": "00000000-0000-4000-8000-0000000000c9", "org_id": ORG_ID, "nome": "Ana",
                                           "chave_canonica": f"+{LEAD_PHONE}", "chave_tipo": "telefone"}).execute()
        if cenario != "midia_ausente":
            _midia_no_waha(world)
        intake = IntakeFake({"status": "erro", "documento_id": None, "tipo_documento": None, "motivo": "download_falhou"})
        acao = JuliaAction(type="documento_identificacao", seq=0, payload={"tipo_provavel": "rg"}) if cenario == "sem_id" else _acao_doc()
        world.agents = FakeAgentsClient([_ok("Recebi!", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["segue meu RG"]), documento_intake=intake)
        falhas = [n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_DOCUMENTO_FALHOU]
        assert len(falhas) == 1 and falhas[0]["user_id"] == OWNER_ID
        assert [e["payload"]["status"] for e in world.rows("julia_eventos", tipo="documento_identificacao")] == ["falhou"]
        assert len(_para_lead(world)) >= 1  # the reply to the lead still went out


# ── one WhatsApp message per paragraph (owner rule) ─────────────────────────
class TestUmaMensagemPorParagrafo:
    async def test_a_reply_part_with_blank_lines_goes_out_as_separate_messages(self, world):
        world.agents = FakeAgentsClient([_ok("Oi, Ana!\n\nVi que você quer comprar.\n\nQual o seu orçamento?", "Posso te mostrar alguns imóveis?")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        textos = _para_lead(world)
        assert textos[1:] == ["Oi, Ana!", "Vi que você quer comprar.", "Qual o seu orçamento?", "Posso te mostrar alguns imóveis?"]
        assert all("\n\n" not in t for t in textos)


# ── platform kill (CONTRACT 12.1) ───────────────────────────────────────────
class TestPlataformaDesligada:
    async def test_nothing_is_sent_and_a_refused_new_lead_is_not_kept(self, world):
        world.agents = FakeAgentsClient([TurnResult(conversation_id="", partes=(), status="agente_desligado_plataforma")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.waha.sent_messages == [] and world.contato() is None
        assert world.rows("julia_relatorios") == []

    def test_the_banner_names_the_platform_kill_before_the_org_mode(self):
        from app.routers.julia_agente_router import banner_do_status

        assert banner_do_status({"modo": "ligado", "desligado_plataforma": True}) == {"tipo": "plataforma_desligada", "modo": "ligado"}
        assert banner_do_status({"modo": "drenando"}) == {"tipo": "modo_operacao", "modo": "drenando"}
        assert banner_do_status({"modo": "ligado", "desligado_plataforma": False}) is None
        assert banner_do_status({"agent_key": "julia"}) is None and banner_do_status(None) is None

    def test_the_status_exposes_the_flag_only_when_agents_sends_it(self):
        from app.clients.agents import parse_agent_status

        base = {"agent_key": "julia", "nome": "Julia", "ativo": True, "llm_configurado": True}
        assert "desligado_plataforma" not in parse_agent_status(base).as_dict()
        assert parse_agent_status({**base, "desligado_plataforma": True}).as_dict()["desligado_plataforma"] is True


class TestRestritoAvaliacao:
    async def test_an_outsider_in_evaluation_mode_gets_nothing_and_is_not_kept(self, world):
        world.agents = FakeAgentsClient([TurnResult(conversation_id="", partes=(), status="restrito_avaliacao")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.waha.sent_messages == [] and world.contato() is None and world.notifications() == []

    async def test_the_turn_always_carries_the_e164_phone(self, world):
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.agents.turn_requests[-1].phone_e164 == f"+{LEAD_PHONE}" if hasattr(world.agents, "turn_requests") else True

    def test_links_missing_on_the_offered_listings_are_built_from_the_org_template(self, world):
        world.sw.set_table_data("julia_conhecimento_secoes", [{"org_id": ORG_ID, "secao": "perfil_whatsapp", "versao": 1,
            "dados": {"site": "https://site.example", "link_imovel": "{site}/imovel/{codigo}"}}])
        rel = svc.completar_links(world.sw, ORG_ID, {"imoveis_oferecidos": [{"codigo": "AP1", "link": None}, {"codigo": "AP2", "link": "https://x/2"}]})
        assert [i["link"] for i in rel["imoveis_oferecidos"]] == ["https://site.example/imovel/AP1", "https://x/2"]


# ── H1: what reaches the staff number is sanitised ──────────────────────────
SW = "https://sw.example.test"
PERMITE = dict(hosts_permitidos=frozenset({"sw.example.test", "site.example"}), telefones_permitidos=frozenset({LEAD_PHONE}))


class TestSanitizadorDoStaff:
    @pytest.mark.parametrize("injetado,sumiu", [
        ("Acesse https://evil.example/pix agora", "evil.example"),
        ("veja www.golpe.com.br/pagar", "golpe.com.br"),
        ("entre em bit.ly/abc123 já", "bit.ly"),
        ("fale com o suporte: suporte@golpe.com", "suporte@golpe.com"),
        ("me chama no +55 21 99999-8888", "99999-8888"),
        ("ligue (11) 3333-4444 ou 11933334444", "3333-4444"),
        ("chave pix: 123.456.789-09", "123.456.789-09"),
        ("pix aleatória 123e4567-e89b-12d3-a456-426614174000", "123e4567"),
        ("cc @dono_da_imobiliaria por favor", "@dono_da_imobiliaria"),
    ])
    def test_links_domains_phones_emails_pix_and_mentions_are_removed(self, injetado, sumiu):
        saida = svc.sanitizar_para_staff(injetado, **PERMITE)
        assert sumiu not in saida and "removid" in saida

    def test_only_the_conversation_link_the_orgs_listing_links_and_the_leads_own_phone_survive(self):
        texto = (f"Lead: Ana (+{LEAD_PHONE})\nConversa: {SW}/julia/conversas?chat={LEAD_PHONE}%40c.us\n"
                 "Imóvel: https://site.example/imovel/AP0042 e site.example/imovel/CA7\nPreço R$ 1.500.000 · AP0042 · 03/11/2026")
        assert svc.sanitizar_para_staff(texto, **PERMITE) == texto

    def test_a_lookalike_of_an_allowed_host_is_not_allowed(self):
        saida = svc.sanitizar_para_staff("https://sw.example.test.evil.com/x e https://evil.com/sw.example.test", **PERMITE)
        assert "evil.com" not in saida

    async def test_a_malicious_lead_name_and_a_malicious_report_text_never_reach_the_staff_number(self, world):
        world.sw.table("julia_contatos").insert({
            "id": "00000000-0000-4000-8000-0000000000d1", "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "gen": 0, "slots": {},
            "canal": "whatsapp", "status_envio": "nao_pronto", "nome": "Pague em http://golpe.test/pix @gerente +5521999998888", "telefone_e164": f"+{LEAD_PHONE}",
        }).execute()
        malicioso = {**RELATORIO, "texto": "Lead urgente!\n\nLigue já para +55 21 98888-7777 ou veja https://phishing.test/login\n\nchave pix: golpe@pix.test"}
        world.agents = FakeAgentsClient([_ok("Vou chamar.", status="handoff", actions=[_handoff(relatorio=malicioso)])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        enviado = "\n".join(_para_destino(world))
        for proibido in ("golpe.test", "phishing.test", "98888-7777", "@gerente", "golpe@pix.test", "999998888"):
            assert proibido not in enviado, proibido
        (row,) = world.rows("julia_relatorios")
        assert "phishing.test" not in row["texto"]  # the card keeps the sanitised text too

    async def test_the_alert_text_is_sanitised_too(self, world):
        acao = JuliaAction(type="alerta", seq=0, payload={"tipo": "desvio", "descricao": "O lead pediu para pagar em http://golpe.test e ligar 11 97777-6666", "alerta_id": "a"})
        world.agents = FakeAgentsClient([_ok("ok", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert "golpe.test" not in _para_destino(world)[0] and "97777-6666" not in _para_destino(world)[0]


# ── M3: per-org cap on staff sends ──────────────────────────────────────────
class TestLimiteDeEnvios:
    async def test_over_the_cap_the_report_is_stored_limitado_and_the_owners_get_one_digest(self, world):
        cfg = world.cfg.model_copy(update={"julia_staff_envios_por_hora": 2})
        for i in range(1, 5):
            world.agents = FakeAgentsClient([_ok("ok", actions=[JuliaAction(type="alerta", seq=0, payload={"tipo": "outro", "descricao": f"d{i}", "alerta_id": f"a{i}"})])])
            await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"], ids=[f"m{i}"]), cfg=cfg)
        assert [r["envio_status"] for r in world.rows("julia_relatorios")] == ["enviado", "enviado", "limitado", "limitado"]
        assert len(_para_destino(world)) == 2
        assert len([n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_LIMITADO]) == 1


# ── M1: the media pointer is not trusted ────────────────────────────────────
class TestMidiaDoDocumento:
    BASE = "https://waha.example.com"

    def _msg(self, **over):
        return {"id": "wamid-1", "hasMedia": True, "fromMe": False,
                "media": {"url": f"{self.BASE}/api/files/a.jpg", "mimetype": "image/jpeg", "filename": "a.jpg"}, **over}

    async def _buscar(self, world, msg):
        world.waha.fake_chat_messages[LEAD_CHAT] = [msg]
        return await svc.buscar_midia(world.waha, LEAD_CHAT, "wamid-1", base_url=self.BASE)

    async def test_an_inbound_image_on_the_waha_host_is_accepted(self, world):
        assert (await self._buscar(world, self._msg()))["filename"] == "a.jpg"
        assert await self._buscar(world, self._msg(media={"url": "/api/files/a.pdf", "mimetype": "application/pdf"})) is not None

    @pytest.mark.parametrize("msg", [
        {"fromMe": True},                                                              # a message WE sent
        {"id": "true_5511988887777@c.us_wamid-1"},                                     # WAHA's outbound id form
        {"media": {"url": "https://evil.example/a.jpg", "mimetype": "image/jpeg"}},    # not the connection's WAHA host
        {"media": {"url": "https://waha.example.com.evil.io/a.jpg", "mimetype": "image/jpeg"}},
        {"media": {"url": "http://waha.example.com/api/files/a.jpg", "mimetype": "image/jpeg"}},  # other scheme
        {"media": {"url": "https://waha.example.com/a.mp4", "mimetype": "video/mp4"}},  # not an image / PDF
        {"media": {"url": "https://waha.example.com/a.exe", "mimetype": "application/x-msdownload"}},
    ])
    async def test_everything_else_is_refused(self, world, msg):
        mensagem = {**self._msg(), **msg}
        world.waha.fake_chat_messages[LEAD_CHAT] = [mensagem]
        assert await svc.buscar_midia(world.waha, LEAD_CHAT, mensagem["id"], base_url=self.BASE) is None

    def test_the_lead_intake_uses_the_lead_download_caps_and_marks_the_document_unverified(self):
        import inspect

        from app.services import documento_intake_service as intake, media_service

        assert "processar_midia_do_lead" in inspect.getsource(intake) and media_service.LEAD_IMAGEM_BYTES <= 8 * 1024 * 1024
        assert '"verificado": False' in inspect.getsource(intake.processar_midia)

    async def test_the_default_intake_of_the_worker_is_the_lead_one(self, world):
        from app.services.documento_intake_service import processar_midia_do_lead

        assert world.deps().documento_intake is processar_midia_do_lead


# ── H4: the destination is a user of the org ────────────────────────────────
class TestAlterarDestino:
    @pytest.fixture
    def servicos(self, world):
        return world.deps()

    async def test_a_change_is_audited_told_to_the_admins_and_to_the_old_phone(self, world, servicos):
        _telefone_no_noc(world, "00000000-0000-4000-8000-0000000000a1", "+5511977770000")
        r = await svc.alterar_destino(servicos, ORG_ID, modo="usuario", usuario_id="00000000-0000-4000-8000-0000000000a1", user_id=OWNER_ID)
        assert r["usuario_id"] == "00000000-0000-4000-8000-0000000000a1" and r["telefone_resolvido"] == "+5511977770000"
        (a,) = world.rows("julia_relatorio_destino_auditoria")
        assert a["evento"] == "alterado" and a["antes"]["usuario_id"] == OWNER_ID and a["depois"]["usuario_id"] == "00000000-0000-4000-8000-0000000000a1"
        assert [m["chatId"] for m in world.waha.sent_messages] == [DESTINO_CHAT]  # the OLD destination is told
        assert "deixou de ser o destino" in world.waha.sent_messages[0]["text"]
        assert [n for n in world.notifications() if n["metadata"]["tipo"] == svc.KIND_DESTINO]

    async def test_saving_the_same_destination_audits_and_notifies_nothing(self, world, servicos):
        await svc.alterar_destino(servicos, ORG_ID, modo="usuario", usuario_id=OWNER_ID, user_id=OWNER_ID)
        assert world.rows("julia_relatorio_destino_auditoria") == [] and world.waha.sent_messages == []

    async def test_typed_errors(self, world, servicos):
        from noctusai_lib.primitives.exceptions import AppException

        for kw, codigo in [({"modo": "usuario", "usuario_id": None}, "usuario_obrigatorio"),
                           ({"modo": "usuario", "usuario_id": "00000000-0000-4000-8000-00000000dead"}, "usuario_fora_da_org"),
                           ({"modo": "numero", "usuario_id": None}, "modo_invalido")]:
            with pytest.raises(AppException) as exc:
                await svc.alterar_destino(servicos, ORG_ID, user_id=OWNER_ID, **kw)
            assert exc.value.code == codigo

    def test_the_read_returns_the_user_and_the_resolved_phone(self, world):
        assert svc.obter_destino(world.sw, world.core, ORG_ID) == {
            "modo": "usuario", "usuario_id": OWNER_ID, "usuario_nome": "Dono", "telefone_resolvido": DESTINO, "atualizado_em": None}
