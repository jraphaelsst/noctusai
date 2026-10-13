"""Gateway fee estimate shown next to an offer's price (CONTRACT §3 `fee_estimate`).

Flat fees dominate low-ticket items (a R$ 9,90 product on Pix loses ~20% to the
R$ 1,99 flat fee), so the offers editor shows the seller what each method will
cost. These are Asaas' PUBLISHED LIST prices as of `FEE_ESTIMATE_AS_OF`; a
negotiated plan, the promotional first-months price or a different card tier
changes them. It is an ESTIMATE and the API/UI label it as one -- never an
invoice figure (the real fee is read from the gateway: `get_fee_breakdown`).
"""
from __future__ import annotations

FEE_ESTIMATE_AS_OF = "2026-10"

#: Asaas list prices (2026): Pix and boleto are flat R$ 1,99 per paid charge;
#: credit card (à vista) is R$ 0,49 + 2,99% of the charge.
PIX_FLAT_CENTS = 199
BOLETO_FLAT_CENTS = 199
CARD_FLAT_CENTS = 49
CARD_PERCENT_BPS = 299  # 2,99% in basis points


def fee_estimate(price_cents: int) -> dict[str, int]:
    """`{pix_cents, boleto_cents, card_cents}` -- integer cents, card rounded half up."""
    if price_cents < 0:
        raise ValueError("price_cents must be >= 0")
    card = CARD_FLAT_CENTS + (price_cents * CARD_PERCENT_BPS + 5000) // 10000
    return {"pix_cents": PIX_FLAT_CENTS, "boleto_cents": BOLETO_FLAT_CENTS, "card_cents": card}


__all__ = [
    "BOLETO_FLAT_CENTS",
    "CARD_FLAT_CENTS",
    "CARD_PERCENT_BPS",
    "FEE_ESTIMATE_AS_OF",
    "PIX_FLAT_CENTS",
    "fee_estimate",
]
