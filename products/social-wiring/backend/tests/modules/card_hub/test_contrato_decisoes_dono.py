"""Owner decisions 2026-10-05 for the contract generator, each backed by the
signed/draft corpus counts (private disk — counts quoted, nothing copied):

1. no comma between number-in-words groups (62 vs 9; "mil," 801 vs 42);
2. the certidões/pendências paragraph is "Parágrafo Primeiro" even when alone
   (76/78) — a NAMED exception, every other clause keeps "Único";
3. estado-civil certidão validity is 30 days (83 signed), one policy constant;
4. the vistoria clause defaults to the condomínio wording (91/93) unless the
   card explicitly says the imóvel is NOT in a condomínio.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from noctusai_lib.domain import texto_ptbr

from app.modules.card_hub.contrato_gerador import extenso, lint, numeracao
from app.modules.card_hub.contrato_gerador.numeracao import ContadorParagrafos
from app.modules.card_hub.contrato_gerador.politica import Politica
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.test_contrato_gerador import _render, _texto


class TestSemVirgulasEntreGrupos:
    def test_generator_extenso_has_no_commas_but_seed_default_is_unchanged(self):
        v = Decimal("2960000.00")
        assert extenso.reais_por_extenso(v) == "dois milhões novecentos e sessenta mil reais"
        assert texto_ptbr.reais_por_extenso(v) == "dois milhões, novecentos e sessenta mil reais"
        assert extenso.brl_por_extenso(v) == (
            "R$ 2.960.000,00 (dois milhões novecentos e sessenta mil reais)"
        )

    def test_lint_and_text_agree(self):
        ok = "O preço é R$ 2.960.000,00 (dois milhões novecentos e sessenta mil reais)."
        com_virgula = "O preço é R$ 2.960.000,00 (dois milhões, novecentos e sessenta mil reais)."
        kw = dict(referencias={}, clausulas={})
        assert "EXTENSO_DIVERGENTE" not in [h["codigo"] for h in lint.lint([ok], **kw)]
        assert "EXTENSO_DIVERGENTE" in [h["codigo"] for h in lint.lint([com_virgula], **kw)]

    def test_a_rendered_contract_with_a_seven_figure_price_has_no_group_commas(self):
        d = fx.variante(4)
        parcelas = [
            d.parcelas[0],
            replace(d.parcelas[1], valor=Decimal("2860000.00")),
        ]
        d = replace(d, parcelas=parcelas, valor_negociado=Decimal("2960000.00"))
        r = _render(4, d)
        texto = "\n".join(r.paragrafos)
        assert "dois milhões novecentos e sessenta mil reais" in texto
        assert "milhões, " not in texto
        assert [h for h in lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas)] == []


class TestParagrafoPrimeiroSozinho:
    def test_certidoes_lone_paragraph_reads_primeiro(self):
        c = ContadorParagrafos({"certidoes": 1})
        assert c("certidoes") == "Parágrafo Primeiro:"

    def test_every_other_clause_keeps_unico(self):
        for chave in ("objeto", "preco", "posse", "onus", "intermediacao"):
            assert ContadorParagrafos({chave: 1})(chave) == "Parágrafo Único:"
        assert numeracao.PARAGRAFO_PRIMEIRO_MESMO_SOZINHO == frozenset({"certidoes"})

    def test_rendered_non_permuta_certidoes_clause_says_primeiro_and_lint_is_clean(self):
        r = _render(1)
        i = next(i for i, p in enumerate(r.paragrafos) if "DAS CERTIDÕES E DOCUMENTOS" in p)
        j = next(j for j, p in enumerate(r.paragrafos) if j > i and p.startswith("CLÁUSULA "))
        rotulos = [p.split(":")[0] for p in r.paragrafos[i:j] if p.startswith("Parágrafo")]
        assert rotulos == ["Parágrafo Primeiro"]
        assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []

    def test_lint_flags_a_lone_unico_in_certidoes_but_accepts_it_elsewhere(self):
        def hits(titulo: str, rotulo: str) -> list[str]:
            ps = [f"CLÁUSULA PRIMEIRA – {titulo}", f"Parágrafo {rotulo}: texto.", "CLÁUSULA SEGUNDA – X"]
            return [h["codigo"] for h in lint.lint(ps, referencias={}, clausulas={}) if h["codigo"].startswith("PARAGRAFO")]

        assert hits("DAS CERTIDÕES E DOCUMENTOS", "Único") == ["PARAGRAFO_UNICO"]
        assert hits("DAS CERTIDÕES E DOCUMENTOS", "Primeiro") == []
        assert hits("DO OBJETO DO CONTRATO", "Único") == []
        assert hits("DO OBJETO DO CONTRATO", "Primeiro") == ["PARAGRAFO_UNICO"]


class TestEstadoCivil30Dias:
    def test_single_policy_constant_is_30(self):
        assert Politica().certidao_estado_civil_max_dias == 30

    def test_pendencia_wording_follows_the_policy(self):
        assert "com data de emissão inferior a 30 dias" in _texto(1)


class TestVistoriaCondominioPorPadrao:
    def _vistoria(self, d) -> str:
        r = _render(1, d)
        i = next(i for i, p in enumerate(r.paragrafos) if "DA VISTORIA PRÉVIA" in p)
        return r.paragrafos[i + 1]

    def _sem_empreendimento(self):
        d = fx.variante(1)
        return replace(d, imovel=replace(d.imovel, empreendimento=None))

    def test_without_empreendimento_and_without_an_answer_it_is_condominio_wording(self):
        d = self._sem_empreendimento()
        assert d.imovel.em_condominio is None
        assert "áreas de uso comum do condomínio" in self._vistoria(d)

    def test_only_an_explicit_false_switches_it_off(self):
        d = self._sem_empreendimento()
        d = replace(d, imovel=replace(d.imovel, em_condominio=False))
        texto = self._vistoria(d)
        assert "condomínio" not in texto
        assert "do estado atual de conservação do imóvel" in texto

    def test_explicit_true_and_empreendimento_stay_condominio(self):
        d = fx.variante(1)
        assert "áreas de uso comum do condomínio" in self._vistoria(d)
        d = replace(d, imovel=replace(d.imovel, em_condominio=True))
        assert "áreas de uso comum do condomínio" in self._vistoria(d)

    def test_manifesta_agrees_with_one_or_several_buyers(self):
        d = self._sem_empreendimento()
        um = self._vistoria(d)
        assert "pelo que manifesta seu conhecimento" in um and "Declara " in um
        dois = self._vistoria(replace(d, compradores=[d.compradores[0], replace(d.compradores[0], parte_id="parte-c2", nome="Beltrana de Tal")]))
        assert "pelo que manifestam seu conhecimento" in dois and "Declaram " in dois
