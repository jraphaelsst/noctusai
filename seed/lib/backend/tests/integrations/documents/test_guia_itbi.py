"""`guia_itbi` — a municipal Guia de ITBI (boxed RÓTULO: valor layout) →
typed fields. All names, CNPJs, CPFs and values in this file are invented.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeGuiaItbiExtractor,
    GuiaItbiExtractor,
    GuiaItbiFields,
    TextSource,
    make_guia_itbi_extractor,
    parse_guia_itbi,
)
from noctusai_lib.integrations.documents.guia_itbi import LadderGuiaItbiExtractor

CPF_VALIDO = "412.954.238-98"
CPF_INVALIDO = "412.954.238-99"


def _guia(
    *,
    valor_transacao: str = "VALOR DA TRANSACAO: R$ 350.000,00 (trezentos e "
    "cinquenta mil reais)",
    aliquota: str = "ALIQUOTA: 2%",
    valor_itbi: str = "VALOR DO ITBI: R$ 7.000,00",
    comprador_cpf: str = CPF_VALIDO,
    vendedor: str = f"VENDEDOR: Ciclano da Silva - CPF: {CPF_VALIDO}",
) -> str:
    """A full, well-formed synthetic Guia de ITBI transcription — the
    `RÓTULO: valor` shape `DOCUMENT_PROMPT_GUIA_ITBI` asks for."""
    return (
        f"{valor_transacao}\n"
        "VALOR VENAL: R$ 300.000,00\n"
        "BASE DE CALCULO: R$ 350.000,00\n"
        f"{aliquota}\n"
        f"{valor_itbi}\n"
        "DATA DE VENCIMENTO: 31/12/2026\n"
        "INSCRICAO IMOBILIARIA: 99.999.999-9\n"
        "MATRICULA: 99.999\n"
        f"COMPRADOR: Fulano de Tal - CPF: {comprador_cpf}\n"
        f"{vendedor}\n"
        "MUNICIPIO: SAO PAULO\n"
    )


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_guia_itbi_extractor(), FakeGuiaItbiExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(make_guia_itbi_extractor(real=True), LadderGuiaItbiExtractor)

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeGuiaItbiExtractor(), GuiaItbiExtractor)
        assert isinstance(LadderGuiaItbiExtractor(), GuiaItbiExtractor)


class TestFullParse:
    def test_every_field(self):
        f = parse_guia_itbi(_guia(), TextSource.TEXT_LAYER)
        assert f.valor_transacao == Decimal("350000.00")
        assert f.valor_venal == Decimal("300000.00")
        assert f.base_calculo == Decimal("350000.00")
        assert f.valor_financiado_sfh is None
        assert f.aliquota_pct == Decimal("2")
        assert f.valor_itbi == Decimal("7000.00")
        assert f.vencimento == date(2026, 12, 31)
        assert f.inscricao_imobiliaria == "99.999.999-9"
        assert f.numero_matricula == "99.999"
        assert f.municipio == "SAO PAULO"
        assert f.error is None
        assert len(f.compradores) == 1
        assert f.compradores[0].cpf == CPF_VALIDO
        assert f.compradores[0].cpf_valido is True
        assert len(f.vendedores) == 1
        assert f.vendedores[0].cpf_valido is True

    def test_text_layer_source_reaches_alta_on_money_fields(self):
        f = parse_guia_itbi(_guia(), TextSource.TEXT_LAYER)
        assert f.confiancas["valor_transacao"] is ExtractionConfidence.ALTA

    def test_no_r_prefix_still_parses(self):
        f = parse_guia_itbi(
            _guia(valor_transacao="VALOR DA TRANSACAO: 350.000,00"),
            TextSource.TEXT_LAYER,
        )
        assert f.valor_transacao == Decimal("350000.00")


class TestFabricationGuards:
    def test_ilegivel_is_none(self):
        f = parse_guia_itbi(
            _guia(valor_transacao="VALOR DA TRANSACAO: [ILEGÍVEL]"),
            TextSource.OCR,
        )
        assert f.valor_transacao is None
        assert f.confiancas["valor_transacao"] is ExtractionConfidence.NENHUMA

    def test_em_branco_is_none(self):
        f = parse_guia_itbi(
            _guia(valor_transacao="VALOR DA TRANSACAO: [EM BRANCO]"),
            TextSource.OCR,
        )
        assert f.valor_transacao is None

    def test_vision_never_alta_on_money_fields(self):
        f = parse_guia_itbi(_guia(), TextSource.OCR)
        for campo in (
            "valor_transacao", "valor_venal", "base_calculo", "valor_itbi",
        ):
            assert f.confiancas[campo] is not ExtractionConfidence.ALTA

    def test_vision_with_agreeing_extenso_reaches_media(self):
        f = parse_guia_itbi(_guia(), TextSource.OCR)
        # `valor_transacao`'s fixture line carries an agreeing extenso.
        assert f.confiancas["valor_transacao"] is ExtractionConfidence.MEDIA

    def test_vision_without_extenso_stays_baixa(self):
        f = parse_guia_itbi(_guia(), TextSource.OCR)
        # `valor_venal` never carries an extenso in this fixture.
        assert f.confiancas["valor_venal"] is ExtractionConfidence.BAIXA

    def test_aliquota_out_of_range_is_nulled(self):
        f = parse_guia_itbi(_guia(aliquota="ALIQUOTA: 15%"), TextSource.OCR)
        assert f.aliquota_pct is None
        assert "aliquota_fora_da_faixa" in (f.aviso or "")

    def test_aliquota_zero_is_out_of_range(self):
        f = parse_guia_itbi(_guia(aliquota="ALIQUOTA: 0%"), TextSource.OCR)
        assert f.aliquota_pct is None

    def test_itbi_sum_mismatch_nulls_valor_itbi_with_aviso(self):
        f = parse_guia_itbi(
            _guia(valor_itbi="VALOR DO ITBI: R$ 9.999,00"), TextSource.OCR
        )
        assert f.valor_itbi is None
        assert "itbi_soma_divergente" in (f.aviso or "")
        assert f.confiancas["valor_itbi"] is ExtractionConfidence.NENHUMA

    def test_itbi_sum_agreeing_keeps_the_value(self):
        f = parse_guia_itbi(_guia(), TextSource.TEXT_LAYER)
        assert f.valor_itbi == Decimal("7000.00")
        assert "itbi_soma_divergente" not in (f.aviso or "")

    def test_bad_cpf_check_digit_is_never_corrected(self):
        f = parse_guia_itbi(_guia(comprador_cpf=CPF_INVALIDO), TextSource.OCR)
        assert f.compradores[0].cpf == CPF_INVALIDO  # kept, not corrected
        assert f.compradores[0].cpf_valido is False
        assert f.confiancas["compradores"] is ExtractionConfidence.BAIXA
        assert "compradores_cpf_digito_invalido" in (f.aviso or "")

    def test_masked_vendedor_yields_no_pessoa(self):
        f = parse_guia_itbi(_guia(vendedor="VENDEDOR: [ILEGÍVEL]"), TextSource.OCR)
        assert f.vendedores == ()
        assert f.confiancas["vendedores"] is ExtractionConfidence.NENHUMA


class TestEmptyAndErrors:
    @pytest.mark.asyncio
    async def test_fake_empty_document_errors(self):
        result = await FakeGuiaItbiExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_fake_default_reading_is_synthetic_and_consistent(self):
        result = await FakeGuiaItbiExtractor().extract(b"bytes")
        assert result.error is None
        assert result.valor_itbi == (
            result.base_calculo * result.aliquota_pct / Decimal("100")
        ).quantize(Decimal("0.01"))

    def test_no_labels_found_is_all_nenhuma(self):
        f = parse_guia_itbi("nada reconhecivel aqui", TextSource.OCR)
        assert f.valor_transacao is None
        assert all(c is ExtractionConfidence.NENHUMA for c in f.confiancas.values())
        assert f.error is None


class TestLayoutMedido883:
    """Label variants measured on a real guide (deal 883, 2026-09-25). Values
    here are invented; only the label SHAPES come from the real document."""

    TEXTO = (
        "Imposto sobre Transmissao de Bens Imoveis: ITBI\n"
        "Valor do Instrumento (a vista): 100.000,00\n"
        "Valor Financiado: 400.000,00\n"
        "Base Calculo: 500.000,00\n"
        "(=)Vr. Imposto R$: 10.000,00\n"
        "(=)Total R$: 10.000,00\n"
    )

    def test_base_calculo_without_de(self):
        from decimal import Decimal
        f = parse_guia_itbi(self.TEXTO, TextSource.OCR)
        assert f.base_calculo == Decimal("500000.00")

    def test_bare_valor_financiado(self):
        from decimal import Decimal
        f = parse_guia_itbi(self.TEXTO, TextSource.OCR)
        assert f.valor_financiado_sfh == Decimal("400000.00")

    def test_vr_imposto_abbreviation(self):
        from decimal import Decimal
        f = parse_guia_itbi(self.TEXTO, TextSource.OCR)
        assert f.valor_itbi == Decimal("10000.00")

    def test_valor_do_instrumento_a_vista_is_not_the_transaction_value(self):
        """It is only the up-front portion (à vista + financiado = total)."""
        f = parse_guia_itbi(self.TEXTO, TextSource.OCR)
        assert f.valor_transacao is None
