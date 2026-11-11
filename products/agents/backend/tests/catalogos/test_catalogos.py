"""The catalogue seam (migration 081): the Protocol's adapters share ONE contract, the factory refuses what it does not
know, and the social-wiring adapter speaks SW's tool vocabulary through a stubbed client (nothing of ours patched)."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.catalogos import (
    CATALOGOS,
    CatalogoDesconhecido,
    CatalogoIndisponivel,
    CatalogoOpcoes,
    FixtureCatalogo,
    ImoveisSwCatalogo,
    catalogo_para,
)
from app.catalogos.fixture import OPCOES_PADRAO
from app.clients.social_wiring import FakeSocialWiringClient

ORG = uuid4()
SW_ITENS = [
    {"codigo": "A1", "titulo": "Apto A1", "tipo": "apartamento", "bairro": "Pinheiros", "preco": 500000, "quartos": 2,
     "link": "https://x.example/a1"},
    {"codigo": "B2", "titulo": "Casa B2", "tipo": "casa", "bairro": "Moema", "preco": 900000, "quartos": 3},
]


def _sw(**respostas) -> FakeSocialWiringClient:
    sw = FakeSocialWiringClient()
    sw.julia_token_orgs.add(ORG)
    sw.julia_responses.update(respostas)
    return sw


def _run(coro):
    return asyncio.run(coro)


def _catalogos():
    return [FixtureCatalogo(), ImoveisSwCatalogo(_sw(
        buscar_imoveis={"data": SW_ITENS}, imovel_campanha={"data": SW_ITENS[:1]},
        detalhes_imovel={"data": SW_ITENS[0]}))]


@pytest.mark.parametrize("catalogo", _catalogos(), ids=lambda c: c.chave)
class TestEveryAdapterHonoursTheProtocol:
    def test_it_is_a_catalogo_opcoes(self, catalogo):
        assert isinstance(catalogo, CatalogoOpcoes) and catalogo.chave in CATALOGOS

    def test_buscar_answers_items_with_a_code(self, catalogo):
        busca = _run(catalogo.buscar(ORG, perfil={}, excluir=[], limite=2))
        assert busca.itens and all(str(i["codigo"]).strip() for i in busca.itens)

    def test_detalhar_an_existing_option(self, catalogo):
        item = _run(catalogo.detalhar(ORG, SW_ITENS[0]["codigo"] if catalogo.chave == "imoveis_sw" else "opcao-a"))
        assert item is not None and item.get("encontrado") is not False and item["codigo"]

    def test_opcao_is_the_generic_shape(self, catalogo):
        item = _run(catalogo.buscar(ORG, perfil={}, excluir=[], limite=1)).itens[0]
        o = catalogo.opcao(item)
        assert set(o) <= {"codigo", "titulo", "resumo", "link", "atributos"} and o["codigo"] == item["codigo"]
        assert isinstance(o["atributos"], dict) and "codigo" not in o["atributos"]

    def test_perfil_texto_is_stable_and_skips_empty_values(self, catalogo):
        assert catalogo.perfil_texto({"operacao": "compra", "regioes": [], "tipo_imovel": None}) == "operacao=compra"


class TestFixtureCatalogo:
    def test_a_template_with_no_business_serves_options_a_b_c(self):
        busca = _run(FixtureCatalogo().buscar(ORG, perfil={}, excluir=[], limite=5))
        assert [i["titulo"] for i in busca.itens] == ["Opção A", "Opção B", "Opção C"]
        assert [i["codigo"] for i in OPCOES_PADRAO] == ["opcao-a", "opcao-b", "opcao-c"]

    def test_it_serves_the_synthetic_catalogue_it_was_given_and_filters_like_the_eval_world(self):
        cat = FixtureCatalogo(SW_ITENS)
        busca = _run(cat.buscar(ORG, perfil={"operacao": "compra", "faixa_preco": {"max": 600000}}, excluir=[], limite=5))
        assert [i["codigo"] for i in busca.itens] == ["A1"]

    def test_the_search_skips_what_was_already_offered_and_honours_the_limit(self):
        cat = FixtureCatalogo()
        busca = _run(cat.buscar(ORG, perfil={}, excluir=["opcao-a"], limite=1))
        assert [i["codigo"] for i in busca.itens] == ["opcao-b"] and busca.meta["restantes_estimados"] == 1

    def test_unknown_detail_says_not_found(self):
        assert _run(FixtureCatalogo().detalhar(ORG, "nada")) == {"encontrado": False}

    def test_unavailable_is_none_never_a_raise(self):
        cat = FixtureCatalogo(falhar=True)
        assert _run(cat.buscar(ORG, perfil={}, excluir=[], limite=1)) is None
        assert _run(cat.detalhar(ORG, "opcao-a")) is None
        assert _run(cat.buscar_origem(ORG, "opcao-a")) is None


class TestImoveisSwCatalogo:
    def test_buscar_sends_the_mapped_search_arguments_and_forwards_only_the_allowlisted_meta(self):
        sw = _sw(buscar_imoveis={"data": SW_ITENS, "relaxado": ["bairro"], "restantes_estimados": 4, "segredo": "x"})
        cat = ImoveisSwCatalogo(sw)
        busca = _run(cat.buscar(
            ORG, perfil={"operacao": "compra", "regioes": "Pinheiros"}, excluir=["Z9"], limite=2, similar_a="ONE1",
            interacao_id="iid"))
        (_o, nome, args), = sw.julia_calls
        assert nome == "buscar_imoveis"
        assert args == {"operacao": "compra", "bairros": ["Pinheiros"], "similar_a": "ONE1", "excluir_codigos": ["Z9"],
                        "limite": 2, "interacao_id": "iid"}
        assert dict(busca.meta) == {"relaxado": ["bairro"], "restantes_estimados": 4}

    def test_an_item_without_a_code_is_dropped(self):
        cat = ImoveisSwCatalogo(_sw(buscar_imoveis={"data": [{"titulo": "sem codigo"}, SW_ITENS[0]]}))
        assert [i["codigo"] for i in _run(cat.buscar(ORG, perfil={}, excluir=[], limite=5)).itens] == ["A1"]

    @pytest.mark.parametrize("resposta", [{"erro": "indisponivel"}, "lixo"])
    def test_an_unavailable_catalogue_is_none(self, resposta):
        cat = ImoveisSwCatalogo(_sw(buscar_imoveis=resposta, detalhes_imovel=resposta, imovel_campanha=resposta))
        assert _run(cat.buscar(ORG, perfil={}, excluir=[], limite=1)) is None
        assert _run(cat.detalhar(ORG, "A1")) is None
        assert _run(cat.buscar_origem(ORG, "A1")) is None

    def test_a_client_that_raises_is_none(self):
        class Quebrado:
            async def julia_ferramenta(self, *a, **k):
                raise RuntimeError("boom")

        assert _run(ImoveisSwCatalogo(Quebrado()).buscar(ORG, perfil={}, excluir=[], limite=1)) is None

    def test_buscar_origem_uses_the_campaign_tool_and_origem_reads_the_state(self):
        sw = _sw(imovel_campanha={"data": SW_ITENS[:1]})
        cat = ImoveisSwCatalogo(sw)
        assert [i["codigo"] for i in _run(cat.buscar_origem(ORG, "A1")).itens] == ["A1"]
        assert sw.julia_calls[0][1:] == ("imovel_campanha", {"codigo": "A1"})

        class Estado:  # the shape of ``contexto.estado``
            class origem:
                codigo_imovel_campanha = "A1"

        assert cat.origem(Estado) == "A1" and cat.origem(None) is None

    def test_detalhar_unwraps_data(self):
        cat = ImoveisSwCatalogo(_sw(detalhes_imovel={"data": SW_ITENS[0]}))
        assert _run(cat.detalhar(ORG, "A1"))["titulo"] == "Apto A1"


class TestFactory:
    def test_an_unknown_key_refuses_loudly_with_no_fallback(self):
        with pytest.raises(CatalogoDesconhecido, match="inventado"):
            catalogo_para("inventado")
        with pytest.raises(CatalogoDesconhecido):
            catalogo_para(None)

    def test_the_real_estate_catalogue_needs_the_client(self):
        with pytest.raises(CatalogoIndisponivel):
            catalogo_para("imoveis_sw")

    def test_every_known_key_builds(self):
        assert isinstance(catalogo_para("imoveis_sw", sw=_sw()), ImoveisSwCatalogo)
        assert isinstance(catalogo_para("fixture"), FixtureCatalogo)
        assert {catalogo_para(k, sw=_sw()).chave for k in CATALOGOS} == set(CATALOGOS)
