"""Request bodies for the purchasing routes (`StrictHttpModel`, `extra="forbid"`).

Quantities are `Decimal` (3 places, fractional KG); money is integer cents.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

MAX_QTY = Decimal("999999999999")
MAX_CENTS = 10_000_000_000_000
MAX_LINES = 500


class OrderLineBody(StrictHttpModel):
    item_id: Optional[UUID] = None
    description: str = Field(min_length=1, max_length=300)
    unit: Optional[str] = Field(default=None, max_length=10)
    qty: Decimal = Field(gt=0, le=MAX_QTY, decimal_places=3)
    unit_cost_cents: int = Field(ge=0, le=MAX_CENTS)


class OrderBody(StrictHttpModel):
    """The whole editable order (create AND replace): lines are replaced as a set, only while in draft."""

    party_id: Optional[UUID] = None
    supplier_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    warehouse_id: Optional[UUID] = None
    expected_date: Optional[date] = None
    installments_count: int = Field(default=1, ge=1, le=120)
    first_due_days: int = Field(default=30, ge=0, le=3650)
    interval_days: int = Field(default=30, ge=0, le=3650)
    freight_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    discount_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    other_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    notes: Optional[str] = Field(default=None, max_length=2000)
    lines: list[OrderLineBody] = Field(min_length=1, max_length=MAX_LINES)


class CancelBody(StrictHttpModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class ReceiptLineBody(StrictHttpModel):
    order_line_id: UUID
    qty: Decimal = Field(gt=0, le=MAX_QTY, decimal_places=3)


class ReceiptBody(StrictHttpModel):
    received_on: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=120)
    lines: list[ReceiptLineBody] = Field(min_length=1, max_length=MAX_LINES)


class SettingsBody(StrictHttpModel):
    approval_threshold_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
