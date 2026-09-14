"""F5 contract generator — the pure core, over synthetic fixtures (no DB).

WHAT THESE PIN
--------------
- the switch derivation for each of spec §1.3's 6 variants, and its modelo;
- the gate REFUSES with the exact missing fields, never renders blanks;
- Σ parcelas ≠ preço and RG = CPF block;
- clause numbers and "Cláusula X" references stay consecutive and correct as
  conditional clauses switch on/off, and "Parágrafo Único" is decided by what
  actually rendered;
- every "R$ X (Y)" in the rendered text round-trips through the extenso;
- the matrícula's selected text lands byte-identical in word/document.xml;
- the post-render lint catches the sample contracts' hand-assembly errors.

Rendering uses the REAL seed docxtpl adapter — the Fake never evaluates Jinja.
"""
from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

import pytest

from noctusai_lib.domain.texto_ptbr import parse_brl, reais_por_extenso
from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, lint
from app.modules.card_hub.contrato_gerador.concordancia import lado
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(n: int, d=None):
    d = d if d is not None else fx.variante(n)
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol)
    return d, pol, sw, derivacao.avaliar(d, sw, pol, fx.ASSINATURA)


def _render(n: int, d=None):
    d, pol, sw, av = _avaliar(n, d)
    assert av.pronto, (av.faltando, av.bloqueios)
    return documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)


def _clausulas(paragrafos):
    return [p for p in paragrafos if p.startswith("CLÁUSULA ")]


class TestSwitchesPorVariante:
    ESPERADO = {
        1: ("compra_venda", dict(tem_financiamento=True, tem_intermediaria=True, tem_intermediacao=True,
                                 tem_itens_integrantes=True, tem_fgts=False, tem_saldo_devedor=False,
                                 tem_permuta=False, ad_corpus=False, a_vista=False)),
        2: ("compra_venda", dict(tem_financiamento=True, tem_fgts=True, tem_saldo_devedor=True,
                                 tem_intermediacao=True, tem_permuta=False)),
        3: ("compra_venda", dict(tem_itens_integrantes=False, ad_corpus=True, tem_intermediacao=True)),
        4: ("compra_venda_a_vista", dict(a_vista=True, tem_saldo_devedor=True, tem_intermediacao=True,
                                         tem_financiamento=False)),
        5: ("compra_venda_permuta", dict(tem_permuta=True, tem_financiamento=True, tem_parcelas_diretas=True,
                                         tem_confissao=True, tem_saldo_devedor=True, tem_intermediacao=False)),
        6: ("compra_venda_permuta", dict(tem_permuta=True, tem_intermediaria=True, tem_declaracao_partes=True,
                                         ad_corpus=True, tem_intermediacao=False, tem_confissao=False)),
    }

    @pytest.mark.parametrize("n", range(1, 7))
    def test_variant(self, n):
        d, _pol, sw, av = _avaliar(n)
        modelo, switches = self.ESPERADO[n]
        assert derivacao.modelo_derivado(sw) == modelo
        assert {k: sw[k] for k in switches} == switches
        assert av.pronto, (av.faltando, av.bloqueios)

    @pytest.mark.parametrize("n", range(1, 7))
    def test_every_variant_renders_14_consecutive_clauses_with_a_clean_lint(self, n):
        r = _render(n)
        ordinais = [c.split(" – ")[0].split(" - ")[0] for c in _clausulas(r.paragrafos)]
        assert len(ordinais) == 14  # 13 fixed + exactly one conditional in each sample variant
        assert ordinais[0] == "CLÁUSULA PRIMEIRA" and ordinais[-1] == "CLÁUSULA DÉCIMA QUARTA"
        assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []


class TestNumeracaoAoLigarEDesligarClausulas:
    def _resolutiva(self, paragrafos):
        return next(p for p in paragrafos if p.startswith("A presente transação é realizada"))

    def test_confissao_on_shifts_every_later_number_and_reference(self):
        v1, v5 = _render(1), _render(5)
        assert "na Cláusula Sétima deste" in self._resolutiva(v1.paragrafos)
        assert "na Cláusula Oitava deste" in self._resolutiva(v5.paragrafos)
        assert v5.clausulas["confissao"] == 3 and v5.clausulas["certidoes"] == 4
        assert "confissao" not in v1.clausulas

    def test_declaracao_on_and_intermediacao_off(self):
        v6 = _render(6)
        assert v6.clausulas["declaracao_partes"] == 9
        assert "intermediacao" not in v6.clausulas
        assert v6.clausulas["foro"] == 14

    def test_a_lone_paragraph_is_unico_and_disappears_with_its_switch(self):
        v1, v3 = _render(1), _render(3)
        objeto = lambda ps: ps[ps.index("CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO") + 1 : ps.index("CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO")]
        assert [p for p in objeto(v1.paragrafos) if p.startswith("Parágrafo")][0].startswith("Parágrafo Único:")
        assert not [p for p in objeto(v3.paragrafos) if p.startswith("Parágrafo")]

    def test_paragraphs_restart_per_clause(self):
        r = _render(5)
        preco = r.paragrafos.index("CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO")
        seguinte = next(i for i, p in enumerate(r.paragrafos) if i > preco and p.startswith("CLÁUSULA "))
        rotulos = [p.split(":")[0] for p in r.paragrafos[preco:seguinte] if p.startswith("Parágrafo")]
        assert rotulos == ["Parágrafo Primeiro", "Parágrafo Segundo"]

    def test_pendencia_letters_are_gap_free(self):
        r = _render(2)
        letras = [p.split("-)")[0] for p in r.paragrafos if re.match(r"^[a-z]{1,2}-\) ", p)]
        assert letras == [chr(ord("a") + i) for i in range(len(letras))]


class TestTextoRenderizado:
    def test_every_amount_round_trips_through_its_extenso(self):
        texto = "\n".join(_render(5).paragrafos)
        valores = re.findall(r"R\$ ([\d.]+,\d{2}) \(([^)]*)\)", texto)
        assert len(valores) >= 8
        for digitos, extenso in valores:
            assert reais_por_extenso(parse_brl(digitos)) == extenso

    def test_matricula_literal_text_is_byte_identical_in_document_xml(self):
        r = _render(1)
        xml = documento.document_xml(r.docx)
        for linha in fx.MATRICULA_TEXTO.split("\n"):
            assert linha in xml
        assert any(fx.MATRICULA_TEXTO in p for p in r.paragrafos)

    def test_multa_rescisoria_is_the_sinal(self):
        texto = "\n".join(_render(1).paragrafos)
        assert "multa rescisória no valor de R$ 50.000,00 (cinquenta mil reais)" in texto

    def test_mixed_gender_sellers_take_the_masculine_plural(self):
        d = fx.base_v1()
        segunda = replace(fx.pessoa("v2", "vendedor", "proprietario", "Cicrana Amostra", "Feminino",
                                    "111222333", "55.555.555-5"))
        d = replace(d, vendedores=[d.vendedores[0], segunda])
        texto = "\n".join(_render(1, d).paragrafos)
        assert '"VENDEDORES"' in texto and "Os VENDEDORES" in texto
        assert lado(["f"], "vendedor").NOME == "VENDEDORA"
        assert "VENDEDORA" not in texto


class TestGate:
    def test_production_today_refuses_naming_every_missing_field(self):
        _d, _pol, _sw, av = _avaliar(1, fx.sem_complementos(fx.variante(1)))
        assert not av.pronto
        assert {f["campo"] for f in av.faltando} == {
            "contrato.titulo_aquisitivo_texto",
            "contrato.posse_prazo_dias",
            "contrato.posse_marco",
            "imobiliaria.plataforma_assinatura",
            "contrato.intermediario.int-1.favorecido",
            "contrato.corretagem_contratantes",
            "contrato.corretagem_parcelas_marco",
        }
        assert all(f["onde"] in {"partes", "certidoes", "imovel", "matricula", "negociacao",
                                 "financiamento", "imobiliaria", "contrato"} for f in av.faltando)

    def test_soma_das_parcelas_diferente_do_preco_blocks(self):
        d = replace(fx.variante(1), valor_negociado=Decimal("500000.01"))
        _d, _pol, _sw, av = _avaliar(1, d)
        assert [b["codigo"] for b in av.bloqueios] == ["SOMA_PARCELAS_DIFERENTE_DO_PRECO"]
        assert not av.pronto

    def test_rg_igual_ao_cpf_blocks(self):
        d = fx.variante(1)
        v = replace(d.vendedores[0], rg=d.vendedores[0].cpf)
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert "RG_IGUAL_CPF" in [b["codigo"] for b in av.bloqueios]

    def test_a_missing_certidao_is_named_per_parte(self):
        d = fx.variante(1)
        v = replace(d.vendedores[0], certidoes=[c for c in d.vendedores[0].certidoes if c.tipo != "serasa"])
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert [(f["campo"], f["parte_id"], f["onde"]) for f in av.faltando] == [
            ("certidao.serasa", "parte-v1", "certidoes")
        ]

    def test_a_married_seller_without_the_spouse_on_the_same_side_blocks(self):
        d = fx.variante(1)
        v = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="c1")
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert "CONJUGE_FORA_DO_LADO" in [b["codigo"] for b in av.bloqueios]

    def test_titular_certidoes_are_missing_when_the_buyer_side_must_certify(self):
        d = fx.variante(5)
        titular = replace(d.compradores[0], parte_id=None, certidoes=None)
        _d, _pol, _sw, av = _avaliar(5, replace(d, compradores=[titular]))
        assert [f["campo"] for f in av.faltando] == ["certidoes.titular.c1"]

    def test_policy_defaults_surface_as_avisos_not_invented_text(self):
        _d, _pol, _sw, av = _avaliar(1)
        codigos = {a["codigo"] for a in av.avisos}
        assert {"ENCARGO_RESCISAO_NAO_DEFINIDO", "MULTA_DIARIA_POSSE_OMITIDA", "CORRETAGEM_RESCISAO_PELA_COMISSAO"} <= codigos


class TestLint:
    def test_duplicate_heading_and_wrong_reference_are_caught(self):
        paragrafos = [
            "CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO",
            "texto",
            "CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO",
            "descrito na Cláusula Terceira",
            "CLÁUSULA SEGUNDA – DAS CERTIDÕES E DOCUMENTOS",
        ]
        codigos = {h["codigo"] for h in lint.lint(paragrafos, referencias={"objeto": 1}, clausulas={"objeto": 1, "preco": 2})}
        assert {"CLAUSULA_DUPLICADA", "REFERENCIA_CLAUSULA_INEXISTENTE", "REFERENCIA_CLAUSULA_ERRADA"} <= codigos

    def test_letter_gap_paragraph_gap_and_bad_extenso_are_caught(self):
        paragrafos = [
            "CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO",
            "Parágrafo Primeiro: um",
            "Parágrafo Terceiro: dois",
            "a-) item;",
            "b-) item;",
            "d-) item.",
            "R$ 1.000,00 (mil e um reais)",
        ]
        codigos = {h["codigo"] for h in lint.lint(paragrafos, referencias={}, clausulas={"objeto": 1})}
        assert {"PARAGRAFO_FORA_DE_SEQUENCIA", "LETRAS_COM_LACUNA", "EXTENSO_DIVERGENTE"} <= codigos
