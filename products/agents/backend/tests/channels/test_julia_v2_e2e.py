"""Julia v2 mechanism, end to end, no live model (CONTRACT §10.3): a ``FakeProvider`` scripts tool calls through the
REAL llm runtime, the REAL channel toolset, the REAL qualification engine/service and the Fake stores.

Scenario: campaign interest -> ``registrar_perfil`` (with ``trecho``) -> ``avaliar_lead`` -> offer batch 1 (3) ->
3x ``nao_gostou`` -> batch 2 -> ``gostou`` -> ``registrar_intencao_visita`` -> identity collection (never echoed,
encrypted) -> ``concluir_qualificacao`` -> the hand-off record to the org owner with profile + summary."""
from __future__ import annotations

import json
from itertools import count
from typing import Any
from uuid import UUID

import pytest
from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage, ToolCall

from app.clients.social_wiring import FakeSocialWiringClient
from tests.channels.conftest import contexto_body, turn_body

_ids = count(1)


def call(name: str, **args: Any) -> ToolCall:
    return ToolCall(f"call-{next(_ids)}", name, args)


def step(*calls: ToolCall) -> ChatToolsResponse:
    return ChatToolsResponse(tool_calls=tuple(calls), finish_reason="tool_calls", usage=LLMUsage(10, 5, 0, 0, 0.001))


def say(text: str) -> ChatToolsResponse:
    return ChatToolsResponse(text=text, usage=LLMUsage(10, 5, 0, 0, 0.001))


def imovel(codigo: str) -> dict[str, Any]:
    return {"codigo": codigo, "tipo": "apartamento", "bairro": "Pinheiros", "preco": 750000,
            "link": f"https://imob.exemplo/{codigo}"}


class ScriptedSW(FakeSocialWiringClient):
    """The CRM tools: ``buscar_imoveis`` answers the next scripted batch; everything else is recorded."""

    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        super().__init__()
        self.batches = list(batches)

    async def julia_ferramenta(self, org_id, nome, args):
        self.julia_calls.append((org_id, nome, dict(args)))
        if self.julia_fail:
            return {"erro": "indisponivel"}
        if nome == "buscar_imoveis":
            lote = self.batches.pop(0) if self.batches else []
            return {"data": lote, "restantes_estimados": len(self.batches) * 3}
        if nome == "detalhes_imovel":
            return {"data": imovel(args["codigo"])}
        return {"data": []}


def tool_results(provider: FakeProvider) -> list[dict[str, Any]]:
    """Every tool result the model was shown, once each, in order (each chat call re-sends the earlier ones)."""
    out, seen = [], set()
    for c in provider.calls:
        for m in c["messages"]:
            if m.role == "tool" and m.tool_call_id not in seen:
                seen.add(m.tool_call_id)
                try:
                    out.append(json.loads(m.content))
                except ValueError:
                    out.append({"_raw": m.content})
    return out


MENSAGEM_1 = ("Quero comprar um apartamento em Pinheiros até 800 mil, em até 3 meses, financiado. "
              "Vi o AP0123 e aceito ver parecidos também.")
CPF, RG, EMAIL = "529.982.247-25", "12.345.678-9", "maria@exemplo.com"


@pytest.fixture
def mundo(chan):
    chan.seed_agent(obrigatoria={"registrar_perfil": "qualificar-lead", "oferecer_imoveis": "ofertar-imoveis"})
    chan.sw = ScriptedSW([
        [imovel("B1"), imovel("B2"), imovel("B3")],
        [imovel("B4"), imovel("B5"), imovel("B6")],
    ])
    from app.dependencies import get_julia_tools_client_dep
    from app.main import app

    app.dependency_overrides[get_julia_tools_client_dep] = lambda: chan.sw
    chan.sw.julia_token_orgs.add(chan.org_id)
    return chan


def ctx_campanha():
    return contexto_body(origem={"canal_origem": "meta_ads", "codigo_imovel_campanha": "AP0123"})


class TestTheWholeQualification:
    def test_from_campaign_interest_to_the_hand_off_to_the_owner(self, mundo):
        chan = mundo
        scripted = [
            # ── turn 1: interest -> skills -> profile -> evaluate -> batch 1 ──
            step(call("abrir_skill", nome="qualificar-lead"), call("abrir_skill", nome="ofertar-imoveis")),
            step(call("registrar_perfil", itens=[
                {"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"},
                {"criterio": "interesse_campanha", "valor": "esse_e_similares", "trecho": "aceito ver parecidos"},
                {"criterio": "tipo_imovel", "valor": "apartamento", "trecho": "um apartamento"},
                {"criterio": "regioes", "valor": ["Pinheiros"], "trecho": "em Pinheiros"},
                {"criterio": "faixa_preco", "valor": {"max": 800000}, "trecho": "até 800 mil"},
                {"criterio": "prazo_decisao", "valor": "ate_3m", "trecho": "em até 3 meses"},
                {"criterio": "forma_pagamento", "valor": "financiamento", "trecho": "financiado"},
            ])),
            step(call("avaliar_lead")),
            step(call("oferecer_imoveis", modo="similares")),
            say("Separei 3 opções: https://imob.exemplo/B1 https://imob.exemplo/B2 https://imob.exemplo/B3. Qual curtiu?"),
            # ── turn 2: 3x nao_gostou -> batch 2 ──
            step(call("registrar_reacao_imovel", codigo="B1", reacao="nao_gostou", motivo="caro"),
                 call("registrar_reacao_imovel", codigo="B2", reacao="nao_gostou"),
                 call("registrar_reacao_imovel", codigo="B3", reacao="nao_gostou")),
            step(call("oferecer_imoveis", modo="similares")),
            say("Tenho mais 3: https://imob.exemplo/B4 https://imob.exemplo/B5 https://imob.exemplo/B6. Algum agrada?"),
            # ── turn 3: gostou -> visit intent ──
            step(call("registrar_reacao_imovel", codigo="B5", reacao="gostou"),
                 call("registrar_intencao_visita", codigo="B5", preferencia_horario="sábado de manhã")),
            say("Ótimo! Para registrar a visita, qual seu nome completo, e-mail, CPF e RG?"),
            # ── turn 4: identity -> conclude ──
            step(call("registrar_identificacao", campo="nome", valor="Maria Souza"),
                 call("registrar_identificacao", campo="email", valor=EMAIL),
                 call("registrar_identificacao", campo="cpf", valor=CPF),
                 call("registrar_identificacao", campo="rg", valor=RG)),
            step(call("avaliar_lead")),
            step(call("concluir_qualificacao")),
            say("Perfeito, um corretor continua daqui."),
        ]
        chan.use_provider(FakeProvider(tool_responses=scripted))

        r1 = chan.turn(turn_body(MENSAGEM_1, ids=["m1"], contexto=ctx_campanha())).json()
        assert r1["status"] == "respondido" and r1["conformidade"] == {"violacoes": []}
        assert r1["qualificacao"]["estagio"] == "qualificado"
        ofertados = chan.qual.codigos_oferecidos(chan.org_id, chan.lead_ref().id)
        assert ofertados == ["B1", "B2", "B3"]
        busca = [a for _o, n, a in chan.sw.julia_calls if n == "buscar_imoveis"][0]
        assert busca["limite"] == 3 and busca["similar_a"] == "AP0123" and busca["excluir_codigos"] == []
        assert (busca["operacao"], busca["tipo"], busca["preco_max"], busca["bairros"]) == (
            "compra", "apartamento", 800000, ["Pinheiros"])
        assert "interacao_id" in busca  # attached server-side, never a model argument

        r2 = chan.turn(turn_body("Nenhum me agradou, são caros", ids=["m2"], contexto=ctx_campanha())).json()
        assert r2["status"] == "respondido"
        buscas = [a for _o, n, a in chan.sw.julia_calls if n == "buscar_imoveis"]
        assert buscas[1]["excluir_codigos"] == ["B1", "B2", "B3"]  # never re-offered
        eventos = chan.qual.eventos(chan.org_id, chan.lead_ref().id)
        assert [e.codigo_imovel for e in eventos if e.evento == "nao_gostou"] == ["B1", "B2", "B3"]
        assert {e.lote for e in eventos if e.evento == "oferecido"} == {1, 2}

        r3 = chan.turn(turn_body("Gostei do B5, quero visitar", ids=["m3"], contexto=ctx_campanha())).json()
        assert r3["actions"] == [{"seq": 1, "type": "intencao_visita", "codigo": "B5", "preferencia_horario": "sábado de manhã"}]
        assert r3["participante"]["estado"] == "ativo" and r3["status"] == "respondido"

        msg4 = f"Meu nome é Maria Souza, e-mail {EMAIL}, CPF {CPF}, RG {RG}"
        r4 = chan.turn(turn_body(msg4, ids=["m4"], contexto=ctx_campanha())).json()
        assert r4["status"] == "concluido" and r4["participante"] == {"agent_key": "julia", "estado": "concluido"}
        [lead_pronto] = [a for a in r4["actions"] if a["type"] == "lead_pronto"]
        assert lead_pronto["estagio"] == "pronto_para_corretor" and lead_pronto["imoveis_gostou"] == ["B5"]
        assert lead_pronto["intencoes_visita"] == ["B5"] and lead_pronto["valores"]["operacao"] == "compra"
        assert r4["qualificacao"]["estagio"] == "pronto_para_corretor"

        # the hand-off record to the org owner: profile + summary (+ MASKED identity)
        [nota] = chan.threads.list_handoffs(chan.org_id, UUID(r4["thread_id"]))
        assert (nota.para.tipo, nota.motivo_codigo) == ("papel", "qualificacao_concluida")
        assert nota.perfil["estagio"] == "pronto_para_corretor" and nota.perfil["intencoes_visita"] == ["B5"]
        assert nota.resumo == "txt:ferramenta.handoff.resumo_conclusao".replace(
            "txt:ferramenta.handoff.resumo_conclusao", nota.resumo) and nota.resumo.startswith("txt:ferramenta.handoff.resumo_conclusao")
        assert nota.identificacao_completa is True

        # a concluded thread is the broker's: the next lead message is appended, never answered
        chan.provider._tool_turns.append("nunca")
        r5 = chan.turn(turn_body("Alguma novidade?", ids=["m5"], contexto=ctx_campanha())).json()
        assert r5["status"] == "conversa_com_outro_responsavel" and r5["reply"]["partes"] == []

        # ── identity: never echoed, never in any transcript / dossier / prompt, encrypted at rest ──
        segredos = (CPF, CPF.replace(".", "").replace("-", ""), RG, "123456789", EMAIL, "Maria Souza")
        for res in tool_results(chan.provider):
            if res.get("campo"):
                assert set(res) <= {"ok", "campo", "status", "faltando"}
        rows = chan.rt.stores.messages.list(chan.org_id, UUID(r4["thread_id"]), limite=200)
        for r in rows:
            if r.role == "user":
                continue  # the lead's own words are theirs
            for s in segredos:
                assert s not in (r.texto or "") and s not in json.dumps(r.blocks)
        for c in chan.provider.calls[-4:]:
            sistema = "\n".join(m.content for m in c["messages"] if m.role == "system")
            for s in segredos:
                assert s not in sistema
        for n in chan.threads.list_handoffs(chan.org_id, UUID(r4["thread_id"])):
            blob = json.dumps({"p": n.perfil, "m": n.identificacao_mascarada, "r": n.resumo}, default=str)
            for s in (CPF, "52998224725", RG, EMAIL):
                assert s not in blob
        rec = chan.ident._store.obter(chan.org_id, chan.lead_ref().id)
        assert rec.cpf_cifrado and CPF not in rec.cpf_cifrado and "52998224725" not in rec.cpf_cifrado
        assert chan.ident._cipher.decifrar(rec.cpf_cifrado) == "52998224725"
        assert rec.rg_cifrado and "123456789" not in rec.rg_cifrado

    def test_the_trecho_must_be_the_leads_own_words_a_fabricated_quote_is_refused(self, mundo):
        chan = mundo
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="qualificar-lead")),
            step(call("registrar_perfil", itens=[
                {"criterio": "operacao", "valor": "compra", "trecho": "quero comprar com certeza"}])),
            say("Entendi! Você busca um imóvel para comprar?"),
        ]))
        body = chan.turn(turn_body("Oi, tudo bem?")).json()
        assert body["qualificacao"]["estagio"] == "novo"
        [res] = [r for r in tool_results(chan.provider) if r.get("recusados")]
        assert res["recusados"][0]["codigo"] == "trecho_nao_confere"
        assert res["recusados"][0]["mensagem"] == "txt:ferramenta.resultado.recusa.trecho_nao_confere"
        assert chan.leads.listar_registros(chan.org_id, chan.lead_ref().id) == []
