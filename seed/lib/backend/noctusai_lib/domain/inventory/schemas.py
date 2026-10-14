"""Request bodies for the inventory routes (`StrictHttpModel`, `extra="forbid"`).

Quantities are `Decimal` (units can be fractional KG, 3 places); money is integer cents.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

#: Sanity bounds (not business rules): keep a typo from becoming a numeric-overflow 500.
MAX_QTY = Decimal("999999999999")
MAX_COST_CENTS = 10_000_000_000_000


class AddressBody(StrictHttpModel):
    street: Optional[str] = Field(default=None, max_length=200)
    number: Optional[str] = Field(default=None, max_length=20)
    complement: Optional[str] = Field(default=None, max_length=100)
    district: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=2)
    zip: Optional[str] = Field(default=None, max_length=10)


class WarehouseBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=30)
    address: Optional[AddressBody] = None
    is_default: bool = False


class WarehousePatch(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    code: Optional[str] = Field(default=None, min_length=1, max_length=30)
    address: Optional[AddressBody] = None
    active: Optional[bool] = None
    is_default: Optional[bool] = None


class _MoveBase(StrictHttpModel):
    item_id: UUID
    warehouse_id: UUID
    source: str = Field(default="manual", min_length=1, max_length=40)
    source_ref: Optional[str] = Field(default=None, min_length=1, max_length=120)
    note: Optional[str] = Field(default=None, max_length=500)
    occurred_at: Optional[datetime] = None


class ReceiveBody(_MoveBase):
    qty: Decimal = Field(gt=0, le=MAX_QTY, decimal_places=3)
    unit_cost_cents: int = Field(ge=0, le=MAX_COST_CENTS)


class IssueBody(_MoveBase):
    qty: Decimal = Field(gt=0, le=MAX_QTY, decimal_places=3)


class AdjustBody(_MoveBase):
    counted_qty: Decimal = Field(ge=0, le=MAX_QTY, decimal_places=3)
    unit_cost_cents: Optional[int] = Field(default=None, ge=0, le=MAX_COST_CENTS)


class TransferBody(StrictHttpModel):
    item_id: UUID
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    qty: Decimal = Field(gt=0, le=MAX_QTY, decimal_places=3)
    source: str = Field(default="manual", min_length=1, max_length=40)
    source_ref: Optional[str] = Field(default=None, min_length=1, max_length=120)
    note: Optional[str] = Field(default=None, max_length=500)
    occurred_at: Optional[datetime] = None


class MinQtyBody(StrictHttpModel):
    item_id: UUID
    warehouse_id: UUID
    min_qty: Decimal = Field(ge=0, le=MAX_QTY, decimal_places=3)
