"""Tests for `noctusai_lib.domain.real_estate.parcelamento`.

The one claim worth defending: `sum(dividir_em_parcelas_iguais(total, n)) ==
total`, exactly, for every `n` — including the awkward divisors where a naive
`round()` chain drifts by a centavo.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.real_estate import dividir_em_parcelas_iguais
from noctusai_lib.domain.real_estate.parcelamento import CENTAVO


class TestTheSumIsExact:
    def test_an_even_split_is_identical_installments(self):
        partes = dividir_em_parcelas_iguais(Decimal("1000.00"), 4)
        assert partes == [Decimal("250.00")] * 4
        assert sum(partes) == Decimal("1000.00")

    def test_an_awkward_divisor_puts_the_remainder_on_the_last(self):
        # 1000 / 3 = 333.33333... — a naive round() per installment drifts.
        partes = dividir_em_parcelas_iguais(Decimal("1000.00"), 3)
        assert partes[0] == partes[1] == Decimal("333.33")
        assert partes[2] == Decimal("333.34")
        assert sum(partes) == Decimal("1000.00")

    def test_ten_centavos_across_three_still_balances(self):
        partes = dividir_em_parcelas_iguais(Decimal("0.10"), 3)
        assert sum(partes) == Decimal("0.10")
        assert partes[0] == partes[1] == Decimal("0.03")
        assert partes[2] == Decimal("0.04")

    def test_a_single_installment_is_the_whole_amount(self):
        assert dividir_em_parcelas_iguais(Decimal("500000.00"), 1) == [
            Decimal("500000.00")
        ]

    def test_a_zero_total_is_all_zeroes(self):
        partes = dividir_em_parcelas_iguais(Decimal("0"), 5)
        assert partes == [Decimal("0.00")] * 4 + [Decimal("0")]
        assert sum(partes) == Decimal("0")


class TestRefusals:
    def test_zero_installments_is_refused(self):
        with pytest.raises(ValueError, match="positivo"):
            dividir_em_parcelas_iguais(Decimal("100"), 0)

    def test_negative_installments_is_refused(self):
        with pytest.raises(ValueError, match="positivo"):
            dividir_em_parcelas_iguais(Decimal("100"), -1)

    def test_a_negative_total_is_refused(self):
        with pytest.raises(ValueError, match="negativo"):
            dividir_em_parcelas_iguais(Decimal("-1"), 3)


def test_a_large_awkward_amount_across_many_installments_still_balances():
    """A property-style sweep — several divisors, one always-true assertion."""
    total = Decimal("487654.33")
    for n in range(1, 37):
        partes = dividir_em_parcelas_iguais(total, n)
        assert len(partes) == n
        assert sum(partes) == total
        # Every part is quantized to the centavo (no residual float noise).
        assert all(p == p.quantize(CENTAVO) for p in partes)
