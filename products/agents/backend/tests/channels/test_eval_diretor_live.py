"""The mechanism-eval world of the Diretor de Criacao (``app`` channel): the live driver runs the criacao turn over a
synthetic tenant (``roteiro.fixture.criacao``), and the criacao asserts hold the reply to the output contract.

Scripted provider (``FakeProvider``) + Fake stores only; every tenant, brand and text here is invented."""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.criacao.saida import MAX_HEADLINE_PALAVRAS
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.eval_driver import ThreadState
from app.studio.eval_driver_live import FixtureSwClient, LiveEvalTurnDriver
from app.studio.eval_mecanismo import AssertInvalido, Traco, avaliar_asserts, validar_asserts
from tests.channels.conftest import ORG_KEY
from tests.channels.diretor_mundo import DIRETOR_KEY, montar_diretor
from tests.channels.test_julia_v2_e2e import call, say, step
from tests.routers.conftest import DEFAULT_USER_ID

URL = "https://fonte.exemplo/estudo"
TENANT = {
    "contexto_marca": {"perfil": {"bio": "Marca de teste", "ctas": "", "nichos": [], "profissoes": []},
                       "brand_kit": None, "memorias": ["Nunca usar CTA comercial."]},
    "estruturas_buscar": {"estruturas": [{"codigo": 101, "formato": "reels", "objetivos": ["alcance"],
                                          "formula_headline": "f", "perfil": "perfil_ficticio", "blocos": []}],
                          "total_candidatas": 1, "ranking": "texto_simples"},
    "pesquisas": {"pesquisas": [{"variavel": "sono", "conteudo": "dado", "url": URL, "plays": None}]},
}

RESPOSTA_OK = f"""### Roteiro 1: Dormir melhor (estrutura #101)
**(Gancho)** Você acorda cansada. Todo dia.

Aí você culpa o café, a cama, o travesseiro, o vizinho que liga o som tarde da noite. Mas olha, não é o café.

### Publicação 1
- Objetivo do post: salvamentos
- CTA: Salva para ler de novo hoje à noite.
- Justificativa do CTA: o objetivo é salvamento, então o pedido é salvar no fim.
- Legenda: Uma rotina simples para a noite.
- Hashtags: #sono #rotina #descanso #noite #bemestar
- Primeiro comentário: Qual parte você testa primeiro?
- Link:
- Fontes: {URL} (verificada)
- Voz: sem amostras
"""


@pytest.fixture
def diretor(chan):
    studio = chan.rt.studio
    montar_diretor(studio, StoreKnowledgeCatalog(chan.rt.knowledge), chan.org_id, DEFAULT_USER_ID, chan.controles)
    d = studio.get_platform_definition(DIRETOR_KEY)
    publicada = next(v for v in studio.list_versions(d.org_id, d.id) if v.status == "ativa")
    studio.create_draft(d.org_id, d.id, publicada.id, DEFAULT_USER_ID)  # the eval runs the DRAFT, as in Studio
    return chan


def _driver(chan, provider):
    return LiveEvalTurnDriver(
        studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes,
        agent_key=DIRETOR_KEY, key_resolver=lambda provider_name, org: ORG_KEY, provider_impl=provider)


def _turno(chan, provider, fixture):
    return asyncio.run(_driver(chan, provider).executar_turno(ThreadState(fixture={"criacao": fixture}), "quero roteiros"))


class TestDriverApp:
    def test_runs_the_criacao_turn_over_the_fixture_tenant(self, diretor):
        provider = FakeProvider(tool_responses=[
            step(call("contexto_marca"), call("estruturas_buscar", formato="reels"), call("pesquisas")), say(RESPOSTA_OK)])
        out = _turno(diretor, provider, TENANT)
        assert out.texto.strip() == RESPOSTA_OK.strip()
        assert [c.nome for c in out.ferramentas] == ["contexto_marca", "estruturas_buscar", "pesquisas"]
        assert all(c.ok for c in out.ferramentas)
        nomes = [n for n, _ in out.resultados_ferramentas]
        assert nomes == ["contexto_marca", "estruturas_buscar", "pesquisas"]
        assert out.resultados_ferramentas[1][1]["estruturas"][0]["codigo"] == 101
        # the lead machinery never ran: no lead state, no hand-off, no qualification tool offered
        assert out.handoff is None and out.estado.estagio is None
        oferecidas = {getattr(t, "name", None) or t.get("function", {}).get("name")
                      for c in provider.calls if c["method"] == "chat_with_tools" for t in (c.get("tools") or [])}
        assert "contexto_marca" in oferecidas and not {"registrar_perfil", "transferir_para_humano"} & oferecidas

    def test_the_whole_mechanism_assert_set_passes_on_a_contract_reply(self, diretor):
        provider = FakeProvider(tool_responses=[
            step(call("contexto_marca"), call("estruturas_buscar", formato="reels"), call("pesquisas")), say(RESPOSTA_OK)])
        out = _turno(diretor, provider, TENANT)
        t = Traco()
        t.absorver(out)
        asserts = {
            "saida_criacao": {"cta_proibidos": ["compre"], "nomes_proibidos": ["perfil_ficticio"]},
            "propostas_criacao": {"tipo": "roteiro", "min": 1, "max": 5},
            "texto_sem_termos": ["perfil_ficticio"],
            "ferramentas_incluem": ["contexto_marca", "estruturas_buscar"],
        }
        validar_asserts(asserts)
        assert avaliar_asserts(asserts, t) == []


class TestFixtureTenant:
    def test_an_unset_tool_answers_its_empty_real_shape(self):
        sw = FixtureSwClient(criacao={})
        voz = asyncio.run(sw.criacao_ferramenta(None, "voz_amostras", {"marca_id": "m"}))
        assert voz == {"amostras": [], "motivo": "sem_transcricoes_da_marca"}
        assert asyncio.run(sw.criacao_ferramenta(None, "contexto_marca", {"marca_id": "m"}))["marca_id"] == "m"

    def test_estrutura_detalhe_reads_the_fixture_library(self):
        sw = FixtureSwClient(criacao=TENANT)
        assert asyncio.run(sw.criacao_ferramenta(None, "estrutura_detalhe", {"codigo": 101}))["codigo"] == 101
        assert asyncio.run(sw.criacao_ferramenta(None, "estrutura_detalhe", {"codigo": 7})) == {"erro": "estrutura_nao_encontrada"}


def _traco(texto, resultados=()):
    t = Traco()
    t.ultimo_texto = texto
    t.resultados_ferramentas = list(resultados)
    return t


class TestCriacaoAsserts:
    RES = [("estruturas_buscar", TENANT["estruturas_buscar"]), ("pesquisas", TENANT["pesquisas"])]

    def test_hashtags_not_five_fail(self):
        texto = RESPOSTA_OK.replace("#bemestar", "")
        falhas = avaliar_asserts({"saida_criacao": True}, _traco(texto, self.RES))
        assert [f.codigo for f in falhas] == ["pub1:hashtags:4"]

    def test_an_invented_source_fails(self):
        texto = RESPOSTA_OK.replace(URL, "https://inventada.exemplo/x")
        codigos = [f.codigo for f in avaliar_asserts({"saida_criacao": True}, _traco(texto, self.RES))]
        assert "pub1:fonte_inventada" in codigos

    def test_ignorar_drops_only_the_named_codes(self):
        texto = RESPOSTA_OK.replace("#bemestar", "")
        assert avaliar_asserts({"saida_criacao": {"ignorar": ["pub1:hashtags"]}}, _traco(texto, self.RES)) == []

    def test_an_invented_estrutura_code_fails(self):
        texto = RESPOSTA_OK.replace("#101", "#999")
        codigos = [f.codigo for f in avaliar_asserts({"propostas_criacao": {"tipo": "roteiro"}}, _traco(texto, self.RES))]
        assert codigos == ["roteiro1:codigo_inventado:999"]

    def test_headline_counts_and_word_limit(self):
        texto = ("1. Você dorme mal por um motivo simples (estrutura #101) (Mistério)\n"
                 "2. " + " ".join(["palavra"] * (MAX_HEADLINE_PALAVRAS + 1)) + " (estrutura #101)\n"
                 "### Estruturas usadas\n1. #101 (estrutura #101)\n")
        codigos = [f.codigo for f in avaliar_asserts(
            {"propostas_criacao": {"tipo": "headline", "min": 3}}, _traco(texto, self.RES))]
        assert codigos == ["propostas:2<3", f"headline2:palavras:{MAX_HEADLINE_PALAVRAS + 1}"]

    def test_a_refusal_has_no_options(self):
        assert avaliar_asserts({"propostas_criacao": {"tipo": "qualquer", "min": 0, "max": 0}},
                               _traco("Isso foge do que eu faço aqui.")) == []

    def test_a_leaked_term_fails_accent_insensitive(self):
        falhas = avaliar_asserts({"texto_sem_termos": ["Jose Ficticio"]}, _traco("como diz o José Fictício"))
        assert [f.codigo for f in falhas] == ["termo1"]

    @pytest.mark.parametrize("valor", [
        {"tipo": "outro"}, {"tipo": "headline", "min": -1}, {"tipo": "headline", "min": 3, "max": 1},
        {"tipo": "headline", "extra": 1},
    ])
    def test_propostas_shape_is_closed(self, valor):
        with pytest.raises(AssertInvalido):
            validar_asserts({"propostas_criacao": valor})

    @pytest.mark.parametrize("valor", [False, {}, {"outro": ["x"]}, {"ignorar": []}])
    def test_saida_shape_is_closed(self, valor):
        with pytest.raises(AssertInvalido):
            validar_asserts({"saida_criacao": valor})
