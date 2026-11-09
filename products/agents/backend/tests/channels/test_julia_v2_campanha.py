"""The ad (campaign) property path: the lead's ad listing is offered at the opening, BEFORE the lead is qualified.

``oferecer_imoveis modo=campanha`` is the one exception to ``pode_ofertar`` (the prompt says so); only the
``similares`` mode needs the qualification minimum. The ad link rides the same channels as every listing link."""
from __future__ import annotations

from typing import Any

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from tests.channels.conftest import contexto_body, turn_body
from tests.channels.test_julia_v2_e2e import ScriptedSW, call, say, step, tool_results

LINK = "https://imobiliariaexemplo.com.br/imovel/ONE8970"


def _anuncio() -> dict[str, Any]:
    return {"codigo": "ONE8970", "tipo": "apartamento", "bairro": "Pinheiros", "preco": 750000, "link": LINK}


class CampanhaSW(ScriptedSW):
    async def julia_ferramenta(self, org_id, nome, args):
        if nome == "imovel_campanha":
            self.julia_calls.append((org_id, nome, dict(args)))
            return {"data": [_anuncio()] if args.get("codigo") == "ONE8970" else []}
        return await super().julia_ferramenta(org_id, nome, args)


def _ctx():
    return contexto_body(origem={"canal_origem": "meta_ads", "codigo_imovel_campanha": "ONE8970"})


@pytest.fixture
def anuncio(chan):
    chan.seed_agent(obrigatoria={"registrar_perfil": "qualificar-lead", "oferecer_imoveis": "ofertar-imoveis"})
    chan.sw = CampanhaSW([])
    from app.dependencies import get_julia_tools_client_dep
    from app.main import app

    app.dependency_overrides[get_julia_tools_client_dep] = lambda: chan.sw
    chan.sw.julia_token_orgs.add(chan.org_id)
    return chan


class TestAdListingAtTheOpening:
    def test_the_ads_property_is_offered_before_the_lead_is_qualified(self, anuncio):
        chan = anuncio
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="ofertar-imoveis")),
            step(call("oferecer_imoveis", modo="campanha")),
            say(f"Oi, sou a Julia! É este o imóvel? {LINK}")]))
        body = chan.turn(turn_body("Oi, vi o anúncio", contexto=_ctx())).json()
        r = tool_results(chan.provider)[-1]
        assert r.get("codigo") != "nao_pode_ofertar", r
        assert r["dados_catalogo"]["imoveis"][0]["link"] == LINK
        assert [(n, a) for _o, n, a in chan.sw.julia_calls if n == "imovel_campanha"] == [("imovel_campanha", {"codigo": "ONE8970"})]
        assert body["status"] == "respondido"
        assert "link_nao_permitido" not in str(body)

    def test_similares_still_needs_the_qualification_minimum(self, anuncio):
        chan = anuncio
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="ofertar-imoveis")),
            step(call("oferecer_imoveis", modo="similares")),
            say("Qual o bairro?")]))
        chan.turn(turn_body("Oi", contexto=_ctx()))
        assert tool_results(chan.provider)[-1]["codigo"] == "nao_pode_ofertar"

    def test_a_second_request_for_the_ads_property_resends_its_link(self, anuncio):
        chan = anuncio
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="ofertar-imoveis")),
            step(call("oferecer_imoveis", modo="campanha")),
            say(f"É este? {LINK}"),
            step(call("oferecer_imoveis", modo="campanha")),
            say(f"Claro, o link de novo: {LINK}")]))
        chan.turn(turn_body("Oi, vi o anúncio", ids=["m1"], contexto=_ctx()))
        body = chan.turn(turn_body("Me manda o link de novo?", ids=["m2"], contexto=_ctx())).json()
        r = tool_results(chan.provider)[-1]
        assert r.get("ok") is True and r["dados_catalogo"]["imoveis"][0]["link"] == LINK
        assert body["status"] == "respondido"
