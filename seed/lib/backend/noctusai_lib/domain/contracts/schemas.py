"""Request bodies for the contracts routes (`StrictHttpModel`, `extra="forbid"`).

Money is integer cents; percentages are basis points (`450` = 4.5%) -- never floats on the wire.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from .types import BillingFrequency, BillingModel, ReadjustmentIndex

MAX_LINES = 100
MAX_SIGNERS = 10
BIG = 10**12  # sanity bound on cents (R$ 10 bi)


class LineIn(StrictHttpModel):
    item_id: Optional[str] = None
    description: str = Field(min_length=1, max_length=300)
    quantity: int = Field(default=1, ge=1, le=100000)
    unit_price_cents: int = Field(ge=0, le=BIG)


class ContractBody(StrictHttpModel):
    title: str = Field(min_length=1, max_length=200)
    number: Optional[str] = Field(default=None, max_length=60)
    party_id: Optional[str] = None
    party_name: Optional[str] = Field(default=None, max_length=200)
    party_doc: Optional[str] = Field(default=None, max_length=24)
    billing_model: BillingModel
    amount_cents: Optional[int] = Field(default=None, ge=0, le=BIG)
    lines: list[LineIn] = Field(default_factory=list, max_length=MAX_LINES)
    frequency: Optional[BillingFrequency] = None
    installments_count: Optional[int] = Field(default=None, ge=1, le=120)
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    first_due_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    auto_renew: bool = False
    renewal_months: int = Field(default=12, ge=1, le=120)
    retainer_minutes: Optional[int] = Field(default=None, ge=0, le=10**6)
    excess_rate_cents: Optional[int] = Field(default=None, ge=0, le=BIG)
    readjustment_index: ReadjustmentIndex = ReadjustmentIndex.NONE
    readjustment_percent_bp: Optional[int] = Field(default=None, ge=0, le=100000)
    readjustment_every_months: int = Field(default=12, ge=1, le=120)
    notice_days: int = Field(default=0, ge=0, le=365)
    penalty_cents: int = Field(default=0, ge=0, le=BIG)
    penalty_bp: int = Field(default=0, ge=0, le=10000)
    document_body: Optional[str] = Field(default=None, max_length=200000)
    notes: Optional[str] = Field(default=None, max_length=4000)


class TermChanges(StrictHttpModel):
    """The terms an amendment may change on a vigente contract (never the billing model or the dates already billed)."""

    amount_cents: Optional[int] = Field(default=None, ge=0, le=BIG)
    lines: Optional[list[LineIn]] = Field(default=None, max_length=MAX_LINES)
    end_date: Optional[date] = None
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    auto_renew: Optional[bool] = None
    renewal_months: Optional[int] = Field(default=None, ge=1, le=120)
    retainer_minutes: Optional[int] = Field(default=None, ge=0, le=10**6)
    excess_rate_cents: Optional[int] = Field(default=None, ge=0, le=BIG)
    readjustment_index: Optional[ReadjustmentIndex] = None
    readjustment_percent_bp: Optional[int] = Field(default=None, ge=0, le=100000)
    readjustment_every_months: Optional[int] = Field(default=None, ge=1, le=120)
    notice_days: Optional[int] = Field(default=None, ge=0, le=365)
    penalty_cents: Optional[int] = Field(default=None, ge=0, le=BIG)
    penalty_bp: Optional[int] = Field(default=None, ge=0, le=10000)


class ContractPatch(TermChanges):
    """Descriptive fields (any time before the contract is final) + the terms/structure (DRAFT only; later -> amendment)."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    number: Optional[str] = Field(default=None, max_length=60)
    party_id: Optional[str] = None
    party_name: Optional[str] = Field(default=None, max_length=200)
    party_doc: Optional[str] = Field(default=None, max_length=24)
    notes: Optional[str] = Field(default=None, max_length=4000)
    document_body: Optional[str] = Field(default=None, max_length=200000)
    billing_model: Optional[BillingModel] = None
    frequency: Optional[BillingFrequency] = None
    installments_count: Optional[int] = Field(default=None, ge=1, le=120)
    first_due_date: Optional[date] = None
    start_date: Optional[date] = None


class AmendmentBody(StrictHttpModel):
    summary: str = Field(min_length=1, max_length=2000)
    effective_on: Optional[date] = None
    changes: TermChanges


class ReadjustBody(StrictHttpModel):
    """`percent_bp` omitted + index `fixed` => the contract's stored `readjustment_percent_bp`. v1 never fetches an index."""

    percent_bp: Optional[int] = Field(default=None, ge=0, le=100000)
    index: Optional[ReadjustmentIndex] = None
    apply: bool = False
    effective_on: Optional[date] = None
    #: Apply again before the next readjustment is due (`last_readjusted_on` + `readjustment_every_months`): refused unless true.
    force: bool = False
    #: A client retry carries the same key: the readjustment is applied ONCE and the retry answers with the first result.
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=120)


class SuspendBody(StrictHttpModel):
    reason: str = Field(min_length=1, max_length=2000)


class TerminateBody(StrictHttpModel):
    reason: str = Field(min_length=1, max_length=2000)
    effective_on: Optional[date] = None
    waive_notice: bool = False
    waive_penalty: bool = False


class UsageBody(StrictHttpModel):
    minutes: int = Field(ge=1, le=10**5)
    period: Optional[date] = None
    description: Optional[str] = Field(default=None, max_length=300)


class RenderBody(StrictHttpModel):
    template: Optional[str] = Field(default=None, max_length=200000)


class SignerIn(StrictHttpModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200)
    cpf: str = Field(min_length=11, max_length=14)
    role: str = Field(default="comprador", max_length=20)
    order: int = Field(default=0, ge=0, le=20)


class SignatureBody(StrictHttpModel):
    signers: list[SignerIn] = Field(min_length=1, max_length=MAX_SIGNERS)
    message: Optional[str] = Field(default=None, max_length=500)


class CancelSignatureBody(StrictHttpModel):
    reason: str = Field(min_length=1, max_length=500)


__all__ = [
    "AmendmentBody", "CancelSignatureBody", "ContractBody", "ContractPatch", "LineIn", "ReadjustBody",
    "RenderBody", "SignatureBody", "SignerIn", "SuspendBody", "TerminateBody", "TermChanges", "UsageBody",
]
