"""`money` — a monetary field's value plus its own "valor por extenso"
cross-check. Synthetic values only.
"""
from __future__ import annotations

from decimal import Decimal

from noctusai_lib.integrations.documents.money import ValorLido, ler_valor
from noctusai_lib.integrations.documents.types import ExtractionConfidence


class TestBasicParse:
    def test_plain_value_with_r_prefix(self):
        r = ler_valor("R$ 350.000,00")
        assert r.valor == Decimal("350000.00")
        assert r.extenso is None
        assert r.extenso_confere is None
        assert r.confianca is ExtractionConfidence.BAIXA

    def test_value_without_r_prefix(self):
        r = ler_valor("350.000,00")
        assert r.valor == Decimal("350000.00")

    def test_small_value(self):
        r = ler_valor("R$ 7.000,00")
        assert r.valor == Decimal("7000.00")

    def test_no_money_run_returns_empty(self):
        r = ler_valor("nada aqui")
        assert r == ValorLido()

    def test_empty_string(self):
        assert ler_valor("") == ValorLido()

    def test_none_like_empty(self):
        assert ler_valor(None) == ValorLido()  # type: ignore[arg-type]


class TestOcrSpaceTolerance:
    """The tolerant pre-normaliser — OCR/vision whitespace noise INSIDE the
    money run only, never a digit re-guessed."""

    def test_space_after_currency_mark(self):
        r = ler_valor("R$1. 234,56")
        assert r.valor == Decimal("1234.56")

    def test_space_around_thousands_separator(self):
        r = ler_valor("1 . 234,56")
        assert r.valor == Decimal("1234.56")

    def test_space_before_comma(self):
        r = ler_valor("R$ 1.234 ,56")
        assert r.valor == Decimal("1234.56")

    def test_lowercase_currency_mark(self):
        r = ler_valor("r$ 1.234,56")
        assert r.valor == Decimal("1234.56")


class TestExtensoCrossCheck:
    def test_agreeing_extenso_raises_to_media(self):
        r = ler_valor(
            "R$ 1.234,56 (mil, duzentos e trinta e quatro reais e "
            "cinquenta e seis centavos)"
        )
        assert r.valor == Decimal("1234.56")
        assert r.extenso == (
            "mil, duzentos e trinta e quatro reais e cinquenta e seis centavos"
        )
        assert r.extenso_confere is True
        assert r.confianca is ExtractionConfidence.MEDIA

    def test_disagreeing_extenso_stays_baixa(self):
        r = ler_valor("R$ 1.234,56 (cem reais)")
        assert r.valor == Decimal("1234.56")
        assert r.extenso == "cem reais"
        assert r.extenso_confere is False
        assert r.confianca is ExtractionConfidence.BAIXA

    def test_extenso_comparison_is_case_and_accent_insensitive(self):
        r = ler_valor(
            "R$ 1.234,56 (MIL, DUZENTOS E TRINTA E QUATRO REAIS E "
            "CINQUENTA E SEIS CENTAVOS)"
        )
        assert r.extenso_confere is True
        assert r.confianca is ExtractionConfidence.MEDIA

    def test_no_extenso_never_reaches_media(self):
        r = ler_valor("R$ 350.000,00")
        assert r.extenso is None
        assert r.extenso_confere is None
        assert r.confianca is ExtractionConfidence.BAIXA

    def test_never_alta(self):
        """`ler_valor` alone never claims `alta` — see the module header:
        that ceiling is the document extractor's call (source-aware), not
        this pure module's."""
        for texto in (
            "R$ 350.000,00",
            "R$ 1.234,56 (mil, duzentos e trinta e quatro reais e "
            "cinquenta e seis centavos)",
        ):
            assert ler_valor(texto).confianca is not ExtractionConfidence.ALTA
