"""AI credit pricing — the ONE place the usage price formula lives.

    price_BRL = cost_usd × (fx + fx_buffer_brl) × (1 + iof_rate + import_tax_rate)
                ÷ (1 − simples_rate − gateway_fee_rate) × (1 + margin)
    credits   = price_BRL ÷ credit_unit_brl

The numbers are DATA in ``public.credit_pricing`` (versioned, insert-only,
migration 093); the effective version is the latest ``effective_from <= now``.
``fx`` is the PTAX the ``ai_usage`` row was priced at (``ai_usage.fx_rate``) —
deterministic: re-pricing a row always gives the same credits.

Margin note (owner 2026-10-29): never cost + 1% — IOF alone is 3.5%. The
seeded ``margin = 1.0`` (100% markup) lands ≈ 45-50% usage gross margin once
IOF, Simples and the gateway fee are paid out of revenue (`gross_margin`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Optional

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

PRICING_TABLE = "credit_pricing"
_CREDIT_Q = Decimal("0.000001")
_BRL_Q = Decimal("0.000001")


class PricingNotConfigured(RuntimeError, IntegrationNotConfigured):
    """No ``credit_pricing`` version is effective — nothing can be priced."""


@dataclass(frozen=True)
class Pricing:
    version: int
    credit_unit_brl: Decimal
    margin: Decimal
    fx_buffer_brl: Decimal
    iof_rate: Decimal
    import_tax_rate: Decimal
    simples_rate: Decimal
    gateway_fee_rate: Decimal
    effective_from: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Pricing":
        d = lambda k, default="0": Decimal(str(row.get(k) if row.get(k) is not None else default))  # noqa: E731
        return cls(
            version=int(row["version"]),
            credit_unit_brl=d("credit_unit_brl"),
            margin=d("margin"),
            fx_buffer_brl=d("fx_buffer_brl"),
            iof_rate=d("iof_rate"),
            import_tax_rate=d("import_tax_rate"),
            simples_rate=d("simples_rate"),
            gateway_fee_rate=d("gateway_fee_rate"),
            effective_from=row.get("effective_from"),
            notes=row.get("notes"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "credit_unit_brl": float(self.credit_unit_brl),
            "margin": float(self.margin),
            "fx_buffer_brl": float(self.fx_buffer_brl),
            "iof_rate": float(self.iof_rate),
            "import_tax_rate": float(self.import_tax_rate),
            "simples_rate": float(self.simples_rate),
            "gateway_fee_rate": float(self.gateway_fee_rate),
            "effective_from": self.effective_from,
            "notes": self.notes,
            "gross_margin": float(gross_margin(self)),
        }


@dataclass(frozen=True)
class UsagePrice:
    price_brl: Decimal
    credits: Decimal
    provider_cost_brl: Decimal  # cost_usd × fx (what the provider bill costs us before IOF)


def _divisor(p: Pricing) -> Decimal:
    divisor = Decimal(1) - p.simples_rate - p.gateway_fee_rate
    if divisor <= 0:
        raise PricingNotConfigured(f"pricing v{p.version}: simples + gateway fee >= 100%")
    return divisor


def price_usage(cost_usd: Any, fx_rate: Any, pricing: Pricing) -> UsagePrice:
    """Price one provider cost (USD at ``fx_rate`` BRL/USD) in BRL and credits."""
    cost = Decimal(str(cost_usd or 0))
    fx = Decimal(str(fx_rate))
    if cost < 0 or fx <= 0:
        raise ValueError(f"invalid cost_usd={cost_usd!r} / fx_rate={fx_rate!r}")
    price = (
        cost * (fx + pricing.fx_buffer_brl) * (Decimal(1) + pricing.iof_rate + pricing.import_tax_rate)
        / _divisor(pricing) * (Decimal(1) + pricing.margin)
    )
    price = price.quantize(_BRL_Q, rounding=ROUND_HALF_EVEN)
    credits = (price / pricing.credit_unit_brl).quantize(_CREDIT_Q, rounding=ROUND_HALF_EVEN)
    return UsagePrice(price_brl=price, credits=credits,
                      provider_cost_brl=(cost * fx).quantize(_BRL_Q, rounding=ROUND_HALF_EVEN))


def credits_for_brl(brl: Any, pricing: Pricing) -> Decimal:
    """Credits a payment of ``brl`` buys (a purchase: 1 credit = credit_unit_brl)."""
    return (Decimal(str(brl)) / pricing.credit_unit_brl).quantize(_CREDIT_Q, rounding=ROUND_HALF_EVEN)


def brl_for_credits(credits: Any, pricing: Pricing) -> Decimal:
    return (Decimal(str(credits)) * pricing.credit_unit_brl).quantize(_BRL_Q, rounding=ROUND_HALF_EVEN)


def credits_for_usd_grant(usd: Any, fx_rate: Any, pricing: Pricing) -> Decimal:
    """An admin grant stated in USD (``US$100 em créditos``): the RETAIL value —
    usd × fx in BRL, converted at the credit unit (no markup: the org receives
    US$100 worth of credits at the price it would pay)."""
    return credits_for_brl(Decimal(str(usd)) * Decimal(str(fx_rate)), pricing)


def gross_margin(pricing: Pricing) -> Decimal:
    """Usage gross margin at a nominal FX of 5.50: (revenue − provider cost incl.
    IOF/import − Simples − gateway fee) ÷ revenue. Informational (pricing editor)."""
    fx = Decimal("5.50")
    unit = price_usage(1, fx, pricing)
    revenue = unit.price_brl
    if revenue <= 0:
        return Decimal(0)
    cost = Decimal(1) * fx * (Decimal(1) + pricing.iof_rate + pricing.import_tax_rate)
    taxes = revenue * (pricing.simples_rate + pricing.gateway_fee_rate)
    return ((revenue - cost - taxes) / revenue).quantize(Decimal("0.0001"))


def load_pricing(db: Any, *, at: Optional[datetime] = None, version: Optional[int] = None) -> Pricing:
    """The effective pricing version (latest ``effective_from <= at``), or a pinned ``version``."""
    q = db.table(PRICING_TABLE).select("*")
    if version is not None:
        rows = q.eq("version", version).limit(1).execute().data or []
    else:
        if at is not None:
            q = q.lte("effective_from", at.isoformat())
        rows = q.order("effective_from", desc=True).order("version", desc=True).limit(1).execute().data or []
    if not rows:
        raise PricingNotConfigured("no credit_pricing version is effective (migration 093 not applied?)")
    return Pricing.from_row(rows[0])


def list_pricing(db: Any) -> list[dict[str, Any]]:
    rows = db.table(PRICING_TABLE).select("*").order("version", desc=True).limit(100).execute().data or []
    return [Pricing.from_row(r).as_dict() | {"created_at": r.get("created_at")} for r in rows]


__all__ = [
    "Pricing",
    "PricingNotConfigured",
    "UsagePrice",
    "brl_for_credits",
    "credits_for_brl",
    "credits_for_usd_grant",
    "gross_margin",
    "list_pricing",
    "load_pricing",
    "price_usage",
]
