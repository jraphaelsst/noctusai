"""Tests for `noctusai_lib.domain.texto_ptbr`.

Each class pins ONE notarial convention the module docstring names, so a
future "simplification" that breaks it fails with the convention's name.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.domain.texto_ptbr import (
    brl_por_extenso,
    data_por_extenso,
    dias_por_extenso,
    formatar_brl,
    formatar_data_br,
    inteiro_por_extenso,
    numero_com_extenso,
    ordinal_por_extenso,
    parse_brl,
    percentual_por_extenso,
    reais_por_extenso,
)


class TestInteiroPorExtenso:
    @pytest.mark.parametrize(
        "n, esperado",
        [
            (0, "zero"),
            (1, "um"),
            (10, "dez"),
            (16, "dezesseis"),
            (21, "vinte e um"),
            (100, "cem"),
            (101, "cento e um"),
            (110, "cento e dez"),
            (999, "novecentos e noventa e nove"),
            (1000, "mil"),
            (1001, "mil e um"),
            (1100, "mil e cem"),
            (1234, "mil, duzentos e trinta e quatro"),
            (2000, "dois mil"),
            (100_000, "cem mil"),
            (1_000_000, "um milhão"),
            (1_000_500, "um milhão e quinhentos"),
            (1_100_000, "um milhão e cem mil"),
            (2_000_001, "dois milhões e um"),
            (
                1_234_567,
                "um milhão, duzentos e trinta e quatro mil, quinhentos e sessenta e sete",
            ),
            (1_000_000_000, "um bilhão"),
        ],
    )
    def test_masculino(self, n, esperado):
        assert inteiro_por_extenso(n) == esperado

    def test_feminino_agrees_units_and_hundreds_not_scales(self):
        assert inteiro_por_extenso(2, feminino=True) == "duas"
        assert inteiro_por_extenso(201, feminino=True) == "duzentas e uma"
        assert inteiro_por_extenso(2_000_000, feminino=True) == "dois milhões"

    @pytest.mark.parametrize("bad", [-1, 1.5, True, "3"])
    def test_refuses_what_it_cannot_read(self, bad):
        with pytest.raises(ValueError):
            inteiro_por_extenso(bad)


class TestReaisPorExtenso:
    @pytest.mark.parametrize(
        "valor, esperado",
        [
            ("0", "zero reais"),
            ("0.01", "um centavo"),
            ("0.50", "cinquenta centavos"),
            ("1", "um real"),
            ("1.01", "um real e um centavo"),
            ("100", "cem reais"),
            ("101", "cento e um reais"),
            ("1000", "mil reais"),
            (
                "1234.56",
                "mil, duzentos e trinta e quatro reais e cinquenta e seis centavos",
            ),
            ("1000000", "um milhão de reais"),
            ("2000000.01", "dois milhões de reais e um centavo"),
            ("1000500", "um milhão e quinhentos reais"),
            (
                "1234567.89",
                "um milhão, duzentos e trinta e quatro mil, quinhentos e "
                "sessenta e sete reais e oitenta e nove centavos",
            ),
        ],
    )
    def test_conventions(self, valor, esperado):
        assert reais_por_extenso(Decimal(valor)) == esperado

    def test_refuses_float_negative_and_sub_centavo(self):
        with pytest.raises(ValueError):
            reais_por_extenso(1.5)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            reais_por_extenso(Decimal("-1"))
        with pytest.raises(ValueError):
            reais_por_extenso(Decimal("1.005"))


class TestBrl:
    def test_digits_and_words_come_from_one_value(self):
        assert brl_por_extenso(Decimal("1234.56")) == (
            "R$ 1.234,56 (mil, duzentos e trinta e quatro reais e cinquenta e "
            "seis centavos)"
        )

    @pytest.mark.parametrize(
        "valor, esperado",
        [("0", "R$ 0,00"), ("1234.5", "R$ 1.234,50"), ("1000000", "R$ 1.000.000,00")],
    )
    def test_formatar(self, valor, esperado):
        assert formatar_brl(Decimal(valor)) == esperado

    @pytest.mark.parametrize("valor", ["0", "0.01", "999.99", "1000", "2000000.01"])
    def test_parse_round_trips_formatar(self, valor):
        assert parse_brl(formatar_brl(Decimal(valor))) == Decimal(valor)

    @pytest.mark.parametrize("bad", ["", "1234,5", "R$ 1,234.56", "abc"])
    def test_parse_refuses_other_shapes(self, bad):
        with pytest.raises(ValueError):
            parse_brl(bad)


class TestOrdinais:
    @pytest.mark.parametrize(
        "n, fem, masc",
        [
            (1, "primeira", "primeiro"),
            (2, "segunda", "segundo"),
            (10, "décima", "décimo"),
            (11, "décima primeira", "décimo primeiro"),
            (16, "décima sexta", "décimo sexto"),
            (20, "vigésima", "vigésimo"),
            (100, "centésima", "centésimo"),
        ],
    )
    def test_both_genders(self, n, fem, masc):
        assert ordinal_por_extenso(n, feminino=True) == fem
        assert ordinal_por_extenso(n) == masc

    @pytest.mark.parametrize("bad", [0, 1000, -1])
    def test_range(self, bad):
        with pytest.raises(ValueError):
            ordinal_por_extenso(bad)


class TestPrazosDatasPercentuais:
    def test_dias(self):
        assert dias_por_extenso(90) == "90 (noventa) dias corridos"
        assert dias_por_extenso(1) == "1 (um) dia corrido"
        assert dias_por_extenso(5, uteis=True) == "5 (cinco) dias úteis"
        assert dias_por_extenso(1, uteis=True) == "1 (um) dia útil"

    def test_numero_com_extenso(self):
        assert numero_com_extenso(2, feminino=True, largura=2) == "02 (duas)"

    def test_datas(self):
        assert data_por_extenso(date(2026, 9, 5)) == "05 de setembro de 2026"
        assert formatar_data_br(date(2026, 3, 1)) == "01/03/2026"

    @pytest.mark.parametrize(
        "valor, esperado",
        [
            ("1", "1% (um por cento)"),
            ("6.00", "6% (seis por cento)"),
            ("1.25", "1,25% (um vírgula vinte e cinco por cento)"),
            ("0.5", "0,5% (zero vírgula cinco por cento)"),
            ("1.05", "1,05% (um vírgula zero cinco por cento)"),
        ],
    )
    def test_percentual(self, valor, esperado):
        assert percentual_por_extenso(Decimal(valor)) == esperado
