"""Request schemas for the billing admin + self-serve routes (strict)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

GatewayName = Literal["stripe", "asaas"]
GatewayMode = Literal["test", "live"]
BillingCycleName = Literal["monthly", "yearly"]
Audience = Literal["individual", "company", "any"]
PayMethod = Literal["card", "pix", "boleto", "unspecified"]


class BillingPlanCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9-_]*$")
    descricao: Optional[str] = Field(default=None, max_length=2000)
    product_id: Optional[str] = None
    audience: Audience = "any"
    trial_days: int = Field(default=0, ge=0, le=365)
    grace_days: int = Field(default=0, ge=0, le=90)
    max_users: int = Field(default=-1, ge=-1)
    features: dict = Field(default_factory=dict)


class BillingPlanUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=100)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    product_id: Optional[str] = None
    audience: Optional[Audience] = None
    trial_days: Optional[int] = Field(default=None, ge=0, le=365)
    grace_days: Optional[int] = Field(default=None, ge=0, le=90)
    max_users: Optional[int] = Field(default=None, ge=-1)
    features: Optional[dict] = None
    ativo: Optional[bool] = None


class PlanPriceCreate(StrictHttpModel):
    billing_cycle: BillingCycleName
    amount_cents: int = Field(..., ge=0, le=100_000_000)
    currency: Literal["BRL", "USD"] = "BRL"
    stripe_price_id_test: Optional[str] = Field(default=None, pattern=r"^price_[A-Za-z0-9]+$")
    stripe_price_id_live: Optional[str] = Field(default=None, pattern=r"^price_[A-Za-z0-9]+$")


class PlanPriceUpdate(StrictHttpModel):
    stripe_price_id_test: Optional[str] = Field(default=None, pattern=r"^(price_[A-Za-z0-9]+)?$")
    stripe_price_id_live: Optional[str] = Field(default=None, pattern=r"^(price_[A-Za-z0-9]+)?$")
    ativo: Optional[bool] = None


class BillingSettingsUpdate(StrictHttpModel):
    mode: Optional[GatewayMode] = None
    automations_enabled: Optional[bool] = None
    stripe_enabled: Optional[bool] = None
    asaas_enabled: Optional[bool] = None
    storage_price_usd_per_gb_month: Optional[Decimal] = Field(default=None, ge=0, le=1000)


class GatewaySecretUpdate(StrictHttpModel):
    gateway: GatewayName
    mode: GatewayMode
    field: Literal["secret_key", "webhook_secret", "api_key", "webhook_token"]
    # Empty string clears the stored value.
    value: str = Field(..., max_length=512)


class GatewayTestRequest(StrictHttpModel):
    gateway: GatewayName
    mode: GatewayMode


class ManualOnboardRequest(StrictHttpModel):
    org_id: str
    plan_price_id: str
    current_period_end: Optional[datetime] = None
    trial_days: int = Field(default=0, ge=0, le=365)
    note: Optional[str] = Field(default=None, max_length=500)


class ManualRenewRequest(StrictHttpModel):
    current_period_end: datetime


class SubscriptionCancelRequest(StrictHttpModel):
    at_period_end: bool = True


class SubscribeRequest(StrictHttpModel):
    plan_price_id: str
    gateway: GatewayName
    billing_method: PayMethod = "card"
    tax_id: Optional[str] = Field(default=None, pattern=r"^\d{11}(\d{3})?$")
    success_url: Optional[str] = Field(default=None, max_length=500)
    cancel_url: Optional[str] = Field(default=None, max_length=500)
