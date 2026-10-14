"""Request bodies for the items routes (`StrictHttpModel`, `extra="forbid"`).

Fiscal/format validation is NOT duplicated here: bodies carry plain optionals and the SERVICE validates
(one rule set shared with the CSV import). Unknown keys are a 422, never silently dropped.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

#: Sanity bound (R$ 100 bi), not a business rule: keeps a typo from becoming a BIGINT-sized lie.
MAX_CENTS = 10_000_000_000_000
MAX_INT = 2_000_000_000


class ItemBody(StrictHttpModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    item_type: str = Field(default="goods", max_length=40)
    unit: str = Field(default="UN", max_length=8)
    category_id: Optional[UUID] = None
    ncm: Optional[str] = Field(default=None, max_length=16)
    cest: Optional[str] = Field(default=None, max_length=16)
    cfop_default: Optional[str] = Field(default=None, max_length=8)
    origem: Optional[int] = Field(default=None, ge=-1, le=100)
    gtin: Optional[str] = Field(default=None, max_length=24)
    cost_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    price_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    weight_g: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    length_mm: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    width_mm: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    height_mm: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    is_active: bool = True


class ItemPatch(StrictHttpModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    item_type: Optional[str] = Field(default=None, max_length=40)
    unit: Optional[str] = Field(default=None, max_length=8)
    category_id: Optional[UUID] = None
    ncm: Optional[str] = Field(default=None, max_length=16)
    cest: Optional[str] = Field(default=None, max_length=16)
    cfop_default: Optional[str] = Field(default=None, max_length=8)
    origem: Optional[int] = Field(default=None, ge=-1, le=100)
    gtin: Optional[str] = Field(default=None, max_length=24)
    cost_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    price_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    weight_g: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    length_mm: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    width_mm: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    height_mm: Optional[int] = Field(default=None, ge=0, le=MAX_INT)
    is_active: Optional[bool] = None


class ItemCategoryBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: Optional[UUID] = None


class ItemCategoryPatch(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    parent_id: Optional[UUID] = None
    is_active: Optional[bool] = None


__all__ = ["ItemBody", "ItemCategoryBody", "ItemCategoryPatch", "ItemPatch", "MAX_CENTS"]
