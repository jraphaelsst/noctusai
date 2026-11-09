"""The eval world can express an ad lead: ``fixture.origem`` makes the thread carry ``estado.origem`` (the campaign code),
for BOTH suites (mecanismo roteiro and the judge's world), validated against the channel contract's own closed model."""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.integrations.llm import FakeProvider
from pydantic import ValidationError

from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.eval_driver import ThreadState
from app.studio.eval_driver_live import LiveEvalTurnDriver, contexto_de_avaliacao
from app.studio.eval_mecanismo import RoteiroInvalido, validar_mundo_juiz, validar_roteiro
from tests.channels.conftest import ORG_KEY
from tests.channels.test_julia_v2_e2e import call, say, step

LINK = "https://imobiliariaexemplo.com.br/imovel/ONE8970"
CATALOGO = ({"codigo": "ONE8970", "tipo": "apartamento", "bairro": "Pinheiros", "preco": 750000, "link": LINK},)


def _driver(chan, provider):
    return LiveEvalTurnDriver(
        studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes,
        agent_key="julia", key_resolver=lambda provider_name, org: ORG_KEY, provider_impl=provider)


class TestDriver:
    def test_the_origin_reaches_the_state_block_and_the_campaign_tool_resolves_the_catalogue(self, chan):
        chan.seed_agent(publish=False)
        provider = FakeProvider(tool_responses=[
            step(call("oferecer_imoveis", modo="campanha")),
            say(f"Oi, sou a Julia! O imóvel do anúncio é este: {LINK} É esse mesmo?")])
        driver = _driver(chan, provider)
        thread = ThreadState(catalogo=CATALOGO, fixture={"origem": {"codigo_imovel_campanha": "ONE8970"}})

        out = asyncio.run(driver.executar_turno(thread, "Oi, vi o anúncio"))

        assert [(t.nome, t.ok) for t in out.ferramentas] == [("oferecer_imoveis", True)]
        assert out.estado.lotes == (("ONE8970",),)
        assert out.violacoes == ()
        assert list(driver._mundo.sw.chamadas) == [("imovel_campanha", {"codigo": "ONE8970"})]
        sistema = "\n".join(str(m.content) for c in provider.calls for m in c["messages"] if m.role == "system")
        assert "ONE8970" in sistema  # the state block shows the campaign code

    def test_without_an_origin_the_world_is_unchanged_and_the_campaign_tool_has_no_code(self, chan):
        chan.seed_agent(publish=False)
        provider = FakeProvider(tool_responses=[step(call("oferecer_imoveis", modo="campanha")), say("Oi! Em que posso ajudar?")])
        driver = _driver(chan, provider)

        out = asyncio.run(driver.executar_turno(ThreadState(catalogo=CATALOGO), "Oi"))

        assert [(t.nome, t.ok) for t in out.ferramentas] == [("oferecer_imoveis", False)]
        assert driver._mundo.contexto is None

    def test_an_invalid_origin_is_refused_by_the_driver_too(self):
        assert contexto_de_avaliacao({}) is None
        ctx = contexto_de_avaliacao({"origem": {"codigo_imovel_campanha": "ONE8970"}})
        assert ctx.estado.origem.codigo_imovel_campanha == "ONE8970"
        with pytest.raises(ValidationError):
            contexto_de_avaliacao({"origem": {"codigo": "ONE8970"}})


class TestRoteiroFixtureOrigem:
    BASE = {"turnos": [{"lead": "Oi, vi o anúncio"}], "catalogo": list(CATALOGO)}

    def test_a_valid_origin_passes_both_suites(self):
        fixture = {"origem": {"canal_origem": "meta_ads", "codigo_imovel_campanha": "ONE8970"}}
        validar_roteiro({**self.BASE, "fixture": fixture})
        validar_mundo_juiz({"catalogo": self.BASE["catalogo"], "fixture": fixture})

    @pytest.mark.parametrize("origem", [
        {"codigo": "ONE8970"},                                   # unknown key (typo)
        {"codigo_imovel_campanha": "ONE8970", "extra": 1},       # unknown key beside a good one
        {"codigo_imovel_campanha": 8970},                        # wrong type
        {"codigo_imovel_campanha": "x" * 65},                    # over the contract's length
        "ONE8970",                                               # not an object
    ])
    def test_a_malformed_origin_is_refused_by_both_suites(self, origem):
        with pytest.raises(RoteiroInvalido):
            validar_roteiro({**self.BASE, "fixture": {"origem": origem}})
        with pytest.raises(RoteiroInvalido):
            validar_mundo_juiz({"fixture": {"origem": origem}})
