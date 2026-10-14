"""Money conversion -- the ONE seed rounding policy for NUMERIC reais -> integer cents.

Policy: **banker's rounding (round-half-to-even)** on the cent, computed on `Decimal` (never through `float`
arithmetic). The finance organ stores integer cents; a host that still holds `NUMERIC(12,2)` reais (igig's
`fatura.valor_total`, a legacy column, a CSV cell) converts through here and nowhere else -- a per-importer
`round(x * 100)` would put a different policy (and a float-error) in every importer.

    to_cents("0.005")  -> 0      (half-even: 0.5 cent rounds to the even 0)
    to_cents("0.015")  -> 2      (1.5 -> 2)
    to_cents("-12.34") -> -1234  (sign preserved: an estorno stays negative)

Pure: stdlib only, no IO, no domain knowledge (the `primitives/` layer contract).
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Union

Reais = Union[Decimal, int, float, str]


def to_decimal(value: Reais) -> Decimal:
    """`value` as an exact `Decimal`. A `float` goes through `repr` (the shortest round-trip string), never binary expansion."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not a money amount: {value!r}")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, float):
        out = Decimal(repr(value))
    else:
        try:
            out = Decimal(str(value).strip().replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError(f"not a money amount: {value!r}") from exc
    if not out.is_finite():
        raise ValueError(f"not a finite money amount: {value!r}")
    return out


def to_cents(value: Reais) -> int:
    """Reais -> integer cents, round-half-even. See the module docstring for the policy."""
    return int((to_decimal(value) * 100).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def cents_to_decimal(cents: int) -> Decimal:
    """Integer cents -> exact reais `Decimal` (two places)."""
    return (Decimal(int(cents)) / 100).quantize(Decimal("0.01"))


__all__ = ["Reais", "cents_to_decimal", "to_cents", "to_decimal"]
