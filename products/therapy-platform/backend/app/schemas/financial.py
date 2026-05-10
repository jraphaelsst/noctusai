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


class CommissionOverrideInput(BaseModel):
    """Frontend-shape commission override embedded in
    :class:`CommissionConfigRequest`. Mirrors the ``CommissionOverride`` type
    declared in ``frontend/src/types/financial.ts``."""

    entity_type: Literal["clinic", "therapist"]
    entity_id: str = Field(..., min_length=1)
    rate_pct: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))


class CommissionConfigRequest(BaseModel):
    """POST ``/api/admin/financials/commissions`` body.

    Accepts EITHER the new shape (``global_rate_pct`` and/or ``override``) OR
    the legacy single-override shape (``target_type``, ``target_id``,
    ``custom_commission_pct``). The legacy fields are normalized into
    ``override`` by :func:`model_post_init` so the router handler only sees
    one shape.

    Either path must yield at least one of ``global_rate_pct`` / ``override``;
    a body with neither is rejected at the router level.
    """

    global_rate_pct: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )
    override: Optional[CommissionOverrideInput] = None

    # Legacy shape (kept for backward compatibility with existing admin tooling).
    target_type: Optional[Literal["clinic", "therapist"]] = None
    target_id: Optional[str] = Field(default=None, min_length=1)
    custom_commission_pct: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )

    def model_post_init(self, __context):  # type: ignore[override]
        if (
            self.override is None
            and self.target_type is not None
            and self.target_id is not None
            and self.custom_commission_pct is not None
        ):
            self.override = CommissionOverrideInput(
                entity_type=self.target_type,
                entity_id=self.target_id,
                rate_pct=self.custom_commission_pct,
            )


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
