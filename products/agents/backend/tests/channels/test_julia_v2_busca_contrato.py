"""``oferecer_imoveis`` against SW's v2 ``buscar_imoveis`` contract (A-polish #8).

* the lead's MUST-haves travel as ``itens_essenciais`` (SW hard filters, never relaxed) -- nice-to-haves stay
  ``caracteristicas``;
* the answer's ``relaxado`` (axes SW widened) and ``similar_a_encontrado`` reach the model next to the listings.
"""
from __future__ import annotations

from app.channels.tool_registry import _consulta_sw
from tests.channels.conftest import turn_body
from tests.channels.test_julia_v2_e2e import (
    MENSAGEM_1,
    ScriptedSW,
    call,
    ctx_campanha,
    imovel,
    say,
    step,
    tool_results,
)
from noctusai_lib.integrations.llm import FakeProvider


def test_must_haves_are_sent_as_itens_essenciais_and_nice_to_haves_as_caracteristicas():
    q = _consulta_sw({
        "operacao": "compra", "itens_essenciais": ["animais", "jardim_quintal"], "caracteristicas": ["piscina"],
    })
    assert q["itens_essenciais"] == ["animais", "jardim_quintal"]
    assert q["caracteristicas"] == ["piscina"]
    assert "itens_essenciais" not in _consulta_sw({"operacao": "compra", "itens_essenciais": []})


class _SwV2(ScriptedSW):
    async def julia_ferramenta(self, org_id, nome, args):
        body = await super().julia_ferramenta(org_id, nome, args)
        if nome == "buscar_imoveis":
            body = {**body, "relaxado": ["regiao_adjacente", "preco"], "similar_a_encontrado": False,
                    "interno_nao_repassar": "x"}
        return body


def test_relaxado_and_similar_a_encontrado_reach_the_model(chan):
    from app.dependencies import get_julia_tools_client_dep
    from app.main import app

    chan.seed_agent()
    chan.sw = _SwV2([[imovel("B1"), imovel("B2"), imovel("B3")]])
    app.dependency_overrides[get_julia_tools_client_dep] = lambda: chan.sw
    chan.sw.julia_token_orgs.add(chan.org_id)
    chan.use_provider(FakeProvider(tool_responses=[
        step(call("registrar_perfil", itens=[
            {"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"},
            {"criterio": "tipo_imovel", "valor": "apartamento", "trecho": "um apartamento"},
            {"criterio": "regioes", "valor": ["Pinheiros"], "trecho": "em Pinheiros"},
            {"criterio": "faixa_preco", "valor": {"max": 800000}, "trecho": "até 800 mil"},
            {"criterio": "interesse_campanha", "valor": "esse_e_similares", "trecho": "aceito ver parecidos"},
            {"criterio": "prazo_decisao", "valor": "ate_3m", "trecho": "em até 3 meses"},
            {"criterio": "forma_pagamento", "valor": "financiamento", "trecho": "financiado"},
        ])),
        step(call("oferecer_imoveis", modo="similares")),
        say("Ampliei a região e o preço: https://imob.exemplo/B1 https://imob.exemplo/B2 https://imob.exemplo/B3. Algum?"),
    ]))
    chan.turn(turn_body(MENSAGEM_1, ids=["m1"], contexto=ctx_campanha()))
    [oferta] = [r for r in tool_results(chan.provider) if "imoveis" in r]
    assert oferta["relaxado"] == ["regiao_adjacente", "preco"] and oferta["similar_a_encontrado"] is False
    assert "interno_nao_repassar" not in oferta  # an explicit allowlist, never the raw SW body
