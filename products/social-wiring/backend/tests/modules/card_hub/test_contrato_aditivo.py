"""Aditivos (migration 190) — the pure core: gate + render, synthetic data.

WHAT THESE PIN
--------------
- both styles (house "ADITIVO AO INSTRUMENTO…", formal "PRIMEIRO TERMO
  ADITIVO") render from the synthetic V1 card with the generator's OWN lint
  clean — re-qualified parties, the original cited by its signing date, the
  amending sections, the ratification and the signatures;
- a structured payment amendment prints the RESTATED schedule through the
  generator's parcela wording (Σ = price, numbered 01..N), and a price
  amendment prints old → new;
- the gate refuses with the contract's own shape: original not signed,
  Σ new parcelas ≠ price (and the amended price is honoured), a party
  missing qualification, parcelas without a payment amendment, a commission
  amendment on a deal with no intermediação, an unknown parcela;
- the lint still bites: an internal clause reference that does not exist is
  caught; a citation of the ORIGINAL's clause is not mistaken for one;
- an `outro` amendment is printed verbatim and named in the legal review.

Rendering uses the REAL seed docxtpl adapter. All data is synthetic
(`contrato_gerador_fixtures`).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_aditivo import documento, service
from app.modules.card_hub.contrato_aditivo.avaliacao import avaliar
from app.modules.card_hub.contrato_aditivo.dados import DadosAditivo, alteracoes_de_json
from app.modules.card_hub.contrato_gerador.documento import gerar_pdf
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from tests.modules.card_hub import contrato_gerador_fixtures as fx

ORIGINAL = date(2026, 3, 10)
DATA = date(2026, 9, 20)


def _alteracoes(*itens: dict) -> list:
    return alteracoes_de_json(list(itens))


PAGAMENTO = {"tipo": "pagamento", "clausula_alvo": 2}
POSSE = {"tipo": "posse", "clausula_alvo": 5, "data": "2026-10-15", "precaria": True,
         "finalidade": "a medição para os móveis planejados"}
COMISSAO = {"tipo": "comissao", "clausula_alvo": 13, "parcela_corretagem": 1, "marco": "parcela",
            "parcela_numero": 2}
OUTRO = {"tipo": "outro", "titulo": "Da trava de dados bancários",
         "texto": "Fica vedada qualquer alteração de dados de pagamento por canal diverso deste instrumento."}


def _novas_parcelas() -> list:
    """The V1 price (500 000) re-split: sinal paid, a second tranche moved
    forward, financiamento unchanged."""
    return [
        fx.parcela("n1", "sinal", "50000.00", 0, evento="quitada anteriormente",
                   forma_pagamento="PIX", favorecido_id="fav-v"),
        fx.parcela("n2", "direta", "30000.00", 1, evento="na assinatura do presente aditivo",
                   forma_pagamento="PIX", favorecido_id="fav-v"),
        fx.parcela("n3", "intermediaria", "20000.00", 2, evento="em até 30 dias da assinatura deste aditivo",
                   forma_pagamento="Transferência", favorecido_id="fav-v"),
        fx.parcela("n4", "financiamento", "400000.00", 3,
                   evento="com prazo máximo de 90 (noventa) dias corridos, a contar da assinatura deste aditivo"),
    ]


def _aditivo(*alteracoes: dict, estilo: str = "house", parcelas=None, **over) -> DadosAditivo:
    base = dict(
        aditivo_id="ad-1",
        contrato_id="contrato-1",
        ordinal=1,
        estilo=estilo,
        status="rascunho",
        alteracoes=_alteracoes(*alteracoes),
        parcelas=parcelas if parcelas is not None else [],
        assinatura_data=DATA,
        original_status="assinado",
        original_assinatura_data=ORIGINAL,
    )
    base.update(over)
    return DadosAditivo(**base)


def _render(d, ad):
    return documento.renderizar(get_docx_render_adapter(real=True), d, ad, POLITICA_PADRAO, DATA)


def _gate(d, ad):
    return avaliar(d, ad, POLITICA_PADRAO, DATA, DATA)


def _codigos(av) -> set[str]:
    return {b["codigo"] for b in av.bloqueios}


class TestRenderHouse:
    def test_house_style_renders_lint_clean_with_every_amendment(self):
        d = fx.base_v1()
        ad = _aditivo(PAGAMENTO, POSSE, COMISSAO, OUTRO, parcelas=_novas_parcelas())
        av = _gate(d, ad)
        assert av.pronto, (av.faltando, av.bloqueios)

        r = _render(d, ad)
        assert documento.lint_aditivo(r.paragrafos) == []
        texto = "\n".join(r.paragrafos)
        assert r.paragrafos[0].startswith(
            "ADITIVO AO INSTRUMENTO PARTICULAR DE PROMESSA DE VENDA E COMPRA DE BEM IMÓVEL – EDIFÍCIO EXEMPLO"
        )
        # Re-qualifies every party (corpus 5/5), house preamble.
        assert "Pelo presente Aditivo Contratual" in texto
        assert "FULANO DE TAL" in texto and "BELTRANA EXEMPLO" in texto
        # Cites the original by its signing date and re-quotes the imóvel.
        assert "CLÁUSULA PRIMEIRA – DO OBJETO DESTE ADITIVO" in texto
        assert "assinado entre as Partes em 10/03/2026" in texto
        assert "Matrícula Nº 12.345" in texto or "Matrícula Nº 12345" in texto
        # One CLÁUSULA per amendment, from SEGUNDA, in the fixed order.
        assert "CLÁUSULA SEGUNDA – DA ALTERAÇÃO DA FORMA DE PAGAMENTO" in texto
        assert "CLÁUSULA TERCEIRA – DA ALTERAÇÃO DA POSSE DO IMÓVEL" in texto
        assert "CLÁUSULA QUARTA – DA COMISSÃO" in texto
        assert "CLÁUSULA QUINTA – DA TRAVA DE DADOS BANCÁRIOS" in texto
        assert "CLÁUSULA SEXTA – DAS DEMAIS CLÁUSULAS E CONDIÇÕES CONTRATUAIS" in texto
        # Citations of the ORIGINAL's clauses.
        assert "Cláusula Segunda do contrato original" in texto
        assert "Cláusula Décima Terceira do contrato original" in texto
        assert "posse precária do imóvel a partir de 15/10/2026" in texto
        assert "quitação integral da Parcela 02" in texto
        assert OUTRO["texto"] in texto
        assert "Cidade Exemplo, 20 de setembro de 2026." in texto
        assert "TESTEMUNHAS:" in texto

    def test_the_payment_amendment_restates_the_schedule_through_the_generators_wording(self):
        d = fx.base_v1()
        r = _render(d, _aditivo(PAGAMENTO, parcelas=_novas_parcelas()))
        parcelas = [p for p in r.paragrafos if p.startswith("Parcela ")]
        assert [p[:10] for p in parcelas] == ["Parcela 01", "Parcela 02", "Parcela 03", "Parcela 04"]
        assert parcelas[0].startswith("Parcela 01: Sinal e princípio de pagamento: R$ 50.000,00")
        assert "R$ 30.000,00 (trinta mil reais)" in parcelas[1]
        texto = "\n".join(r.paragrafos)
        assert "O preço de R$ 500.000,00 (quinhentos mil reais)" in texto

    def test_a_price_amendment_prints_old_and_new_price(self):
        d = fx.base_v1()
        novas = _novas_parcelas()
        novas[1] = replace(novas[1], valor=Decimal("20000.00"))  # Σ = 490 000
        ad = _aditivo({**PAGAMENTO, "novo_valor": "490000.00"}, parcelas=novas)
        assert _gate(d, ad).pronto
        texto = "\n".join(_render(d, ad).paragrafos)
        assert "O preço ajustado de R$ 500.000,00 (quinhentos mil reais) fica alterado para R$ 490.000,00" in texto

    def test_a_second_house_aditivo_carries_its_ordinal_in_the_title(self):
        r = _render(fx.base_v1(), _aditivo(POSSE, ordinal=2))
        assert r.paragrafos[0].startswith("SEGUNDO ADITIVO AO INSTRUMENTO PARTICULAR")

    def test_the_pdf_is_produced_from_the_same_rendering(self):
        r = _render(fx.base_v1(), _aditivo(POSSE))
        assert gerar_pdf(r.docx)[:5] == b"%PDF-"


class TestRenderFormal:
    def test_formal_style_renders_lint_clean_numbered_sections(self):
        d = fx.base_v1()
        ad = _aditivo(PAGAMENTO, POSSE, COMISSAO, estilo="formal", parcelas=_novas_parcelas())
        assert _gate(d, ad).pronto
        r = _render(d, ad)
        assert documento.lint_aditivo(r.paragrafos) == []
        texto = "\n".join(r.paragrafos)
        assert r.paragrafos[0].startswith("PRIMEIRO TERMO ADITIVO AO INSTRUMENTO PARTICULAR")
        assert "Pelo presente instrumento particular" in texto
        assert "celebrar o presente PRIMEIRO TERMO ADITIVO" in texto
        assert "firmado em 10/03/2026" in texto
        assert "1. DA ALTERAÇÃO DA CLÁUSULA SEGUNDA – DO PREÇO E FORMA DE PAGAMENTO" in texto
        assert "1.1. As parcelas acima substituem integralmente" in texto
        assert "2. DA ALTERAÇÃO DA CLÁUSULA QUINTA – POSSE DO IMÓVEL" in texto
        assert "3. DA ALTERAÇÃO DA CLÁUSULA DÉCIMA TERCEIRA – INTERMEDIAÇÃO" in texto
        assert "4. DA RATIFICAÇÃO" in texto
        assert "4.1. O presente Termo Aditivo passa a integrar o instrumento originário" in texto
        assert "Cláusula Segunda do instrumento originário" in texto

    def test_a_fisica_aditivo_prints_signature_lines_and_vias(self):
        r = _render(fx.base_v1(), _aditivo(POSSE, estilo="formal", modalidade_assinatura="fisica"))
        texto = "\n".join(r.paragrafos)
        assert "em 02 (duas) vias de igual teor e forma" in texto
        assert "______________________________" in texto
        assert documento.lint_aditivo(r.paragrafos) == []


class TestGate:
    def test_an_unsigned_original_is_refused(self):
        av = _gate(fx.base_v1(), _aditivo(POSSE, original_status="rascunho", original_assinatura_data=None))
        assert "ORIGINAL_NAO_ASSINADO" in _codigos(av)
        assert "contrato.assinatura_data" in {f["campo"] for f in av.faltando}
        assert av.pronto is False

    def test_an_original_with_a_signing_date_admits_an_aditivo(self):
        assert _gate(fx.base_v1(), _aditivo(POSSE, original_status="em_revisao")).pronto

    def test_new_parcelas_must_sum_to_the_price(self):
        novas = _novas_parcelas()
        novas[1] = replace(novas[1], valor=Decimal("1000.00"))
        av = _gate(fx.base_v1(), _aditivo(PAGAMENTO, parcelas=novas))
        assert "SOMA_PARCELAS_DIFERENTE_DO_PRECO" in _codigos(av)

    def test_the_amended_price_is_what_the_parcelas_must_sum_to(self):
        av = _gate(fx.base_v1(), _aditivo({**PAGAMENTO, "novo_valor": "600000.00"}, parcelas=_novas_parcelas()))
        assert "SOMA_PARCELAS_DIFERENTE_DO_PRECO" in _codigos(av)

    def test_out_of_order_vencimentos_are_refused(self):
        novas = _novas_parcelas()
        novas[1] = replace(novas[1], vencimento=date(2026, 12, 1))
        novas[2] = replace(novas[2], vencimento=date(2026, 11, 1))
        assert "VENCIMENTOS_FORA_DE_ORDEM" in _codigos(_gate(fx.base_v1(), _aditivo(PAGAMENTO, parcelas=novas)))

    def test_a_payment_amendment_without_parcelas_is_faltando_on_the_aditivo(self):
        av = _gate(fx.base_v1(), _aditivo(PAGAMENTO))
        falta = next(f for f in av.faltando if f["campo"] == "aditivo.parcelas")
        assert falta["destino"]["alvo"] == "aditivo-ad-1"

    def test_a_schedule_falta_points_at_the_aditivo_not_the_negociacao(self):
        novas = _novas_parcelas()
        novas[2] = replace(novas[2], forma_pagamento=None)
        av = _gate(fx.base_v1(), _aditivo(PAGAMENTO, parcelas=novas))
        falta = next(f for f in av.faltando if f["campo"] == "aditivo.parcela.n3.forma_pagamento")
        assert falta["onde"] == "contrato" and falta["destino"]["alvo"] == "aditivo-ad-1"
        # The ORIGINAL's posse terms are not re-judged by the payment gate.
        assert not any(f["campo"].startswith("negociacao.posse") for f in av.faltando)

    def test_parcelas_without_a_payment_amendment_are_refused(self):
        av = _gate(fx.base_v1(), _aditivo(POSSE, parcelas=_novas_parcelas()))
        assert "PARCELAS_SEM_ALTERACAO_DE_PAGAMENTO" in _codigos(av)

    def test_a_party_missing_qualification_blocks(self):
        d = fx.base_v1()
        # `nacionalidade`, not `profissao`: a missing profissão only warns
        # since P5 F8 (the signed corpus omits it).
        d = replace(d, vendedores=[replace(d.vendedores[0], faltando_qualificacao=["nacionalidade"])])
        av = _gate(d, _aditivo(POSSE))
        assert "qualificacao.nacionalidade" in {f["campo"] for f in av.faltando}
        assert av.pronto is False

    def test_no_amendment_at_all_is_faltando(self):
        assert "aditivo.alteracoes" in {f["campo"] for f in _gate(fx.base_v1(), _aditivo()).faltando}

    def test_a_commission_amendment_needs_an_intermediacao(self):
        d = replace(fx.base_v1(), intermediarios=[])
        assert "COMISSAO_SEM_INTERMEDIACAO" in _codigos(_gate(d, _aditivo(COMISSAO)))

    def test_a_commission_parcela_must_exist(self):
        av = _gate(fx.base_v1(), _aditivo({**COMISSAO, "parcela_numero": 9}))
        assert "COMISSAO_PARCELA_INEXISTENTE" in _codigos(av)

    def test_an_aditivo_dated_before_the_original_is_refused(self):
        av = avaliar(fx.base_v1(), _aditivo(POSSE), POLITICA_PADRAO, date(2026, 1, 1), DATA)
        assert "ADITIVO_ANTERIOR_AO_ORIGINAL" in _codigos(av)

    def test_a_free_clause_is_flagged_for_the_legal_review(self):
        av = _gate(fx.base_v1(), _aditivo(OUTRO))
        assert av.pronto
        assert "OUTRO_EXIGE_REVISAO_JURIDICA" in {a["codigo"] for a in av.avisos}

    def test_a_generated_originals_clause_number_is_cross_checked(self):
        av = _gate(fx.base_v1(), _aditivo({**POSSE, "clausula_alvo": 1}, original_origem="gerado"))
        assert "CLAUSULA_ALVO_DIVERGENTE" in {a["codigo"] for a in av.avisos}


class TestLint:
    def test_a_citation_of_the_original_is_not_an_internal_reference(self):
        paragrafos = [
            "CLÁUSULA PRIMEIRA – DO OBJETO DESTE ADITIVO",
            "Altera a Cláusula Décima Terceira do contrato original e a Parcela 04 do contrato original.",
        ]
        assert documento.lint_aditivo(paragrafos) == []

    def test_an_internal_reference_to_a_missing_clause_still_bites(self):
        paragrafos = ["CLÁUSULA PRIMEIRA – DO OBJETO DESTE ADITIVO", "Conforme a Cláusula Terceira acima."]
        assert "REFERENCIA_CLAUSULA_INEXISTENTE" in {h["codigo"] for h in documento.lint_aditivo(paragrafos)}

    def test_a_citation_with_a_bogus_ordinal_is_caught(self):
        hits = documento.lint_aditivo(["Altera a Cláusula Zerésima do contrato original."])
        assert "REFERENCIA_ORIGINAL_INVALIDA" in {h["codigo"] for h in hits}


class TestRevisaoJuridica:
    def test_every_version_is_reviewed_and_each_free_clause_is_named(self):
        ad = _aditivo(POSSE, OUTRO)
        campos = service.campos_revisao(ad, ["DA TRAVA DE DADOS BANCÁRIOS"], "a" * 64)
        assert [c["campo"] for c in campos] == ["redacao", "outro"]
        assert campos[1]["rotulo"] == "Cláusula livre: DA TRAVA DE DADOS BANCÁRIOS"
        assert all(len(c["valor_sha256"]) == 64 for c in campos)


@pytest.mark.parametrize("estilo", ["house", "formal"])
def test_the_snapshot_hash_is_deterministic_and_data_sensitive(estilo):
    d = fx.base_v1()
    a = documento.snapshot_aditivo_sha256(d, _aditivo(POSSE, estilo=estilo), POLITICA_PADRAO, DATA)
    b = documento.snapshot_aditivo_sha256(d, _aditivo(POSSE, estilo=estilo), POLITICA_PADRAO, DATA)
    c = documento.snapshot_aditivo_sha256(d, _aditivo(COMISSAO, estilo=estilo), POLITICA_PADRAO, DATA)
    assert a == b != c


def test_aditivo_testemunhas_falta_lands_on_the_contratos_picker():
    d = fx.base_v1()
    d = replace(d, testemunhas=[])
    av = avaliar(d, _aditivo(POSSE), POLITICA_PADRAO, DATA, DATA)
    f = next(x for x in av.faltando if x["campo"] == "imobiliaria.testemunhas")
    assert f["destino"]["tela"] == "card_contratos"
    assert f["destino"]["alvo"] == f"contrato-testemunhas-select-{d.contrato_id}"
