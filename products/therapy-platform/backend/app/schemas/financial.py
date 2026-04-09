"""
Financial schemas — wallets, payments, transactions, commissions, refunds.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class WalletTopUpRequest(BaseModel):
    """Patient loads credits into wallet via Stripe."""

    amount: Decimal = Field(..., ge=Decimal("1.00"), description="Valor em reais")
    payment_method_id: str = Field(..., min_length=1, description="Stripe payment method ID")


class WithdrawalRequest(BaseModel):
    """Request withdrawal from wallet to bank account."""

    amount: Decimal = Field(..., ge=Decimal("10.00"), description="Valor mínimo configurável via platform_settings")


class CardValidationRequest(BaseModel):
    """Phantom charge to validate a card."""

    payment_method_id: str = Field(..., min_length=1, description="Stripe payment method ID")


class PaymentMethodAdd(BaseModel):
    """Attach a Stripe payment method to the user."""

    stripe_payment_method_id: str = Field(..., min_length=1)
    is_default: bool = False


class ClinicTransferRequest(BaseModel):
    """Voluntary transfer from clinic wallet to therapist wallet."""

    therapist_id: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=Decimal("0"))
    reason: str = Field(..., min_length=1, max_length=500)


class CommissionOverrideRequest(BaseModel):
    """Set/update a platform commission override for a clinic or therapist."""

    target_type: Literal["clinic", "therapist"]
    target_id: str = Field(..., min_length=1)
    custom_commission_pct: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))


class RefundRequestCreate(BaseModel):
    """Patient submits a refund request."""

    transaction_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=10, max_length=2000)


class RefundReviewRequest(BaseModel):
    """Admin reviews (approves/denies) a refund request."""

    action: Literal["approve", "deny"]
    response: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Obrigatório para negação",
    )


class TransactionFilters(BaseModel):
    """Filters for listing transactions."""

    status: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    therapist_id: Optional[str] = None
    patient_id: Optional[str] = None
    clinic_id: Optional[str] = None
