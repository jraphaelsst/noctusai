"""`noctusai_lib.primitives.money.to_cents` -- the one seed NUMERIC->cents policy (round-half-even)."""
from decimal import Decimal

import pytest

from noctusai_lib.primitives.money import cents_to_decimal, to_cents


@pytest.mark.parametrize(
    "raw, cents",
    [
        ("0.005", 0),  # half-even: 0.5 cent -> 0
        ("0.015", 2),  # 1.5 -> 2
        ("0.025", 2),  # 2.5 -> 2
        ("0.035", 4),
        ("1234.56", 123456),
        (Decimal("19.99"), 1999),
        (19.99, 1999),  # float via repr, never binary expansion
        (0.29, 29),  # 0.29*100 == 28.999999999999996 in float arithmetic
        (10, 1000),
        ("-12.34", -1234),  # an estorno keeps its sign
        ("-0.005", 0),
        ("-0.015", -2),
        ("12,50", 1250),
    ],
)
def test_to_cents(raw, cents):
    assert to_cents(raw) == cents


@pytest.mark.parametrize("bad", [None, True, "abc", "NaN", Decimal("Infinity")])
def test_to_cents_refuses_non_money(bad):
    with pytest.raises(ValueError):
        to_cents(bad)


def test_cents_to_decimal_roundtrip():
    assert cents_to_decimal(123456) == Decimal("1234.56")
    assert to_cents(cents_to_decimal(-7)) == -7
