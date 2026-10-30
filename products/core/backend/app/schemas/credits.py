"""Request schemas for the AI credit wallet routes (strict — unknown fields → 422)."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

WalletMode = Literal["prepaid", "postpaid_trusted", "byok"]


class CreditPurchaseRequest(StrictHttpModel):
    amount_brl: Decimal = Field(..., gt=0, le=Decimal("50000"))
    gateway: Literal["stripe", "asaas"] = "asaas"
    billing_method: Literal["pix", "boleto", "card", "unspecified"] = "pix"
    tax_id: Optional[str] = Field(default=None, min_length=11, max_length=18)
    success_url: Optional[str] = Field(default=None, max_length=500)
    cancel_url: Optional[str] = Field(default=None, max_length=500)


class CreditGrantRequest(StrictHttpModel):
    credits: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("100000000"))
    usd: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("100000"))
    reason: str = Field(..., min_length=3, max_length=1000)

    @model_validator(mode="after")
    def _exactly_one_amount(self) -> "CreditGrantRequest":
        if (self.credits is None) == (self.usd is None):
            raise ValueError("informe 'credits' OU 'usd' (exatamente um)")
        return self


class CreditAdjustmentRequest(StrictHttpModel):
    credits: Decimal = Field(..., ge=Decimal("-100000000"), le=Decimal("100000000"))
    reason: str = Field(..., min_length=3, max_length=1000)


class CreditWalletSettingsRequest(StrictHttpModel):
    mode: Optional[WalletMode] = None
    overdraft_limit_credits: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("100000000"))
    alert_thresholds: Optional[list[float]] = Field(default=None, max_length=10)


class CreditPricingCreate(StrictHttpModel):
    credit_unit_brl: Decimal = Field(..., gt=0, le=Decimal("100"))
    margin: Decimal = Field(..., ge=0, le=Decimal("20"))
    fx_buffer_brl: Decimal = Field(default=Decimal("0.10"), ge=0, le=Decimal("5"))
    iof_rate: Decimal = Field(..., ge=0, lt=1)
    import_tax_rate: Decimal = Field(default=Decimal("0"), ge=0, lt=1)
    simples_rate: Decimal = Field(..., ge=0, lt=1)
    gateway_fee_rate: Decimal = Field(..., ge=0, lt=1)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _divisor(self) -> "CreditPricingCreate":
        if self.simples_rate + self.gateway_fee_rate >= Decimal("0.9"):
            raise ValueError("simples_rate + gateway_fee_rate deve ser < 0.9")
        return self
