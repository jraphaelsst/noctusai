"""Quote totals -- pure, integer cents, server-computed (a client never tells the server what a quote costs).

    line.total   = round_half_up(qty * unit_price) - line.discount           (>= 0)
    subtotal     = sum(line.total)
    total        = subtotal - discount                                       (header discount <= subtotal)

Quantities are `Decimal` (3 places, fractional KG / hours); every amount leaves here as an `int` of cents.
Rounding is HALF-UP on the cents of each line, so a printed document re-adds to the same total.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping

from .errors import DESCONTO_INVALIDO, LINHA_INVALIDA, invalid


def money_text(cents: int, currency: str = "BRL") -> str:
    reais, centavos = divmod(int(cents), 100)
    whole = f"{reais:,}".replace(",", ".")
    return f"{'R$ ' if currency == 'BRL' else currency + ' '}{whole},{centavos:02d}"


def line_gross_cents(qty: Decimal, unit_price_cents: int) -> int:
    return int((qty * Decimal(unit_price_cents)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def line_total_cents(qty: Decimal, unit_price_cents: int, discount_cents: int, *, index: int = 0) -> int:
    gross = line_gross_cents(qty, unit_price_cents)
    if discount_cents < 0 or discount_cents > gross:
        raise invalid(f"lines[{index}].discount_cents", "O desconto da linha não pode ser maior que o valor da linha.", DESCONTO_INVALIDO)
    return gross - discount_cents


def compute_totals(lines: Iterable[Mapping[str, Any]], discount_cents: int = 0) -> dict[str, int]:
    """`{subtotal_cents, discount_cents, total_cents}` from normalized lines (`qty`, `unit_price_cents`, `discount_cents`)."""
    subtotal = 0
    for i, line in enumerate(lines):
        qty = line["qty"] if isinstance(line["qty"], Decimal) else Decimal(str(line["qty"]))
        if qty <= 0:
            raise invalid(f"lines[{i}].qty", "A quantidade deve ser maior que zero.", LINHA_INVALIDA)
        subtotal += line_total_cents(qty, int(line["unit_price_cents"]), int(line.get("discount_cents") or 0), index=i)
    discount = int(discount_cents or 0)
    if discount < 0 or discount > subtotal:
        raise invalid("discount_cents", "O desconto não pode ser maior que o subtotal do orçamento.", DESCONTO_INVALIDO)
    return {"subtotal_cents": subtotal, "discount_cents": discount, "total_cents": subtotal - discount}


__all__ = ["compute_totals", "line_gross_cents", "line_total_cents", "money_text"]
