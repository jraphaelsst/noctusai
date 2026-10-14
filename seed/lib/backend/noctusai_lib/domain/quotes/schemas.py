"""Request bodies for the quote routes (`StrictHttpModel`, `extra="forbid"`).

Quantities are `Decimal` (3 places); money is integer cents (never a float on the wire).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

#: Sanity bounds (not business rules): keep a typo from becoming a numeric-overflow 500.
MAX_QTY = Decimal("999999999999")
MAX_CENTS = 10_000_000_000_000
MAX_LINES = 200

_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class QuoteLineBody(StrictHttpModel):
    """One line. With `item_id` the description / unit / price / kind default from the item (and may be overridden)."""

    item_id: Optional[UUID] = None
    description: Optional[str] = Field(default=None, min_length=1, max_length=500)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=10)
    kind: Optional[Literal["goods", "service"]] = None
    qty: Decimal = Field(gt=0, le=MAX_QTY, decimal_places=3)
    unit_price_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    discount_cents: int = Field(default=0, ge=0, le=MAX_CENTS)


class QuoteBody(StrictHttpModel):
    party_id: UUID
    title: Optional[str] = Field(default=None, max_length=200)
    valid_until: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    terms: Optional[str] = Field(default=None, max_length=8000)
    discount_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    convert_to: Optional[Literal["order", "contract", "none"]] = None
    lines: list[QuoteLineBody] = Field(default_factory=list, max_length=MAX_LINES)


class QuotePatch(StrictHttpModel):
    party_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, max_length=200)
    valid_until: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    terms: Optional[str] = Field(default=None, max_length=8000)
    discount_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    convert_to: Optional[Literal["order", "contract", "none"]] = None
    lines: Optional[list[QuoteLineBody]] = Field(default=None, max_length=MAX_LINES)


class CalculateBody(StrictHttpModel):
    discount_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    lines: list[QuoteLineBody] = Field(default_factory=list, max_length=MAX_LINES)


class NewVersionBody(StrictHttpModel):
    valid_until: Optional[date] = None


class SendBody(StrictHttpModel):
    channel: Literal["email", "link"] = "email"
    to: Optional[str] = Field(default=None, max_length=254, pattern=_EMAIL)
    message: Optional[str] = Field(default=None, max_length=1000)


class StaffAcceptBody(StrictHttpModel):
    """A staff member records an acceptance obtained outside the link (phone, signed paper, e-mail)."""

    signer_name: str = Field(min_length=2, max_length=120)
    note: Optional[str] = Field(default=None, max_length=500)


class StaffRejectBody(StrictHttpModel):
    reason: str = Field(min_length=1, max_length=500)
    signer_name: Optional[str] = Field(default=None, min_length=2, max_length=120)


class PublicAcceptBody(StrictHttpModel):
    name: str = Field(min_length=2, max_length=120)
    agree: bool = False


class PublicRejectBody(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    reason: Optional[str] = Field(default=None, max_length=500)


class SignerBody(StrictHttpModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254, pattern=_EMAIL)
    cpf: str = Field(min_length=11, max_length=14)


class SignatureBody(StrictHttpModel):
    signers: list[SignerBody] = Field(min_length=1, max_length=10)
    message: Optional[str] = Field(default=None, max_length=500)
