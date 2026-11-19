"""Cost helpers -- LLM legs reuse the seed pricing; vendor legs price units.

LLM legs: ``llm_leg_usd`` = the seed ``estimate_cost_usd`` (catalog price at
call time). Vendor legs (ElevenLabs/HeyGen credits, no tokens):
``vendor_credit_usd`` = credits actually charged x configured USD per credit.
Both quantize like ``photo_editing.costs`` and become a ``cost_ledger`` row
through the SAME ``build_cost_row`` constructor (category ``vendor_credits``),
so the ledger shape is one -- no parallel recorder.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from noctusai_lib.domain.photo_editing.costs import CURRENCY_USD, build_cost_row
from noctusai_lib.domain.photo_editing.types import CostLedgerRow
from noctusai_lib.integrations.llm.usage import estimate_cost_usd

CATEGORY_VENDOR_CREDITS = "vendor_credits"
_Q = Decimal("0.000001")


def llm_leg_usd(
    provider: str, model: str, *, prompt_tokens: int = 0, completion_tokens: int = 0
) -> Decimal:
    amount = estimate_cost_usd(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return Decimal(repr(amount)).quantize(_Q, rounding=ROUND_HALF_UP)


def vendor_credit_usd(creditos_cobrados: Decimal | int | float, usd_por_credito: Decimal) -> Decimal:
    """Credits the vendor reported as charged x price per credit. Both required:
    an unmeasured input raises instead of yielding an estimate."""
    if creditos_cobrados is None or usd_por_credito is None:
        raise ValueError("credits and price per credit must both be measured")
    return (Decimal(str(creditos_cobrados)) * usd_por_credito).quantize(_Q, rounding=ROUND_HALF_UP)


def vendor_cost_row(
    *, org_id: str, step: str, post_id: str, vendor: str, custo_usd: Decimal
) -> CostLedgerRow:
    """``cost_ledger`` row (USD native, fx pending until the PTAX backfill)."""
    return build_cost_row(
        org_id=org_id,
        category=CATEGORY_VENDOR_CREDITS,
        step=f"{vendor}.{step}",
        reference_type="media_production_passo",
        reference_id=post_id,
        amount_native=custo_usd,
        currency=CURRENCY_USD,
    )
