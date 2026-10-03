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
        """It is only the up-front portion (à vista + financiado = total):
        never read AS the transaction value, only summed into it."""
        from decimal import Decimal
        f = parse_guia_itbi(self.TEXTO, TextSource.OCR)
        assert f.valor_a_vista == Decimal("100000.00")
        assert f.valor_transacao != f.valor_a_vista
        assert f.valor_transacao == Decimal("500000.00")


class TestSharedBoxMatcherGuard:
    """`guia_itbi._campo` never had the other-field-longer-label guard
    `financiamento_imobiliario._campo` carried — it now delegates to the
    shared `caixa_rotulada.campo`, which has it. No município's REAL
    label set measured so far actually needs it (no two `_ROTULOS` fields
    here have a substring relationship today), so this exercises the
    module's own `_campo` directly against a synthetic vocabulary shaped
    like the 883/Itaú one that DID need it — proving the guard is wired
    through this module too, not just present in the shared module's own
    tests."""

    def test_the_guard_is_wired_through_guia_itbi_s_own_campo(self):
        from noctusai_lib.integrations.documents.guia_itbi import _campo

        linha = "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL: R$ 400.000,00"
        todos = (
            "PRECO DE VENDA DO IMOVEL",
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",
        )
        valor, achado, mascarado = _campo(
            [linha], ("PRECO DE VENDA DO IMOVEL",), todos_rotulos=todos
        )
        assert (valor, achado, mascarado) == (None, None, False)


# --- a guide that prints the price only as its two parts (P1/883, 2026-09-28) --

from decimal import Decimal as _D  # noqa: E402

from noctusai_lib.integrations.documents.guia_itbi import parse_guia_itbi as _parse  # noqa: E402
from noctusai_lib.integrations.documents.types import (  # noqa: E402
    ExtractionConfidence as _C,
    TextSource as _S,
)

#: Carapicuíba's layout (invented values): "Valor do Instrumento (à vista)" +
#: "Valor Financiado", and no transaction-value box anywhere.
GUIA_PARTES = """
Imposto sobre Transmissão de Bens Imóveis e de Direitos: ITBI
Inscrição Cadastral: 12345.67.89.0001.00.000
Transação: COMPRA E VENDA
Valor do Instrumento (à vista): 200.000,00
Valor Financiado: 800.000,00
Base Cálculo: 1.000.000,00
(=)Vr. Imposto R$: 20.000,00
"""


class TestValorTransacaoDerivadoDasPartes:
    def test_sum_of_the_parts_is_the_transaction_value(self) -> None:
        r = _parse(GUIA_PARTES, _S.OCR)
        assert r.valor_a_vista == _D("200000.00")
        assert r.valor_financiado_sfh == _D("800000.00")
        assert r.valor_transacao == _D("1000000.00")
        assert "valor_transacao_derivado" in (r.aviso or "")

    def test_corroborated_by_the_base_is_media_never_alta(self) -> None:
        r = _parse(GUIA_PARTES, _S.TEXT_LAYER)
        assert r.confiancas["valor_transacao"] is _C.MEDIA

    def test_a_base_that_disagrees_leaves_it_baixa(self) -> None:
        r = _parse(GUIA_PARTES.replace("1.000.000,00", "1.200.000,00"), _S.OCR)
        assert r.valor_transacao == _D("1000000.00")
        assert r.confiancas["valor_transacao"] is _C.BAIXA

    def test_one_part_alone_is_not_a_price(self) -> None:
        r = _parse(GUIA_PARTES.replace("Valor Financiado: 800.000,00\n", ""), _S.OCR)
        assert r.valor_transacao is None
        assert "valor_transacao_derivado" not in (r.aviso or "")

    def test_a_printed_transaction_value_always_wins(self) -> None:
        r = _parse(GUIA_PARTES + "Valor da Transação: 1.050.000,00\n", _S.OCR)
        assert r.valor_transacao == _D("1050000.00")
        assert "valor_transacao_derivado" not in (r.aviso or "")


# ─── text-layer LAYOUT shapes measured on real guides (2026-10-03) ────────
# Every text-layer guide in the corpus read `sem_dados` before this: 0/6.
# The fixtures below copy the real LAYOUT only — every name, number and
# value is invented.

#: Cotia's text layer dumps the boxed row "Área do Terreno | Fração Ideal |
#: Área Const. | Valor Venal IPTU | Valor do Instrumento" as a label column
#: followed by a value column. The line after the instrumento label is an
#: AREA ("412,50"), which a next-line reader takes for the price.
_COTIA_COLUNAR = (
    "Imposto Sobre Transmissão de Bens Imóveis - Inter-Vivos-ITBI\n"
    "1 - Contribuinte(Comprador)\n"
    "Natureza da Transação\n"
    "12345.67.89.0001.00.000\n"
    "54321\n"
    "X\n"
    "Compra e Venda\n"
    "Área do Terreno\n"
    "Fração Ideal\n"
    "Área Const.\n"
    "Valor Venal IPTU\n"
    "Valor do Instrumento (Valor Venal de Mercado)\n"
    "412,50\n"
    "1\n"
    "198,30\n"
    "R$ 287.654,32\n"
    "R$1.234.567,89\n"
    "Aviso\n"
    "Data de Vencimento\n"
)


class TestLayoutColunarCotia:
    def test_transaction_value_is_the_instrument_column_value(self) -> None:
        r = parse_guia_itbi(_COTIA_COLUNAR, TextSource.TEXT_LAYER)
        assert r.valor_transacao == Decimal("1234567.89")
        assert r.rotulos["valor_transacao"] == "VALOR DO INSTRUMENTO (VALOR VENAL DE MERCADO)"

    def test_venal_pairs_with_its_own_column_value_not_an_area(self) -> None:
        r = parse_guia_itbi(_COTIA_COLUNAR, TextSource.TEXT_LAYER)
        assert r.valor_venal == Decimal("287654.32")

    def test_instrument_with_market_gloss_is_not_the_cash_part(self) -> None:
        r = parse_guia_itbi(_COTIA_COLUNAR, TextSource.TEXT_LAYER)
        assert r.valor_a_vista is None

    def test_unequal_money_label_and_value_counts_is_none_never_a_guess(self) -> None:
        # One R$ amount for two money labels — ambiguous, so not paired.
        texto = _COTIA_COLUNAR.replace("R$ 287.654,32\n", "287.654,32\n")
        r = parse_guia_itbi(texto, TextSource.TEXT_LAYER)
        assert r.valor_transacao is None

    def test_vision_line_shape_of_the_same_guide(self) -> None:
        texto = (
            "VALOR VENAL IPTU: R$ 287.654,32\n"
            "VALOR DO INSTRUMENTO (VALOR VENAL DE MERCADO): R$ 1.234.567,89\n"
        )
        r = parse_guia_itbi(texto, TextSource.OCR)
        assert r.valor_transacao == Decimal("1234567.89")
        assert r.valor_venal == Decimal("287654.32")


#: Embu das Artes prints the facts as prose in an observations box; the
#: text layer wraps it where the page width falls — through the label.
_EMBU_PROSA = (
    "PREFEITURA DA ESTÂNCIA TURÍSTICA DE EMBU DAS ARTES\n"
    "Total Lançado - R$:\n"
    "MATRICULA - 123; VALOR VENAL 2026: R$ 287.654,32 E VALOR DA\n"
    "TRANSAÇÃO: R$ 1.234.567,89.\n"
    f"Adquirente: Fulano de Tal - CPF: {CPF_VALIDO}.\n"
)


class TestLayoutProsaQuebradaEmbu:
    def test_label_split_across_a_line_break_is_found(self) -> None:
        r = parse_guia_itbi(_EMBU_PROSA, TextSource.TEXT_LAYER)
        assert r.valor_transacao == Decimal("1234567.89")
        assert r.rotulos["valor_transacao"] == "VALOR DA TRANSACAO"
