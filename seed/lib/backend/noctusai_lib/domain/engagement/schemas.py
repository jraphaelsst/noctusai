"""Engagement HTTP bodies -- `StrictHttpModel` (`extra="forbid"`)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api.schemas import StrictHttpModel


class EngagementEventBody(StrictHttpModel):
    member_id: Optional[UUID] = None
    source: str = Field(min_length=1, max_length=40)
    action: str = Field(min_length=1, max_length=80)
    occurred_at: Optional[datetime] = None
    idempotency_key: str = Field(min_length=1, max_length=200)


class PointRuleBody(StrictHttpModel):
    source: str = Field(min_length=1, max_length=40)
    action: str = Field(min_length=1, max_length=80)
    points: int = Field(gt=0, le=1_000_000)
    daily_cap: Optional[int] = Field(None, gt=0)
    period_cap: Optional[int] = Field(None, gt=0)


class BadgeRuleBody(StrictHttpModel):
    badge_id: str = Field(min_length=1, max_length=80)
    metric: str = Field(min_length=1, max_length=120)
    threshold: int = Field(gt=0)
    label: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=300)
