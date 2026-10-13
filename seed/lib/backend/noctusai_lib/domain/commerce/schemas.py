"""Request bodies for the commerce routes (`StrictHttpModel`, `extra="forbid"`).

Responses are plain dicts inside the seed envelopes (`success_response` /
`paginated_response`) -- correctness is pinned by tests and the contract, the
card_hub convention.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

from .types import (
    CouponKind,
    FulfillmentType,
    PaymentMethod,
    PrivacyRequestKind,
    ProductStatus,
    ProductType,
    TaxRegime,
    TaxTreatment,
)

_MAX_JSON_BYTES = 16_000
MAX_PRICE_CENTS = 100_000_000  # R$ 1.000.000,00 -- an upper sanity bound, not a business rule


def _bounded_json(value: dict, label: str) -> dict:
    if len(json.dumps(value, default=str)) > _MAX_JSON_BYTES:
        raise ValueError(f"{label} is too large")
    return value


# ─── staff ────────────────────────────────────────────────────────────────


class ProfileBody(StrictHttpModel):
    legal_name: str = Field(min_length=2, max_length=200)
    trade_name: str = Field(min_length=1, max_length=200)
    cnpj: str = Field(min_length=1, max_length=32)
    tax_regime: TaxRegime
    tax_treatment: dict[ProductType, TaxTreatment] = Field(default_factory=dict)
    locale: str = Field(default="pt-BR", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    brand_tokens: dict[str, Any] = Field(default_factory=dict)
    address: dict[str, Any] = Field(default_factory=dict)
    contact_email: Optional[str] = Field(default=None, max_length=254)
    contact_phone: Optional[str] = Field(default=None, max_length=40)
    #: Honoured ONLY for a platform admin; silently ignored otherwise (CONTRACT §3).
    platform_fee_bps: Optional[int] = Field(default=None, ge=0, le=10000)
    expected_version: int = Field(ge=0)

    @field_validator("brand_tokens", "address")
    @classmethod
    def _small(cls, v: dict) -> dict:
        return _bounded_json(v, "field")


class CnpjLookupBody(StrictHttpModel):
    cnpj: str = Field(min_length=1, max_length=32)


class HostBody(StrictHttpModel):
    hostname: str = Field(min_length=3, max_length=253)
    is_primary: bool = False


class CategoryBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, max_length=80)
    parent_id: Optional[UUID] = None
    position: int = Field(default=0, ge=0, le=100000)


class CategoryPatch(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, max_length=80)
    parent_id: Optional[UUID] = None
    position: Optional[int] = Field(default=None, ge=0, le=100000)


class ProductBody(StrictHttpModel):
    title: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=20000)
    product_type: ProductType
    fulfillment_type: Optional[FulfillmentType] = None
    category_id: Optional[UUID] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tax_treatment_override: Optional[TaxTreatment] = None

    @field_validator("attributes")
    @classmethod
    def _small(cls, v: dict) -> dict:
        return _bounded_json(v, "attributes")


class ProductPatch(StrictHttpModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = Field(default=None, max_length=20000)
    product_type: Optional[ProductType] = None
    fulfillment_type: Optional[FulfillmentType] = None
    category_id: Optional[UUID] = None
    attributes: Optional[dict[str, Any]] = None
    tax_treatment_override: Optional[TaxTreatment] = None

    @field_validator("attributes")
    @classmethod
    def _small(cls, v: Optional[dict]) -> Optional[dict]:
        return _bounded_json(v, "attributes") if v is not None else v


class StatusBody(StrictHttpModel):
    status: ProductStatus


class OfferBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    price_cents: int = Field(gt=0, le=MAX_PRICE_CENTS)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    active: bool = True
    position: int = Field(default=0, ge=0, le=100000)


class OfferPatch(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    price_cents: Optional[int] = Field(default=None, gt=0, le=MAX_PRICE_CENTS)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    active: Optional[bool] = None
    position: Optional[int] = Field(default=None, ge=0, le=100000)


class CouponBody(StrictHttpModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: CouponKind
    value: int = Field(gt=0, le=MAX_PRICE_CENTS)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(default=None, gt=0)
    active: bool = True

    @model_validator(mode="after")
    def _coherent(self) -> "CouponBody":
        if self.kind is CouponKind.PERCENT and not 1 <= self.value <= 100:
            raise ValueError("percent coupons take a value between 1 and 100")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class CouponPatch(StrictHttpModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Optional[CouponKind] = None
    value: Optional[int] = Field(default=None, gt=0, le=MAX_PRICE_CENTS)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(default=None, gt=0)
    active: Optional[bool] = None


# ─── storefront ───────────────────────────────────────────────────────────


class QuoteItem(StrictHttpModel):
    offer_id: UUID
    qty: int = Field(default=1, ge=1, le=99)


class QuoteBody(StrictHttpModel):
    items: list[QuoteItem] = Field(min_length=1, max_length=50)
    coupon: Optional[str] = Field(default=None, max_length=40)


class Buyer(StrictHttpModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    doc: str = Field(max_length=32)
    phone: Optional[str] = Field(default=None, max_length=40)


class Consents(StrictHttpModel):
    terms_version: str = Field(default="", max_length=40)
    privacy_version: str = Field(default="", max_length=40)
    marketing: bool = False
    immediate_delivery_waiver: bool = False


class CheckoutBody(StrictHttpModel):
    items: list[QuoteItem] = Field(min_length=1, max_length=50)
    coupon: Optional[str] = Field(default=None, max_length=40)
    buyer: Buyer
    address: Optional[dict[str, Any]] = None
    payment_method: PaymentMethod
    #: Optional at the schema level ON PURPOSE: a missing block is the domain
    #: error `aceite_obrigatorio` (422), not a generic validation error.
    consents: Optional[Consents] = None

    @field_validator("address")
    @classmethod
    def _small(cls, v: Optional[dict]) -> Optional[dict]:
        return _bounded_json(v, "address") if v is not None else v


class AccessLinkBody(StrictHttpModel):
    email: str = Field(max_length=254)


class PrivacyRequestBody(StrictHttpModel):
    email: str = Field(max_length=254)
    kind: PrivacyRequestKind
    details: Optional[str] = Field(default=None, max_length=2000)


class TokenBody(StrictHttpModel):
    token: str = Field(min_length=10, max_length=2048)


__all__ = [
    "AccessLinkBody",
    "Buyer",
    "CategoryBody",
    "CategoryPatch",
    "CheckoutBody",
    "CnpjLookupBody",
    "Consents",
    "CouponBody",
    "CouponPatch",
    "HostBody",
    "MAX_PRICE_CENTS",
    "OfferBody",
    "OfferPatch",
    "ProductBody",
    "ProductPatch",
    "ProfileBody",
    "PrivacyRequestBody",
    "QuoteBody",
    "QuoteItem",
    "StatusBody",
    "TokenBody",
]
