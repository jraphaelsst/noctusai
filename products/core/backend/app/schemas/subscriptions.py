"""Request/response schemas for `app.routers.subscriptions`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class SubscriptionCreate(StrictHttpModel):
    org_id: str
    plan_id: str
    status: str = Field(default="active", pattern="^(active|canceled|expired|trial)$")
    expires_at: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class SubscriptionUpdate(StrictHttpModel):
    plan_id: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|canceled|expired|trial)$")
    expires_at: Optional[str] = None
    canceled_at: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    metadata: Optional[dict] = None
