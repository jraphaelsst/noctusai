"""`financiamento_imobiliario` — ONE parser, TWO readers (contrato +
proposta), sharing ONE Quadro Resumo vocabulary. All names, CPFs and
values in this file are invented; the 25-page contract fixtures use a
synthetic in-memory PDF built with PyMuPDF (no real document).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.integrations.documents import (
    ContaCreditoVendedor,
    ExtractionConfidence,
    FakeContratoFinanciamentoExtractor,
    FakePropostaFinanciamentoExtractor,
    FinanciamentoImobiliarioExtractor,
    FinanciamentoImobiliarioFields,
    TextSource,
    make_contrato_financiamento_extractor,
    make_proposta_financiamento_extractor,
    parse_financiamento_imobiliario,
)
from noctusai_lib.integrations.documents.financiamento_imobiliario import (
    LadderContratoFinanciamentoExtractor,
    LadderPropostaFinanciamentoExtractor,
)
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)

CPF_VALIDO = "412.954.238-98"
CPF_INVALIDO = "412.954.238-99"


def _quadro(
    *,
    compra_venda: str = "VALOR DE COMPRA E VENDA: R$ 500.000,00",
    financiado: str = "VALOR FINANCIADO: R$ 400.000,00",
    fgts: str = "RECURSOS DO FGTS: R$ 20.000,00",
    recursos_proprios: str = "RECURSOS PROPRIOS: R$ 80.000,00",
    prazo: str = "PRAZO: 360 meses",
    conta: str = (
        "CONTA DE CREDITO DO VENDEDOR: BANCO: ITAU; AGENCIA: 0001; "
        f"CONTA: 99999-9; CPF DO TITULAR: {CPF_VALIDO}"
    ),
    vendedor_cpf: str = CPF_VALIDO,
) -> str:
    """A full, well-formed synthetic Quadro Resumo — the `RÓTULO: valor`
    shape `DOCUMENT_PROMPT_FINANCIAMENTO` asks for."""
    return (
        "QUADRO RESUMO\n"
        "BANCO: ITAU UNIBANCO\n"
        "NUMERO DO CONTRATO: 12345-6\n"
        f"{compra_venda}\n"
        "VALOR DE AVALIACAO: R$ 520.000,00\n"
        f"{financiado}\n"
        f"{fgts}\n"
        f"{recursos_proprios}\n"
        f"{prazo}\n"
        "TAXA NOMINAL: 9,5%\n"
        "TAXA EFETIVA: 9,9%\n"
        "SISTEMA DE AMORTIZACAO: SAC\n"
        f"COMPRADOR: Fulano de Tal - CPF: {CPF_VALIDO}\n"
        f"VENDEDOR: Ciclano da Silva - CPF: {vendedor_cpf}\n"
        f"{conta}\n"
    )


class TestFactoryAndProtocol:
    def test_contrato_default_is_the_fake(self):
        assert isinstance(
            make_contrato_financiamento_extractor(), FakeContratoFinanciamentoExtractor
        )

    def test_proposta_default_is_the_fake(self):
        assert isinstance(
            make_proposta_financiamento_extractor(), FakePropostaFinanciamentoExtractor
        )

    def test_contrato_real_selects_the_ladder(self):
        assert isinstance(
            make_contrato_financiamento_extractor(real=True),
            LadderContratoFinanciamentoExtractor,
        )

    def test_proposta_real_selects_the_ladder(self):
        assert isinstance(
            make_proposta_financiamento_extractor(real=True),
            LadderPropostaFinanciamentoExtractor,
        )

    def test_every_adapter_satisfies_the_protocol(self):
        assert isinstance(FakeContratoFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)
        assert isinstance(FakePropostaFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)
        assert isinstance(LadderContratoFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)
        assert isinstance(LadderPropostaFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)


class TestFullParse:
    def test_every_field(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato")
        assert f.documento == "contrato"
        assert f.banco_nome == "Itaú Unibanco S.A."
        assert f.banco_codigo == "341"
        assert f.numero_contrato == "12345-6"
        assert f.valor_compra_venda == Decimal("500000.00")
        assert f.valor_avaliacao == Decimal("520000.00")
        assert f.valor_financiado == Decimal("400000.00")
        assert f.valor_fgts == Decimal("20000.00")
        assert f.valor_recursos_proprios == Decimal("80000.00")
        assert f.prazo_meses == 360
        assert f.taxa_nominal_aa == Decimal("9.5")
        assert f.taxa_efetiva_aa == Decimal("9.9")
        assert f.sistema_amortizacao == "SAC"
        assert len(f.compradores) == 1 and f.compradores[0].cpf_valido is True
        assert len(f.vendedores) == 1 and f.vendedores[0].cpf_valido is True
        assert f.quadro_encontrado is True
        assert f.error is None

    def test_conta_credito_vendedor_is_structured(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato")
        conta = f.conta_credito_vendedor
        assert conta is not None
        assert conta.banco_nome == "Itaú Unibanco S.A."
        assert conta.banco_codigo == "341"
        assert conta.agencia == "0001"
        assert conta.conta == "99999-9"
        assert conta.titular_cpf == CPF_VALIDO
        assert conta.titular_cpf_valido is True

    def test_conta_credito_vendedor_absent_is_none(self):
        f = parse_financiamento_imobiliario(
            _quadro(conta="").replace("\n\n", "\n"), TextSource.TEXT_LAYER, "contrato"
        )
        assert f.conta_credito_vendedor is None


class TestQuadroEncontrado:
    def test_anchor_missing_is_not_found(self):
        texto = _quadro().replace("QUADRO RESUMO\n", "")
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is False

    def test_anchor_alone_with_fewer_than_three_fields_is_not_found(self):
        texto = (
            "QUADRO RESUMO\n"
            "VALOR DE COMPRA E VENDA: R$ 500.000,00\n"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is False

    def test_exactly_three_of_four_is_found(self):
        # compra_venda + financiado + prazo present; fgts/recursos_proprios
        # both absent — still 3 of 4.
        texto = (
            "QUADRO RESUMO\n"
            "VALOR DE COMPRA E VENDA: R$ 500.000,00\n"
            "VALOR FINANCIADO: R$ 400.000,00\n"
            "PRAZO: 360 meses\n"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is True

    def test_resumo_do_financiamento_is_also_an_anchor(self):
        texto = _quadro().replace("QUADRO RESUMO", "RESUMO DO FINANCIAMENTO")
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is True


#: An Itaú-shaped summary (P1/883, 2026-09-26) — numbered items, no "QUADRO
#: RESUMO" title, "CREDOR: ITAÚ UNIBANCO", and a financed-amount label that
#: CONTAINS the compra-e-venda one. Values invented; A+B+C sums to item 1.
_ITAU_QUADRO = (
    "INSTRUMENTO PARTICULAR DE VENDA E COMPRA DE BEM IMÓVEL, FINANCIAMENTO\n"
    "CREDOR: ITAÚ UNIBANCO S.A.\n"
    "3 - FINANCIAMENTO:\n"
    "A - Valor destinado ao pagamento do preço de venda do Imóvel: R$ 400.000,00\n"
    "B - Valor destinado ao pagamento de despesas: R$ 0,00\n"
    "C - Valor total do financiamento (saldo devedor): R$ 412.000,00\n"
    "1 - PREÇO DE VENDA DO IMÓVEL: Apartamento / Casa / Imóvel Comercial R$ 500.000,00\n"
    "Valor Total R$ 500.000,00\n"
    "A - Recursos próprios R$ 80.000,00\n"
    "B - Recursos do FGTS R$ 20.000,00\n"
    "C - Recursos do financiamento R$ 400.000,00\n"
    "4 - CONDIÇÕES DO FINANCIAMENTO:\n"
    "A - Taxa efetiva anual de juros: 11,50%\n"
    "D - Prazo de amortização (número de prestações): 360 meses\n"
    "E - Sistema de Amortização: SAC\n"
    "12 - PRAZO DE CARÊNCIA PARA EXPEDIÇÃO DE INTIMAÇÃO: 30 dias\n"
    "13 - VALOR DA AVALIAÇÃO REALIZADA E ATRIBUÍDA PARA FINS DE VENDA EM LEILÃO "
    "PÚBLICO: Apartamento descrito no item 1 acima R$ 520.000,00\n"
)


class TestItauQuadro:
    """P1/883 (2026-09-26): the label wording of the real Itaú contract."""

    def test_reads_every_money_field_and_the_sum_confers(self):
        f = parse_financiamento_imobiliario(_ITAU_QUADRO, TextSource.OCR, "contrato")
        assert f.error is None
        assert f.quadro_encontrado is True
        assert f.valor_compra_venda == Decimal("500000.00")
        assert f.valor_financiado == Decimal("400000.00")
        assert f.valor_fgts == Decimal("20000.00")
        assert f.valor_recursos_proprios == Decimal("80000.00")
        assert f.valor_avaliacao == Decimal("520000.00")
        assert "quadro_resumo_soma_divergente" not in (f.aviso or "")

    def test_preco_de_venda_inside_the_financed_label_is_not_compra_venda(self):
        """Item 3A ("Valor destinado ao pagamento do PREÇO DE VENDA DO
        IMÓVEL") is printed BEFORE item 1 here; the longer label of the
        other field owns that line."""
        f = parse_financiamento_imobiliario(_ITAU_QUADRO, TextSource.OCR, "contrato")
        assert f.rotulos["valor_compra_venda"] == "PRECO DE VENDA DO IMOVEL"
        assert f.valor_compra_venda != f.valor_financiado

    def test_saldo_devedor_is_not_the_financed_amount(self):
        texto = _ITAU_QUADRO.replace("C - Recursos do financiamento R$ 400.000,00\n", "")
        texto = texto.replace(
            "A - Valor destinado ao pagamento do preço de venda do Imóvel: R$ 400.000,00\n", ""
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.valor_financiado is None

    def test_credor_names_the_bank_not_unibanco_s_a(self):
        f = parse_financiamento_imobiliario(_ITAU_QUADRO, TextSource.OCR, "contrato")
        assert f.rotulos["banco_nome"] == "CREDOR"
        assert f.banco_codigo == "341"

    def test_prazo_is_amortizacao_not_the_intimacao_carencia(self):
        texto = _ITAU_QUADRO.replace(
            "12 - PRAZO DE CARÊNCIA PARA EXPEDIÇÃO DE INTIMAÇÃO: 30 dias\n", ""
        )
        texto = "12 - PRAZO DE CARÊNCIA PARA EXPEDIÇÃO DE INTIMAÇÃO: 30 dias\n" + texto
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.prazo_meses == 360


class TestDataDocumentoSynonymOrdering:
    """`data_documento`'s synonym tuple used to list the bare "DATA" FIRST
    — `_campo` tried synonyms in DECLARED order, so a coincidental "DATA"
    mention anywhere earlier in the document starved the real, specific
    "DATA DE EMISSAO"/"DATA DO CONTRATO" box further down (the identical
    class of bug `prazo_meses`'s bare "PRAZO" already needed fixing once).
    `caixa_rotulada.campo` tries synonyms longest-first regardless of this
    tuple's own declared order."""

    def test_a_coincidental_bare_data_mention_never_shadows_the_real_box(self):
        texto = (
            _quadro()
            + "\nO IMOVEL FOI ATUALIZADO NESTA DATA CONFORME LAUDO.\n"
            + "DATA DE EMISSAO: 15/03/2020\n"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.data_documento == date(2020, 3, 15)
        assert f.rotulos["data_documento"] == "DATA DE EMISSAO"


class TestFgtsSynonyms:
    """Other banks' Quadros print the FGTS box under different wording
    than Itaú's "RECURSOS DO FGTS" — see the module's own `_ROTULOS`
    comment."""

    def test_conta_vinculada_synonym_is_read(self):
        f = parse_financiamento_imobiliario(
            _quadro(fgts="RECURSOS DA CONTA VINCULADA DO FGTS: R$ 20.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert f.valor_fgts == Decimal("20000.00")

    def test_valor_da_conta_vinculada_synonym_is_read(self):
        f = parse_financiamento_imobiliario(
            _quadro(fgts="VALOR DA CONTA VINCULADA: R$ 20.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert f.valor_fgts == Decimal("20000.00")

    def test_bare_fgts_synonym_is_read_as_a_last_resort(self):
        f = parse_financiamento_imobiliario(
            _quadro(fgts="FGTS: R$ 20.000,00"), TextSource.OCR, "contrato"
        )
        assert f.valor_fgts == Decimal("20000.00")

    def test_bare_fgts_never_overrides_a_masked_recursos_do_fgts_box(self):
        """The bare "FGTS" is tried LAST (longest-synonym-first) — a
        masked "RECURSOS DO FGTS: [EM BRANCO]" box is recognised as
        MASKED (the specific, printed box), never silently overridden by
        the bare synonym matching the same text."""
        f = parse_financiamento_imobiliario(
            _quadro(fgts="RECURSOS DO FGTS: [EM BRANCO]"), TextSource.OCR, "contrato"
        )
        assert f.valor_fgts is None
        assert f.rotulos["valor_fgts"] == "RECURSOS DO FGTS"



class TestItauContaVendedor:
    """P1/883 (2026-09-27): Itaú prints the seller's account on the line
    AFTER "VALOR A SER LIBERADO AO VENDEDOR: R$ …", as `|`-separated
    sub-fields with the bank as a FEBRABAN code."""

    _ITEM_8 = (
        "8 - VALOR A SER LIBERADO AO VENDEDOR: R$ 400.000,00\n"
        f"Nome: FULANA DE TAL | CPF / CNPJ: {CPF_VALIDO} | Cód. Banco: 0033 | "
        "Agência: 1234- | Conta: 01000123-4 | Percentual: 100.00%\n"
        "9 - VALOR A SER LIBERADO AO COMPRADOR: R$ 0,00 | Cód. Banco: 341 | "
        "Agência: 9999 | Conta: 88888-8\n"
    )

    def test_reads_the_account_from_the_next_line(self):
        f = parse_financiamento_imobiliario(_ITAU_QUADRO + self._ITEM_8, TextSource.OCR, "contrato")
        c = f.conta_credito_vendedor
        assert c is not None
        assert c.banco_codigo == "033"
        assert c.banco_nome == "Banco Santander (Brasil) S.A."
        assert c.agencia == "1234"
        assert c.conta == "01000123-4"
        assert c.titular_cpf == CPF_VALIDO
        assert c.titular_cpf_valido is True

    def test_the_buyer_item_never_bleeds_into_the_seller_account(self):
        f = parse_financiamento_imobiliario(_ITAU_QUADRO + self._ITEM_8, TextSource.OCR, "contrato")
        assert f.conta_credito_vendedor.conta != "88888-8"

    def test_one_sub_field_per_line_shape(self):
        """The more common flattening of Itaú's table (883, 3 of 3 runs):
        one `Rótulo: valor` line per column, then a clause paragraph."""
        texto = _ITAU_QUADRO + (
            "8 - VALOR A SER LIBERADO AO VENDEDOR: R$ 400.000,00\n\n"
            "Nome: FULANA DE TAL\n"
            f"CPF / CNPJ: {CPF_VALIDO}\n"
            "Cód. Banco: 033\n"
            "Agência: 1234-\n"
            "Conta: 01000123-4\n"
            "Percentual: 100.00%\n"
            "9 - VALOR A SER LIBERADO AO COMPRADOR: R$ 0,00\n"
            "Cód. Banco: 341\nAgência: 9999\nConta: 88888-8\n"
        )
        c = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato").conta_credito_vendedor
        assert (c.banco_codigo, c.agencia, c.conta) == ("033", "1234", "01000123-4")
        assert c.titular_cpf == CPF_VALIDO

    def test_a_clause_after_the_box_ends_it(self):
        texto = _ITAU_QUADRO + (
            "8 - VALOR A SER LIBERADO AO VENDEDOR: R$ 400.000,00\n"
            "O Itaú pagará o valor indicado no item 8 por meio de crédito na conta.\n"
            "Conta: 77777-7\n"
        )
        c = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato").conta_credito_vendedor
        assert c.conta is None

    def test_an_unknown_bank_code_is_not_guessed(self):
        texto = _ITAU_QUADRO + self._ITEM_8.replace("Cód. Banco: 0033", "Cód. Banco: 0999")
        c = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato").conta_credito_vendedor
        assert c.banco_codigo is None
        assert c.banco_nome is None
        assert c.conta == "01000123-4"

    def test_an_unknown_bank_code_is_surfaced_not_silent(self):
        texto = _ITAU_QUADRO + self._ITEM_8.replace("Cód. Banco: 0033", "Cód. Banco: 1033")
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.conta_credito_vendedor.banco_impresso == "1033"
        assert "conta_credito_vendedor_banco_nao_reconhecido" in (f.aviso or "")

    def test_a_known_bank_carries_no_banco_impresso(self):
        f = parse_financiamento_imobiliario(_ITAU_QUADRO + self._ITEM_8, TextSource.OCR, "contrato")
        assert f.conta_credito_vendedor.banco_impresso is None
        assert "banco_nao_reconhecido" not in (f.aviso or "")

    def test_amount_line_alone_yields_an_empty_account_not_a_crash(self):
        texto = _ITAU_QUADRO + "8 - VALOR A SER LIBERADO AO VENDEDOR: R$ 400.000,00\n"
        c = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato").conta_credito_vendedor
        assert c is not None
        assert (c.agencia, c.conta, c.titular_cpf) == (None, None, None)

    def test_the_semicolon_box_shape_still_reads(self):
        c = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato").conta_credito_vendedor
        assert c.banco_codigo == "341"
        assert c.agencia == "0001"
        assert c.conta == "99999-9"



class TestItauProposta:
    """P1/883 (2026-09-28): the Itaú approval message (a phone screenshot)."""

    _MSG = (
        "Oi, FULANA! Seu Crédito Imobiliário foi aprovado! Proposta: 12345678.\n"
        "Válido até: 2026-10-30\n"
        "Valor do imóvel: R$ 500.000,00\n"
        "Valor do crédito: R$ 400.000,00\n"
        "Prazo: 30 anos (360 meses)\n"
        "Primeira parcela: R$ 4.321,00\n"
    )

    def test_valor_do_credito_is_the_financed_amount(self):
        f = parse_financiamento_imobiliario(self._MSG, TextSource.OCR, "proposta")
        assert f.valor_compra_venda == Decimal("500000.00")
        assert f.valor_financiado == Decimal("400000.00")

    def test_prazo_in_years_and_months_is_months(self):
        f = parse_financiamento_imobiliario(self._MSG, TextSource.OCR, "proposta")
        assert f.prazo_meses == 360

    def test_prazo_in_years_only_converts(self):
        texto = self._MSG.replace("Prazo: 30 anos (360 meses)", "Prazo: 30 anos")
        assert parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta").prazo_meses == 360

    def test_bare_prazo_number_is_months(self):
        texto = self._MSG.replace("Prazo: 30 anos (360 meses)", "Prazo: 360")
        assert parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta").prazo_meses == 360


class TestDpsTripwire:
    def test_dps_marker_short_circuits_with_no_fields(self):
        texto = (
            "DECLARACAO PESSOAL DE SAUDE\nO proponente declara que...\n"
            "PESO: ... ALTURA: ...\nJa teve alguma DOENCA? SIM ( ) NAO ( )"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error == "documento_sensivel_dps"
        assert f.valor_compra_venda is None
        assert f.compradores == ()
        assert f.confiancas == {}
        assert f.rotulos == {}

    def test_dps_questionnaire_wins_even_inside_a_full_quadro(self):
        texto = (
            "DECLARACAO PESSOAL DE SAUDE\nPESO: ... ALTURA: ...\n"
            "Esta em TRATAMENTO medico? SIM ( ) NAO ( )\n" + _quadro()
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error == "documento_sensivel_dps"
        assert f.quadro_encontrado is False

    def test_a_bare_dps_mention_in_an_insurance_clause_is_not_a_dps(self):
        """P1/883 (Itaú, 2026-09-25): a real financing contract NAMES the DPS
        in its MIP insurance clause. That mention carries no health data and
        must not refuse the whole contract."""
        texto = (
            _quadro() + "\nCLAUSULA DO SEGURO MIP: o DEVEDOR preencheu a "
            "Declaracao Pessoal de Saude exigida pela seguradora.\n"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error is None
        assert f.quadro_encontrado is True

    def test_dps_variant_questionario_de_saude(self):
        texto = "QUESTIONARIO DE SAUDE\nPergunta 1: ..."
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error == "documento_sensivel_dps"

    def test_mention_and_insurance_words_on_different_pages_is_not_a_dps(self):
        """P1/883 (Itaú, 2026-09-26): page 7 names the DPS in the MIP clause,
        page 8's insurance text says "doença"/"tratamento". Joined, the 5–8
        window looked like a questionnaire that exists on no page."""
        pagina7 = _quadro() + "\nSEGURO MIP: o DEVEDOR preencheu a Declaracao Pessoal de Saude."
        pagina8 = "A seguradora nao cobre DOENCA preexistente nem TRATAMENTO em curso."
        f = parse_financiamento_imobiliario(
            pagina7 + "\n\n" + pagina8, TextSource.OCR, "contrato", paginas=[pagina7, pagina8]
        )
        assert f.error is None
        assert f.quadro_encontrado is True

    def test_mention_and_questionnaire_on_the_same_page_still_refuses(self):
        pagina = "DECLARACAO PESSOAL DE SAUDE\nPESO: ... ALTURA: ...\nDOENCA? SIM ( ) NAO ( )"
        f = parse_financiamento_imobiliario(
            _quadro() + "\n\n" + pagina, TextSource.OCR, "contrato", paginas=[_quadro(), pagina]
        )
        assert f.error == "documento_sensivel_dps"

    def test_a_form_title_on_any_page_still_refuses(self):
        f = parse_financiamento_imobiliario(
            _quadro() + "\n\nQUESTIONARIO DE SAUDE",
            TextSource.OCR,
            "contrato",
            paginas=[_quadro(), "QUESTIONARIO DE SAUDE"],
        )
        assert f.error == "documento_sensivel_dps"


class TestFabricationGuards:
    def test_vision_never_alta_on_money_fields(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.OCR, "contrato")
        for campo in (
            "valor_compra_venda", "valor_financiado", "valor_fgts",
            "valor_recursos_proprios",
        ):
            assert f.confiancas[campo] is not ExtractionConfidence.ALTA

    def test_quadro_sum_agreeing_promotes_to_media_even_without_extenso(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.OCR, "contrato")
        # None of this fixture's money lines carry a parenthetical extenso,
        # yet the Quadro's own arithmetic agrees (400k + 20k + 80k = 500k).
        assert f.confiancas["valor_financiado"] is ExtractionConfidence.MEDIA

    def test_quadro_sum_mismatch_caps_every_money_field_at_baixa_no_nulling(self):
        f = parse_financiamento_imobiliario(
            _quadro(recursos_proprios="RECURSOS PROPRIOS: R$ 50.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert "quadro_resumo_soma_divergente" in (f.aviso or "")
        assert f.valor_financiado == Decimal("400000.00")  # NOT nulled
        assert f.confiancas["valor_financiado"] is ExtractionConfidence.BAIXA
        assert f.confiancas["valor_recursos_proprios"] is ExtractionConfidence.BAIXA

    def test_fgts_absent_and_partial_sum_mismatch_raises_the_partial_aviso(self):
        """The FULL sum check (`quadro_resumo_soma_divergente`) only ever
        runs with all four legs present — when FGTS itself was never read,
        financiado + recursos próprios alone already not adding up to
        compra e venda is exactly what a genuinely-unread FGTS leg would
        explain."""
        f = parse_financiamento_imobiliario(
            _quadro(fgts=""),  # financiado 400k + próprios 80k != compra_venda 500k
            TextSource.OCR,
            "contrato",
        )
        assert f.valor_fgts is None
        assert "quadro_resumo_fgts_ausente" in (f.aviso or "")
        assert "quadro_resumo_soma_divergente" not in (f.aviso or "")
        assert f.valor_financiado == Decimal("400000.00")  # never nulled

    def test_fgts_absent_but_partial_sum_matching_does_not_raise_the_aviso(self):
        f = parse_financiamento_imobiliario(
            _quadro(fgts="", recursos_proprios="RECURSOS PROPRIOS: R$ 100.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert f.valor_fgts is None
        assert "quadro_resumo_fgts_ausente" not in (f.aviso or "")

    def test_fgts_present_never_raises_the_partial_aviso(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.OCR, "contrato")
        assert "quadro_resumo_fgts_ausente" not in (f.aviso or "")

    def test_financiado_over_compra_venda_is_nulled(self):
        f = parse_financiamento_imobiliario(
            _quadro(financiado="VALOR FINANCIADO: R$ 900.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert f.valor_financiado is None
        assert "valor_financiado_maior_que_compra_venda" in (f.aviso or "")
        assert f.confiancas["valor_financiado"] is ExtractionConfidence.NENHUMA

    def test_financiado_over_avaliacao_is_nulled(self):
        texto = _quadro().replace(
            "VALOR DE AVALIACAO: R$ 520.000,00", "VALOR DE AVALIACAO: R$ 350.000,00"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.valor_financiado is None
        assert "valor_financiado_maior_que_avaliacao" in (f.aviso or "")

    def test_bad_cpf_check_digit_is_never_corrected(self):
        f = parse_financiamento_imobiliario(
            _quadro(vendedor_cpf=CPF_INVALIDO), TextSource.OCR, "contrato"
        )
        assert f.vendedores[0].cpf == CPF_INVALIDO
        assert f.vendedores[0].cpf_valido is False
        assert "vendedores_cpf_digito_invalido" in (f.aviso or "")

    def test_text_layer_reaches_alta_on_money_fields(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato")
        assert f.confiancas["valor_compra_venda"] is ExtractionConfidence.ALTA


class TestContratoLeEveryPage:
    """Owner mandate 2026-09-28: every page read, page by page, in ONE
    `transcribe()` call (`paginas=None`) — no two-pass window, no per-window
    page cap. A fake, injected transcriber stands in for
    `documents.transcription`'s real ladder; the page-by-page vision-call
    mechanics themselves are covered end-to-end in
    `test_transcription_paginas.py`."""

    class _FakeTranscriber:
        def __init__(self, transcricao: Transcription):
            self._transcricao = transcricao
            self.chamadas: list[object] = []

        async def transcribe(self, content, *, mimetype=None, filename=None, force_vision=False, paginas=None):
            self.chamadas.append(paginas)
            return self._transcricao

    @pytest.mark.asyncio
    async def test_a_single_call_reads_every_page_paginas_is_none(self):
        t = self._FakeTranscriber(
            Transcription(
                pages=(TranscribedPage(number=1, text=_quadro(), source=TextSource.OCR),),
                num_paginas=25,
            )
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert t.chamadas == [None]
        assert r.quadro_encontrado is True
        assert r.paginas_lidas == (1,)
        assert r.error is None

    @pytest.mark.asyncio
    async def test_a_quadro_past_the_old_eight_page_hard_cap_is_found(self):
        """The superseded two-pass window never read past page 8 — this
        Quadro sits on page 10 of a 25-page contract."""
        paginas = tuple(
            TranscribedPage(number=n, text="nada aqui" if n != 10 else _quadro(), source=TextSource.OCR)
            for n in range(1, 11)
        )
        t = self._FakeTranscriber(Transcription(pages=paginas, num_paginas=25))
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert r.quadro_encontrado is True
        assert r.paginas_lidas == tuple(range(1, 11))
        assert r.error is None

    @pytest.mark.asyncio
    async def test_not_found_anywhere_is_the_named_error(self):
        paginas = tuple(
            TranscribedPage(number=n, text="nada aqui", source=TextSource.OCR)
            for n in range(1, 9)
        )
        t = self._FakeTranscriber(Transcription(pages=paginas, num_paginas=25))
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert r.error == "quadro_resumo_nao_encontrado"
        assert r.paginas_lidas == tuple(range(1, 9))

    @pytest.mark.asyncio
    async def test_transcriber_failure_is_surfaced_not_swallowed(self):
        class _FailingTranscriber:
            async def transcribe(self, *a, **kw):
                return Transcription(error="missing_credentials", error_message="no key")

        ext = LadderContratoFinanciamentoExtractor(transcriber=_FailingTranscriber())
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert r.error == "missing_credentials"
        assert r.quadro_encontrado is False

    @pytest.mark.asyncio
    async def test_dps_short_circuits_with_no_further_reading(self):
        t = self._FakeTranscriber(
            Transcription(
                pages=(
                    TranscribedPage(
                        number=1,
                        text=(
                            "DECLARACAO PESSOAL DE SAUDE\nPESO: ... ALTURA: ...\n"
                            "CIRURGIA? SIM ( ) NAO ( )"
                        ),
                        source=TextSource.OCR,
                    ),
                ),
                num_paginas=25,
            )
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert len(t.chamadas) == 1
        assert r.error == "documento_sensivel_dps"

    @pytest.mark.asyncio
    async def test_dps_is_judged_per_page_across_the_whole_document(self):
        """P1/883: the extractor hands the parser its pages, so a mention on
        page 7 and insurance words on page 8 do not refuse the contract."""
        paginas = (
            TranscribedPage(number=1, text="nada", source=TextSource.OCR),
            TranscribedPage(number=2, text="nada", source=TextSource.OCR),
            TranscribedPage(
                number=7,
                text=_ITAU_QUADRO
                + "SEGURO MIP: a Declaracao Pessoal de Saude do DEVEDOR.",
                source=TextSource.OCR,
            ),
            TranscribedPage(
                number=8,
                text="Nao cobre DOENCA preexistente nem TRATAMENTO em curso.",
                source=TextSource.OCR,
            ),
        )
        t = self._FakeTranscriber(Transcription(pages=paginas, num_paginas=25))
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert r.error is None
        assert r.quadro_encontrado is True
        assert r.valor_financiado == Decimal("400000.00")


class TestEmptyAndErrors:
    @pytest.mark.asyncio
    async def test_fake_contrato_empty_document_errors(self):
        result = await FakeContratoFinanciamentoExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_fake_proposta_empty_document_errors(self):
        result = await FakePropostaFinanciamentoExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_ladder_contrato_empty_document_errors(self):
        result = await LadderContratoFinanciamentoExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_fake_contrato_default_reading_is_synthetic_and_consistent(self):
        result = await FakeContratoFinanciamentoExtractor().extract(b"bytes")
        assert result.error is None
        assert result.documento == "contrato"
        assert (
            result.valor_financiado + result.valor_fgts + result.valor_recursos_proprios
            == result.valor_compra_venda
        )

    @pytest.mark.asyncio
    async def test_fake_proposta_default_reading_is_synthetic(self):
        result = await FakePropostaFinanciamentoExtractor().extract(b"bytes")
        assert result.error is None
        assert result.documento == "proposta"

    def test_no_labels_found_is_all_nenhuma(self):
        f = parse_financiamento_imobiliario("nada reconhecivel aqui", TextSource.OCR, "contrato")
        assert f.valor_compra_venda is None
        assert f.error is None
        assert all(c is ExtractionConfidence.NENHUMA for c in f.confiancas.values())


# ─── the proponente(s) a bank PROPOSTA letter names (2026-10-03) ─────────
# Shapes measured on 11 real proposals; every name/number here is invented.


class TestPropostaProponentes:
    def test_itau_greeting_names_the_proponente_without_a_cpf(self) -> None:
        texto = (
            "Carta de Crédito\nN. Proposta: 12345678\n"
            "Oi, Fulana Sintética de Teste. Sua proposta foi aprovada e agora "
            "você pode conferir as condições do crédito:\n"
            "Valor do Imóvel: R$ 640.000,00\n"
        )
        r = parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta")
        assert r.nomes_proponentes == ("FULANA SINTETICA DE TESTE",)
        assert r.compradores == ()

    def test_greeting_without_a_full_stop(self) -> None:
        texto = "Oi, Fulana Sintetica Sua proposta foi aprovada e agora ...\n"
        r = parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta")
        assert r.nomes_proponentes == ("FULANA SINTETICA",)

    def test_name_and_cpf_on_separate_label_lines_are_paired(self) -> None:
        texto = (
            "Prezado(s) Cliente(s):\n"
            "1) Nome do (s) Comprador (es): FULANA SINTETICA DE TESTE\n"
            f"2) CPF(s): {CPF_VALIDO}\n"
        )
        r = parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta")
        assert len(r.compradores) == 1
        assert r.compradores[0].nome == "FULANA SINTETICA DE TESTE"
        assert r.compradores[0].cpf == CPF_VALIDO
        assert r.compradores[0].cpf_valido is True
        assert r.nomes_proponentes == ("FULANA SINTETICA DE TESTE",)

    def test_two_names_joined_by_e_split_only_to_match_two_cpfs(self) -> None:
        texto = (
            "Nome dos Compradores: FULANO SINTETICO E BELTRANA SINTETICA\n"
            f"CPF(s): {CPF_VALIDO}; 529.982.247-25\n"
        )
        r = parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta")
        assert [p.nome for p in r.compradores] == ["FULANO SINTETICO", "BELTRANA SINTETICA"]

    def test_masked_cpf_leaves_the_name_unpaired(self) -> None:
        texto = (
            "Nome do (s) Comprador (es): FULANA SINTETICA DE TESTE\n"
            "CPF(s): ***.954.238-**\n"
        )
        r = parse_financiamento_imobiliario(texto, TextSource.OCR, "proposta")
        assert r.compradores == ()
        assert r.nomes_proponentes == ("FULANA SINTETICA DE TESTE",)
