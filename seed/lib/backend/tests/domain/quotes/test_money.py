"""Totals: integer cents, half-up per line, server-computed, refusals pinned."""
from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.quotes.errors import QuotesError
from noctusai_lib.domain.quotes.money import compute_totals, line_gross_cents, line_total_cents, money_text


def L(qty, price, disc=0):
    return {"qty": Decimal(str(qty)), "unit_price_cents": price, "discount_cents": disc}


def test_half_up_rounding_per_line():
    assert line_gross_cents(Decimal("0.5"), 1) == 1       # 0.5 -> 1 (half-up, not bankers)
    assert line_gross_cents(Decimal("2.5"), 3) == 8       # 7.5 -> 8
    assert line_gross_cents(Decimal("1.333"), 100) == 133


def test_totals_add_up_from_rounded_lines():
    lines = [L("1.333", 100), L("0.5", 1), L(3, 999, 100)]
    t = compute_totals(lines, discount_cents=50)
    assert t == {"subtotal_cents": 133 + 1 + (2997 - 100), "discount_cents": 50, "total_cents": 133 + 1 + 2897 - 50}


def test_total_is_always_subtotal_minus_discount():
    t = compute_totals([L(2, 1050)], 100)
    assert t["total_cents"] == t["subtotal_cents"] - t["discount_cents"] == 2000


@pytest.mark.parametrize(
    "lines, discount",
    [([L(1, 100)], 101), ([L(1, 100, 101)], 0), ([L(0, 100)], 0), ([L(-1, 100)], 0), ([L(1, 100)], -1)],
)
def test_refusals(lines, discount):
    with pytest.raises(QuotesError) as err:
        compute_totals(lines, discount)
    assert err.value.status_code == 422


def test_line_discount_cannot_exceed_the_line():
    with pytest.raises(QuotesError) as err:
        line_total_cents(Decimal(1), 100, 101, index=2)
    assert err.value.code == "desconto_invalido" and err.value.details["field"] == "lines[2].discount_cents"


def test_empty_quote_totals_zero():
    assert compute_totals([], 0) == {"subtotal_cents": 0, "discount_cents": 0, "total_cents": 0}


def test_money_text_pt_br():
    assert money_text(123456) == "R$ 1.234,56"
    assert money_text(5) == "R$ 0,05"
    assert money_text(100, "USD") == "USD 1,00"
