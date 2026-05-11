"""Request/response schemas for `app.routers.plans`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class PlanCreate(StrictHttpModel):
    nome: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=50)
    descricao: Optional[str] = None
    price_monthly: float = Field(default=0, ge=0)
    price_yearly: float = Field(default=0, ge=0)
    max_users: int = Field(default=-1)
    max_products: int = Field(default=-1)
    features: dict = Field(default_factory=dict)
    is_custom: bool = False
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None


class PlanUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, max_length=100)
    descricao: Optional[str] = None
    price_monthly: Optional[float] = Field(default=None, ge=0)
    price_yearly: Optional[float] = Field(default=None, ge=0)
    max_users: Optional[int] = None
    max_products: Optional[int] = None
    features: Optional[dict] = None
    is_custom: Optional[bool] = None
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None
