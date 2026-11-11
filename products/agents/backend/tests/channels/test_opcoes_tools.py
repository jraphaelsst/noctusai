"""The generic offer tools (migration 081): ``oferecer_opcoes`` / ``detalhes_opcao`` / ``registrar_reacao_opcao`` over a
:class:`~app.catalogos.CatalogoOpcoes`, driven through the REAL toolset handler with the REAL qualification service
(Fake stores, nothing of ours patched), plus the proof that Julia -- whose rows name the real-estate tools -- is
byte-for-byte what she was.

Real-estate and generic tools share ONE core, so the second half checks the two vocabularies side by side."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from noctusai_lib.integrations.llm import ToolCall

from app.catalogos import FixtureCatalogo
from app.channels import tool_registry as tr
from app.channels.tool_registry import JuliaTurno, TOOLS, construir_toolset, schema_de, tools_ofertaveis
from app.clients.social_wiring import FakeSocialWiringClient
from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.models import EventoImovel, LeadSinais, Registro
from app.qualificacao.service import EventoImovelResultado, QualificacaoService
from app.qualificacao.store import FakePadraoStore
from app.schemas.channels import ChannelContexto
from app.stores.conformidade import LIMITES_PADRAO
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS
from app.studio.models import ConteudoBundle, FerramentaData, TextoData
from app.studio.textos_registry import CODIGOS_RECUSA, RECUSAS_POR_FERRAMENTA, TEXTOS, chaves_exigidas
from tests.channels.julia_v2 import publicar_padrao, texto_de, versao_com_identidade

GOLDEN = Path(__file__).parent / "golden" / "julia_ferramentas_baseline.json"
ORG, AGENT, THREAD, LEAD = uuid4(), uuid4(), uuid4(), uuid4()
NOVAS = ("oferecer_opcoes", "detalhes_opcao", "registrar_reacao_opcao")
OPCAO_A, OPCAO_B, OPCAO_C = "opcao-a", "opcao-b", "opcao-c"


def _conteudo(*ferramentas: str) -> ConteudoBundle:
    return ConteudoBundle(
        textos=tuple(TextoData(c, texto_de(c)) for c in TEXTOS if TEXTOS[c].aplica_a != "runtime"),
        ferramentas=tuple(FerramentaData(n, f"desc:{n}") for n in ferramentas),
    )


def _estado(origem: str | None):
    return ChannelContexto.model_validate({
        "hash": "0" * 64, "agora": "2026-11-10T12:00:00+00:00", "fuso": "America/Sao_Paulo",
        "estado": {"interacao_id": str(uuid4()), "encerrado": False,
                   **({"origem": {"codigo_imovel_campanha": origem}} if origem else {})},
    }).estado


class Mundo:
    """One lead of one agent whose standard names ``catalogo``; ``chamar`` runs a tool through the real handler."""

    def __init__(self, *, catalogo: str | None = "fixture", ferramentas=NOVAS, qualificado=True, limites=LIMITES_PADRAO,
                 origem: str | None = None, fixo: Any = None, lote: int = 3, sw: Any = None, qual_wrap=None):
        self.padroes, self.leads = FakePadraoStore(), FakeLeadQualificacaoStore()
        base = versao_com_identidade()
        vid = publicar_padrao(self.padroes, versao=replace(
            base, parametros=replace(base.parametros, catalogo=catalogo, lote_ofertas=lote)))
        self.padrao = self.padroes.obter_versao(vid)
        self.qual = QualificacaoService(self.padroes, self.leads)
        if qualificado:  # ``minimo_para_ofertar`` of the fixture standard
            self.leads.adicionar_registros(
                ORG, LEAD, agent_id=AGENT, versao_id=vid, thread_id=None, message_id=None,
                registros=[Registro("operacao", "compra", "migracao"), Registro("interesse_campanha", "aberto", "migracao"),
                           Registro("regioes", ["Pinheiros"], "migracao")])
        self.t = JuliaTurno(
            org_id=ORG, agent_id=AGENT, agent_key="sdr", thread_id=THREAD, lead_ref_id=LEAD, conteudo=_conteudo(*ferramentas),
            compiled_hash="h" * 64, padrao=self.padrao, qual=qual_wrap(self.qual) if qual_wrap else self.qual, threads=None,
            skills=None, sw=sw, ident=None, handoff_destino=None, limites=limites, mensagens_lead=[],
            sinais=LeadSinais(), estado_sw=_estado(origem), catalogo_fixo=fixo)
        self.toolset = construir_toolset(self.t)

    def chamar(self, nome: str, **args: Any) -> dict[str, Any]:
        self.t.reiniciar_tentativa()  # one call per tool per turn is the cap (``max_oferecer_turno``): each call is a turn
        r = asyncio.run(self.toolset.handler(ToolCall("c1", nome, args)))
        return json.loads(r.content)

    def eventos(self, catalogo: str | None = None) -> list[tuple[str, str, str]]:
        return [(e.evento, e.codigo_imovel, e.catalogo) for e in self.leads.listar_eventos(ORG, LEAD)
                if catalogo in (None, e.catalogo)]


class TestOferecerOpcoes:
    def test_similares_offers_a_batch_with_the_generic_shape_and_records_it_under_the_catalogue(self):
        m = Mundo(lote=2)
        r = m.chamar("oferecer_opcoes", modo="similares")
        assert r["ok"] is True and r["lote"] == 1
        opcoes = r["dados_catalogo"]["opcoes"]
        assert [o["codigo"] for o in opcoes] == [OPCAO_A, OPCAO_B]
        assert set(opcoes[0]) == {"codigo", "titulo", "resumo", "atributos"} and opcoes[0]["titulo"] == "Opção A"
        assert m.eventos() == [("oferecido", OPCAO_A, "fixture"), ("oferecido", OPCAO_B, "fixture")]
        assert OPCAO_A in m.t.codigos_vistos  # conformance reads the same sets the real-estate tool fills

    def test_the_next_batch_skips_what_was_offered_then_the_catalogue_runs_out(self):
        m = Mundo(lote=2)
        m.chamar("oferecer_opcoes", modo="similares")
        r = m.chamar("oferecer_opcoes", modo="similares")
        assert [o["codigo"] for o in r["dados_catalogo"]["opcoes"]] == [OPCAO_C] and r["lote"] == 2
        r = m.chamar("oferecer_opcoes", modo="similares")
        assert r["ok"] is True and r["esgotado"] is True and "dados_catalogo" not in r

    def test_the_limit_argument_narrows_the_batch(self):
        r = Mundo(lote=3).chamar("oferecer_opcoes", modo="similares", limite=1)
        assert len(r["dados_catalogo"]["opcoes"]) == 1

    def test_modo_origem_offers_the_option_the_lead_arrived_with_even_before_qualification(self):
        m = Mundo(qualificado=False, origem=OPCAO_B)
        r = m.chamar("oferecer_opcoes", modo="origem")
        assert r["ok"] is True and [o["codigo"] for o in r["dados_catalogo"]["opcoes"]] == [OPCAO_B]
        assert m.eventos() == [("oferecido", OPCAO_B, "fixture")]

    def test_asking_for_the_origin_again_resends_it_without_a_new_event(self):
        m = Mundo(origem=OPCAO_B)
        m.chamar("oferecer_opcoes", modo="origem")
        r = m.chamar("oferecer_opcoes", modo="origem")
        assert r["reenvio"] is True and r["dados_catalogo"]["opcoes"][0]["codigo"] == OPCAO_B
        assert len(m.eventos()) == 1

    def test_refusal_sem_origem(self):
        r = Mundo().chamar("oferecer_opcoes", modo="origem")
        assert (r["ok"], r["codigo"]) == (False, "sem_origem") and r["mensagem"] == "txt:ferramenta.resultado.recusa.sem_origem"

    def test_refusal_nao_pode_ofertar_until_the_standard_says_so(self):
        assert Mundo(qualificado=False).chamar("oferecer_opcoes", modo="similares")["codigo"] == "nao_pode_ofertar"

    def test_refusal_limite_ofertas(self):
        m = Mundo(limites=replace(LIMITES_PADRAO, max_imoveis_distintos=1), lote=1)
        assert m.chamar("oferecer_opcoes", modo="similares")["ok"] is True
        assert m.chamar("oferecer_opcoes", modo="similares")["codigo"] == "limite_ofertas"

    @pytest.mark.parametrize(("recusa_do_servico", "esperado"), [
        ("lote_invalido", "lote_invalido"),
        ("imovel_ja_oferecido", "imovel_ja_oferecido"),  # an offer race is tolerated: the option IS on record
        ("evento_invalido", "evento_invalido"),
    ])
    def test_refusals_the_service_returns_reach_the_model_under_their_code(self, recusa_do_servico, esperado):
        class Recusa:
            def __init__(self, qual): self._q = qual
            def __getattr__(self, n): return getattr(self._q, n)
            def registrar_evento_imovel(self, *a, **k): return EventoImovelResultado(False, recusa_do_servico)

        r = Mundo(qual_wrap=Recusa).chamar("oferecer_opcoes", modo="similares")
        if recusa_do_servico == "imovel_ja_oferecido":
            assert r["ok"] is True  # tolerated, like the real-estate tool
        else:
            assert r["codigo"] == esperado

    def test_opcao_ja_oferecida_is_the_generic_name_of_imovel_ja_oferecido(self):
        assert tr._codigo_recusa("imovel_ja_oferecido", True) == "opcao_ja_oferecida"
        assert tr._codigo_recusa("imovel_nao_oferecido", True) == "opcao_nao_oferecida"
        assert tr._codigo_recusa("imovel_ja_oferecido", False) == "imovel_ja_oferecido"
        assert tr._codigo_recusa(None, True) == "evento_invalido"

    def test_an_unavailable_catalogue_is_indisponivel(self):
        r = Mundo(fixo=FixtureCatalogo(falhar=True)).chamar("oferecer_opcoes", modo="similares")
        assert (r["ok"], r["codigo"]) == (False, "indisponivel")

    def test_an_unknown_catalogue_key_is_not_offered(self):
        m = Mundo(catalogo="inventado")
        assert not {s.name for s in m.toolset.tools} & set(NOVAS)  # the standard names a catalogue nobody can build

    def test_a_key_that_stops_resolving_mid_flight_answers_indisponivel_and_logs_the_cause(self, caplog):
        m = Mundo()
        m.t.padrao = replace(m.t.padrao, parametros=replace(m.t.padrao.parametros, catalogo="inventado"))
        with caplog.at_level("ERROR"):
            r = m.chamar("oferecer_opcoes", modo="similares")
        assert (r["ok"], r["codigo"]) == (False, "indisponivel") and m.eventos() == []  # never another catalogue's options
        assert "catalogo_indisponivel" in caplog.text and "inventado" in caplog.text

    def test_an_agent_that_names_no_catalogue_is_not_offered_the_tools(self):
        m = Mundo(catalogo=None)
        assert not {s.name for s in m.toolset.tools} & set(NOVAS)

    def test_the_eval_world_catalogue_replaces_whatever_the_standard_names(self):
        fixo = FixtureCatalogo([{"codigo": "Z1", "titulo": "Sintética"}])
        m = Mundo(catalogo=None, fixo=fixo)
        r = m.chamar("oferecer_opcoes", modo="similares")
        assert [o["codigo"] for o in r["dados_catalogo"]["opcoes"]] == ["Z1"] and fixo.chamadas

    def test_catalogue_text_is_shaped_before_the_model_reads_it(self):
        fixo = FixtureCatalogo([{"codigo": "Z1", "titulo": "Ligue 11 99999-8888", "resumo": "veja https://evil.example/x",
                                 "link": "https://ok.example/z1", "atributos_extra": "ignorado"}])
        o = Mundo(fixo=fixo).chamar("oferecer_opcoes", modo="similares")["dados_catalogo"]["opcoes"][0]
        assert "99999" not in o["titulo"] and "evil.example" not in o["resumo"] and o["link"] == "https://ok.example/z1"

    def test_only_the_contracted_siblings_are_forwarded(self):
        class ComMeta(FixtureCatalogo):
            async def buscar(self, *a, **k):
                b = await super().buscar(*a, **k)
                return replace(b, meta={"relaxado": ["bairro"], "itens_nao_verificaveis": ["pets"], "restantes_estimados": 9, "x": 1})

        r = Mundo(fixo=ComMeta()).chamar("oferecer_opcoes", modo="similares")
        assert r["relaxado"] == ["bairro"] and r["itens_nao_verificaveis"] == ["pets"]
        assert "restantes_estimados" not in r and "x" not in r


class TestDuplicateOfferIsPerCatalogue:
    def _svc(self):
        padroes, leads = FakePadraoStore(), FakeLeadQualificacaoStore()
        vid = publicar_padrao(padroes)
        return QualificacaoService(padroes, leads), vid

    def _oferecer(self, qual, vid, codigo, catalogo):
        return qual.registrar_evento_imovel(
            ORG, LEAD, agent_id=AGENT, versao_id=vid, codigo_imovel=codigo, evento="oferecido", origem="similar", lote=1,
            catalogo=catalogo)

    def test_the_same_code_in_the_same_catalogue_is_refused_the_second_time(self):
        qual, vid = self._svc()
        assert self._oferecer(qual, vid, "X1", "fixture").ok
        assert self._oferecer(qual, vid, "X1", "fixture").codigo == "imovel_ja_oferecido"

    def test_the_same_code_in_another_catalogue_is_another_option(self):
        qual, vid = self._svc()
        assert self._oferecer(qual, vid, "X1", "imoveis_sw").ok
        assert self._oferecer(qual, vid, "X1", "fixture").ok
        assert qual.codigos_oferecidos(ORG, LEAD, "fixture") == ["X1"]
        assert qual.codigos_oferecidos(ORG, LEAD, "outro") == []

    def test_a_reaction_needs_the_offer_in_ITS_catalogue(self):
        qual, vid = self._svc()
        self._oferecer(qual, vid, "X1", "imoveis_sw")
        r = qual.registrar_evento_imovel(
            ORG, LEAD, agent_id=AGENT, versao_id=vid, codigo_imovel="X1", evento="gostou", origem="similar", catalogo="fixture")
        assert r.codigo == "imovel_nao_oferecido"


class TestDetalhesOpcao:
    def test_the_detail_is_shaped_and_a_new_code_is_recorded_as_asked_by_the_lead(self):
        m = Mundo()
        r = m.chamar("detalhes_opcao", codigo=OPCAO_B)
        assert r["encontrado"] is True and r["dados_catalogo"]["codigo"] == OPCAO_B
        assert m.eventos() == [("oferecido", OPCAO_B, "fixture")]
        assert m.leads.listar_eventos(ORG, LEAD)[0].origem == "pedido_lead"

    def test_an_unknown_code_is_not_found_and_nothing_is_remembered(self):
        m = Mundo()
        assert m.chamar("detalhes_opcao", codigo="nada") == {"ok": True, "encontrado": False}
        assert m.eventos() == []

    def test_refusal_limite_ofertas(self):
        m = Mundo(limites=replace(LIMITES_PADRAO, max_imoveis_distintos=1))
        m.chamar("detalhes_opcao", codigo=OPCAO_A)
        assert m.chamar("detalhes_opcao", codigo=OPCAO_B)["codigo"] == "limite_ofertas"

    def test_an_unavailable_catalogue_is_indisponivel(self):
        assert Mundo(fixo=FixtureCatalogo(falhar=True)).chamar("detalhes_opcao", codigo=OPCAO_A)["codigo"] == "indisponivel"


class TestRegistrarReacaoOpcao:
    @pytest.mark.parametrize("reacao", ["gostou", "nao_gostou", "quer_ver_mais"])
    def test_each_reaction_is_the_event_the_engine_reads(self, reacao):
        m = Mundo()
        m.chamar("oferecer_opcoes", modo="similares", limite=1)
        r = m.chamar("registrar_reacao_opcao", codigo=OPCAO_A, reacao=reacao, motivo="porque sim")
        assert r == {"ok": True, "inalterado": False}
        assert (reacao, OPCAO_A, "fixture") in m.eventos()
        assert m.leads.listar_eventos(ORG, LEAD)[-1].motivo == "porque sim"

    def test_the_same_reaction_twice_is_unchanged(self):
        m = Mundo()
        m.chamar("oferecer_opcoes", modo="similares", limite=1)
        m.chamar("registrar_reacao_opcao", codigo=OPCAO_A, reacao="gostou")
        assert m.chamar("registrar_reacao_opcao", codigo=OPCAO_A, reacao="gostou")["inalterado"] is True

    def test_refusal_opcao_nao_oferecida(self):
        r = Mundo().chamar("registrar_reacao_opcao", codigo=OPCAO_A, reacao="gostou")
        assert (r["ok"], r["codigo"]) == (False, "opcao_nao_oferecida")

    def test_the_reaction_moves_the_qualification_like_the_real_estate_one(self):
        m = Mundo()
        antes = m.qual.avaliar(ORG, LEAD, m.padrao.id)
        m.chamar("oferecer_opcoes", modo="similares", limite=1)
        m.chamar("registrar_reacao_opcao", codigo=OPCAO_A, reacao="gostou")
        depois = m.qual.avaliar(ORG, LEAD, m.padrao.id)
        assert depois.score > antes.score  # ``imoveis_gostou`` scores: the same engine input as ``registrar_reacao_imovel``


class TestSchemas:
    def test_the_generic_tools_are_strict_and_mirror_the_real_estate_ones(self):
        for nome, imovel in zip(NOVAS, ("oferecer_imoveis", "detalhes_imovel", "registrar_reacao_imovel")):
            sch = schema_de(nome, {})
            assert sch["additionalProperties"] is False
            assert set(sch["properties"]) == set(schema_de(imovel, {})["properties"])
        assert schema_de("oferecer_opcoes", {})["properties"]["modo"]["enum"] == ["origem", "similares"]
        assert schema_de("oferecer_opcoes", {})["properties"]["limite"] == schema_de("oferecer_imoveis", {})["properties"]["limite"]

    def test_no_org_or_lead_id_in_any_argument(self):
        for nome in NOVAS:
            assert not {"org_id", "lead_ref_id", "agent_id", "catalogo"} & set(schema_de(nome, {})["properties"])

    def test_every_refusal_code_of_the_generic_tools_has_its_text_row_tied_to_them(self):
        for codigo in ("sem_origem", "opcao_ja_oferecida", "opcao_nao_oferecida", "nao_pode_ofertar", "limite_ofertas"):
            assert codigo in CODIGOS_RECUSA
            assert RECUSAS_POR_FERRAMENTA[codigo] & set(NOVAS)
            assert f"ferramenta.resultado.recusa.{codigo}" in TEXTOS
        for codigo in ("sem_origem", "opcao_ja_oferecida", "opcao_nao_oferecida"):
            assert tr.classe_recusa(codigo) in ("corrigivel", "contada")
        assert tr.classe_recusa("sem_origem") == "corrigivel" and tr.classe_recusa("opcao_ja_oferecida") == "contada"


class TestJuliaIsUnchanged:
    """Her rows name the real-estate tools; nothing of the generic ones reaches her toolset, her required texts or the
    schemas the provider sees. The baseline JSON was frozen from the registry BEFORE this change."""

    base = json.loads(GOLDEN.read_text())

    def test_her_tool_set_is_the_frozen_one_and_the_new_tools_are_additions_nobody_asked_for(self):
        assert [n for n in TOOLS if n not in NOVAS] == self.base["ferramentas"]
        assert set(NOVAS) <= set(TOOLS) and set(NOVAS) <= FERRAMENTAS_CONHECIDAS

    def test_the_schemas_of_her_tools_are_identical(self):
        for nome in self.base["ferramentas"]:
            assert TOOLS[nome].args.model_json_schema() == self.base["schemas"][nome], nome
            assert sorted(TOOLS[nome].exige) == self.base["exige"][nome], nome

    def test_her_effective_required_text_set_is_identical(self):
        exigidas = chaves_exigidas(
            tool_policy={"web_search": False, "knowledge": False}, tem_skills=True, com_cliente=False, canal=True,
            com_qualificacao=True, com_dados_org=True, ferramentas_ativas=frozenset(self.base["ferramentas"]))
        assert sorted(exigidas) == self.base["textos_exigidos"]

    def test_an_agent_that_adopts_the_generic_tools_owes_exactly_the_new_texts(self):
        kw = dict(tool_policy={"web_search": False, "knowledge": False}, tem_skills=True, com_cliente=False, canal=True,
                  com_qualificacao=True, com_dados_org=True)
        antes = chaves_exigidas(ferramentas_ativas=frozenset(self.base["ferramentas"]), **kw)
        depois = chaves_exigidas(ferramentas_ativas=frozenset(self.base["ferramentas"]) | set(NOVAS), **kw)
        assert antes <= depois
        assert depois - antes == {
            "ferramenta.resultado.recusa.sem_origem", "ferramenta.resultado.recusa.opcao_ja_oferecida",
            "ferramenta.resultado.recusa.opcao_nao_oferecida"}

    def test_her_rows_offer_her_tools_and_none_of_the_generic_ones_even_with_a_catalogue_in_the_standard(self):
        rows = [*self.base["ferramentas"]]
        m = Mundo(catalogo="fixture", ferramentas=rows)
        oferecidas = {s.name for s in m.toolset.tools}
        assert not oferecidas & set(NOVAS) and {"avaliar_lead", "registrar_perfil"} <= oferecidas
        # ``sw`` is absent in this world: her SW-backed tools are not offered either, exactly as before
        assert "oferecer_imoveis" not in oferecidas

    def test_the_real_estate_offer_still_reads_social_wiring_through_the_adapter(self):
        sw = FakeSocialWiringClient()
        sw.julia_token_orgs.add(ORG)
        sw.julia_responses["buscar_imoveis"] = {"data": [{"codigo": "A1", "titulo": "Apto", "preco": 1}], "relaxado": ["bairro"],
                                                "restantes_estimados": 2}
        m = Mundo(catalogo=None, ferramentas=self.base["ferramentas"], sw=sw)
        r = m.chamar("oferecer_imoveis", modo="similares", limite=1)
        assert r["dados_catalogo"] == {"imoveis": [{"codigo": "A1", "titulo": "Apto", "preco": 1}]}  # key + shape unchanged
        assert r["relaxado"] == ["bairro"] and r["restantes_estimados"] == 2  # the 4-key meta allowlist, unchanged
        assert m.eventos() == [("oferecido", "A1", "imoveis_sw")]
        (_o, nome, args), = sw.julia_calls
        assert nome == "buscar_imoveis" and args["excluir_codigos"] == [] and args["limite"] == 1
        assert m.chamar("detalhes_imovel", codigo="A1")["ok"] is True
        assert [c[1] for c in sw.julia_calls] == ["buscar_imoveis", "detalhes_imovel"]
