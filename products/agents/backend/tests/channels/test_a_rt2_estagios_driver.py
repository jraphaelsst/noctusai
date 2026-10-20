"""Julia v2 A-RT2: ordered stages for consumers, and the live EvalTurnDriver over the real turn path."""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.dependencies import SCOPE_CHANNEL_STATUS, SCOPE_CHANNEL_TURN
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.eval_driver import EvalTurnDriver, ThreadState, configure_eval_turn_driver, get_eval_turn_driver
from app.studio.eval_driver_live import FixtureSwClient, LiveEvalTurnDriver, make_live_eval_driver_factory
from tests.channels.conftest import ORG_KEY, contexto_body, turn_body
from tests.channels.test_julia_v2_e2e import call, say, step

URL = "/api/channels/agents/julia/qualificacao/estagios"


class TestEstagiosEndpoint:
    def test_requires_a_token(self, chan):
        chan.seed_agent()
        assert chan.request("GET", URL).status_code == 401

    def test_turn_scope_alone_is_403(self, chan):
        chan.seed_agent()
        with chan.as_token(SCOPE_CHANNEL_TURN):
            r = chan.request("GET", URL)
        assert r.status_code == 403 and r.json()["code"] == "scope_missing"

    def test_a_token_of_another_agent_is_403(self, chan):
        from uuid import uuid4

        chan.seed_agent()
        with chan.as_token(SCOPE_CHANNEL_STATUS, principal=uuid4()):
            r = chan.request("GET", URL)
        assert r.status_code == 403 and r.json()["code"] == "agent_not_allowed"

    def test_returns_the_ordered_stages_and_nothing_else(self, chan):
        chan.seed_agent()
        with chan.as_token(SCOPE_CHANNEL_STATUS):
            r = chan.request("GET", URL)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body, "the published standard has stages"
        assert all(set(s) == {"chave", "rotulo", "ordem", "conclusivo"} for s in body)
        assert [s["ordem"] for s in body] == sorted(s["ordem"] for s in body)
        por_chave = {s["chave"]: s for s in body}
        assert por_chave["pronto_para_corretor"]["conclusivo"] is True and por_chave["novo"]["conclusivo"] is False
        assert {s["chave"] for s in body} >= {"novo", "qualificado", "pronto_para_corretor"}

    def test_no_published_version_is_409(self, chan):
        chan.seed_agent(publish=False)
        with chan.as_token(SCOPE_CHANNEL_STATUS):
            r = chan.request("GET", URL)
        assert r.status_code == 409 and r.json()["code"] == "no_active_version"

    def test_the_turn_carries_the_stage_keys_in_order(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi! Você quer comprar ou alugar?")]))
        body = chan.turn(turn_body("Oi", contexto=contexto_body())).json()
        ordem = body["qualificacao"]["estagios_ordem"]
        with chan.as_token(SCOPE_CHANNEL_STATUS):
            lista = chan.request("GET", URL).json()
        assert ordem == [s["chave"] for s in lista] and ordem.index("novo") < ordem.index("pronto_para_corretor")


def _roteiro_catalogo():
    return tuple(
        {"codigo": c, "tipo": "apartamento", "bairro": "Pinheiros", "preco": 700000 + i, "operacao": "compra",
         "link": f"https://imob.exemplo/{c}"}
        for i, c in enumerate(("B1", "B2", "B3", "B4"))
    )


def _driver(chan, provider):
    return LiveEvalTurnDriver(
        studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes,
        key_resolver=lambda provider_name, org: ORG_KEY, provider_impl=provider)


PERFIL = [
    {"criterio": "operacao", "valor": "compra", "trecho": "quero comprar"},
    {"criterio": "interesse_campanha", "valor": "esse_e_similares", "trecho": "parecidos"},
    {"criterio": "tipo_imovel", "valor": "apartamento", "trecho": "apartamento"},
    {"criterio": "regioes", "valor": ["Pinheiros"], "trecho": "Pinheiros"},
    {"criterio": "faixa_preco", "valor": {"max": 800000}, "trecho": "800 mil"},
    {"criterio": "prazo_decisao", "valor": "ate_3m", "trecho": "3 meses"},
    {"criterio": "forma_pagamento", "valor": "financiamento", "trecho": "financiado"},
]
MSG = "quero comprar um apartamento em Pinheiros até 800 mil em 3 meses, financiado, aceito parecidos"


class TestLiveDriver:
    def test_tipo_is_live_only_without_a_provider_seam(self, chan):
        chan.seed_agent(publish=False)
        assert _driver(chan, FakeProvider(tool_responses=[])).tipo == "fake"
        live = LiveEvalTurnDriver(studio_store=chan.rt.studio, catalog=None, padroes=chan.padroes)
        assert live.tipo == "live" and isinstance(live, EvalTurnDriver)

    def test_a_turn_fills_the_estado_and_the_offer_batches_from_the_fixture_catalogue(self, chan):
        chan.seed_agent(publish=False)  # the driver evaluates the DRAFT of the platform definition
        provider = FakeProvider(tool_responses=[
            step(call("registrar_perfil", itens=PERFIL)),
            step(call("oferecer_imoveis", modo="similares")),
            say("Separei 3 opções: https://imob.exemplo/B1 https://imob.exemplo/B2 https://imob.exemplo/B3. Qual curtiu?"),
        ])
        driver = _driver(chan, provider)

        out = asyncio.run(driver.executar_turno(ThreadState(catalogo=_roteiro_catalogo()), MSG))

        assert [t.nome for t in out.ferramentas] == ["registrar_perfil", "oferecer_imoveis"]
        assert all(t.ok for t in out.ferramentas)
        assert out.ferramentas[1].args == {"modo": "similares"}
        assert out.estado.lotes == (("B1", "B2", "B3"),)
        assert out.estado.estagio == "qualificado" and out.estado.criterios["operacao"] == "compra"
        assert out.bolhas and out.handoff is None and out.violacoes == ()
        assert out.custo_usd and out.custo_usd > 0
        # the SW the tools talked to is the fixture one: nothing reached a real tenant
        assert [n for n, _a in driver._mundo.sw.chamadas] == ["buscar_imoveis"]

    def test_the_world_is_rebuilt_per_execution_and_never_touches_the_shared_stores(self, chan):
        chan.seed_agent(publish=False)
        provider = FakeProvider(tool_responses=[
            step(call("registrar_perfil", itens=PERFIL)), step(call("oferecer_imoveis", modo="similares")),
            say("Aqui: https://imob.exemplo/B1 https://imob.exemplo/B2 https://imob.exemplo/B3. Curtiu algum?"),
            say("Oi! Você quer comprar ou alugar?"),
        ])
        driver = _driver(chan, provider)
        th = ThreadState(catalogo=_roteiro_catalogo())
        asyncio.run(driver.executar_turno(th, MSG))
        first = driver._mundo
        driver.nova_execucao()
        out = asyncio.run(driver.executar_turno(th, "oi"))
        assert driver._mundo is not first and out.estado.lotes == ()
        # not one lead / thread / message landed in the product's own (shared) stores
        assert chan.rt.stores.messages.list(chan.org_id, __import__("uuid").UUID(int=0), limite=1) == []
        assert chan.threads.get_lead_ref_by_externa(chan.org_id, first.lead_externo) is None

    def test_a_draftless_agent_is_refused_with_a_typed_error(self, chan):
        chan.seed_agent()  # published, no draft left
        from app.channels.turno import TurnoRecusado

        driver = _driver(chan, FakeProvider(tool_responses=[]))
        with pytest.raises(TurnoRecusado) as exc:
            asyncio.run(driver.executar_turno(ThreadState(), "oi"))
        assert exc.value.codigo == "no_draft"

    def test_the_factory_registers_through_the_eval_seam(self, chan):
        chan.seed_agent(publish=False)
        configure_eval_turn_driver(make_live_eval_driver_factory(
            studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes))
        try:
            driver = get_eval_turn_driver()
            assert isinstance(driver, LiveEvalTurnDriver) and driver.tipo == "live"
        finally:
            configure_eval_turn_driver(None)


class TestFixtureSw:
    def test_search_filters_pages_and_excludes(self):
        sw = FixtureSwClient(_roteiro_catalogo())
        r = asyncio.run(sw.julia_ferramenta(None, "buscar_imoveis", {
            "operacao": "compra", "preco_max": 700002, "excluir_codigos": ["B1"], "limite": 5}))
        assert [i["codigo"] for i in r["data"]] == ["B2", "B3"] and r["restantes_estimados"] == 0
        assert asyncio.run(sw.julia_ferramenta(None, "detalhes_imovel", {"codigo": "ZZ"})) == {"erro": "nao_encontrado"}


class TestLiveDriverRealConformance:
    """The suite runs under the rules + limits configured for the definition's row, not code defaults."""

    def _driver_com_regras(self, chan, real, provider):
        d = _driver(chan, provider)
        d._conformidade = real
        return d

    def test_rules_and_limits_are_copied_from_the_real_store(self, chan):
        from app.stores.conformidade import FakeConformidadeStore

        chan.seed_agent(publish=False)
        definicao = chan.rt.studio.get_platform_definition("julia")
        real = FakeConformidadeStore()
        real.definir_regra(definicao.org_id, definicao.id, "termina_sem_pergunta", ativo=False)
        real.definir_regra(definicao.org_id, definicao.id, "vazamento_prompt", politica="registrar",
                           parametros={"shingle_tokens": 30})
        real.definir_limites(definicao.org_id, definicao.id, max_turnos_janela=1)
        driver = self._driver_com_regras(chan, real, FakeProvider(tool_responses=[say("Oi! Você quer comprar ou alugar?")]))

        asyncio.run(driver.executar_turno(ThreadState(), "oi"))

        cf = driver._mundo.svc.conformidade
        regras = cf.regras(definicao.org_id, definicao.id)
        assert regras["termina_sem_pergunta"].ativo is False
        assert regras["vazamento_prompt"].politica == "registrar" and regras["vazamento_prompt"].parametros == {"shingle_tokens": 30}
        assert cf.limites(definicao.org_id, definicao.id).max_turnos_janela == 1

    def test_the_real_limit_is_enforced_by_the_real_turn_path(self, chan):
        from app.stores.conformidade import FakeConformidadeStore

        chan.seed_agent(publish=False)
        definicao = chan.rt.studio.get_platform_definition("julia")
        real = FakeConformidadeStore()
        real.definir_limites(definicao.org_id, definicao.id, max_turnos_janela=1)
        driver = self._driver_com_regras(chan, real, FakeProvider(tool_responses=[
            say("Oi! Você quer comprar ou alugar?"), say("Entendi! E o bairro?")]))
        primeiro = asyncio.run(driver.executar_turno(ThreadState(), "oi"))
        segundo = asyncio.run(driver.executar_turno(ThreadState(), "quero comprar"))
        assert primeiro.violacoes == () and primeiro.bolhas
        assert [v.regra for v in segundo.violacoes] == ["limite_atingido"] and segundo.bolhas == ()

    def test_without_a_real_store_the_code_defaults_apply(self, chan):
        chan.seed_agent(publish=False)
        driver = _driver(chan, FakeProvider(tool_responses=[say("Oi! Você quer comprar ou alugar?")]))
        asyncio.run(driver.executar_turno(ThreadState(), "oi"))
        definicao = chan.rt.studio.get_platform_definition("julia")
        regras = driver._mundo.svc.conformidade.regras(definicao.org_id, definicao.id)
        assert regras["vazamento_prompt"].politica == "bloquear"
