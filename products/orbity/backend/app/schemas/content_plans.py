"""
Pydantic schemas for /api/content/plans/* — monthly content plans + items.

StrictHttpModel (extra="forbid") on every inbound model. Outbound models
ignore extra DB columns. Platform values are the SAME literals as
content_posts (schemas/social_content.PlatformLiteral) so an item can be
promoted to a post without translation.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

from app.schemas.social_content import PlatformLiteral

PlanStatusLiteral = Literal["draft", "active"]
CreationModeLiteral = Literal["ai", "manual"]
ItemStatusLiteral = Literal["planned", "task_created", "in_progress", "published", "discarded"]

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

class PlanItemCreate(StrictHttpModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    format: Optional[str] = Field(default=None, max_length=60)
    platform: Optional[PlatformLiteral] = None
    post_date: Optional[date] = None
    due_date: Optional[date] = None
    caption: Optional[str] = Field(default=None, max_length=5000)
    reference_notes: Optional[str] = Field(default=None, max_length=5000)


class PlanItemUpdate(StrictHttpModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    format: Optional[str] = Field(default=None, max_length=60)
    platform: Optional[PlatformLiteral] = None
    post_date: Optional[date] = None
    due_date: Optional[date] = None
    caption: Optional[str] = Field(default=None, max_length=5000)
    reference_notes: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[ItemStatusLiteral] = None


class PlanItemsAppend(StrictHttpModel):
    items: list[PlanItemCreate] = Field(..., min_length=1, max_length=50)


class PlanItemsReorder(StrictHttpModel):
    ids: list[UUID] = Field(..., min_length=1, max_length=500)


class PlanItemOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    plan_id: UUID
    order_position: int
    title: str
    description: Optional[str] = None
    format: Optional[str] = None
    platform: Optional[str] = None
    post_date: Optional[str] = None
    due_date: Optional[str] = None
    caption: Optional[str] = None
    reference_notes: Optional[str] = None
    status: str
    task_id: Optional[UUID] = None
    post_id: Optional[UUID] = None
    created_at: str
    updated_at: str


class PlanItemDeleteOut(StrictHttpModel):
    deleted: bool
    discarded: bool


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

class PlanCreate(StrictHttpModel):
    client_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    title: str = Field(..., min_length=1, max_length=255)
    month: str = Field(..., pattern=MONTH_PATTERN)
    strategy_context: dict[str, Any] = Field(default_factory=dict)
    status: PlanStatusLiteral = "active"
    creation_mode: CreationModeLiteral = "manual"
    items: list[PlanItemCreate] = Field(default_factory=list, max_length=100)

    @field_validator("strategy_context")
    @classmethod
    def _bounded_context(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(str(v)) > 8000:
            raise ValueError("strategy_context muito grande")
        return v


class PlanUpdate(StrictHttpModel):
    client_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    month: Optional[str] = Field(default=None, pattern=MONTH_PATTERN)
    strategy_context: Optional[dict[str, Any]] = None
    status: Optional[PlanStatusLiteral] = None


class PlanOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    client_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    title: str
    month: str
    strategy_context: dict[str, Any] = Field(default_factory=dict)
    status: str
    creation_mode: str
    created_at: str
    updated_at: str
    items: list[PlanItemOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tasks from items
# ---------------------------------------------------------------------------

class PlanTasksCreate(StrictHttpModel):
    item_ids: list[UUID] = Field(..., min_length=1, max_length=200)
    assignee_user_id: Optional[UUID] = None


class PlanTasksOut(StrictHttpModel):
    created: int
    skipped: int
    failed: int
    task_ids: list[UUID]


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------

class AIGenerateParams(StrictHttpModel):
    items_count: int = Field(..., ge=1, le=20)
    period_days: Literal[7, 14, 30, 60, 90] = 30
    start_date: date
    # 0 = Domingo ... 6 = Sábado (same convention as the upstream UI).
    weekdays: list[int] = Field(..., min_length=1, max_length=7)
    platforms: list[PlatformLiteral] = Field(..., min_length=1, max_length=5)
    formats: list[str] = Field(default_factory=list, max_length=10)
    focus: Optional[str] = Field(default=None, max_length=1000)
    objective: Optional[str] = Field(default=None, max_length=120)
    tone: Optional[str] = Field(default=None, max_length=120)
    tone_custom: Optional[str] = Field(default=None, max_length=300)
    audience: Optional[str] = Field(default=None, max_length=600)
    pillars: list[str] = Field(default_factory=list, max_length=12)
    mix_distribution: Optional[str] = Field(default=None, max_length=300)
    allow_sales_cta: bool = True
    avoid: Optional[str] = Field(default=None, max_length=1000)
    references: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays deve conter valores de 0 (domingo) a 6 (sábado)")
        return sorted(set(v))

    @field_validator("platforms")
    @classmethod
    def _unique_platforms(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _window_has_allowed_day(self) -> "AIGenerateParams":
        from datetime import timedelta

        for offset in range(self.period_days + 1):
            d = self.start_date + timedelta(days=offset)
            if (d.weekday() + 1) % 7 in self.weekdays:
                return self
        raise ValueError("Nenhum dos dias da semana escolhidos cai dentro da janela")


class AIGeneratedItem(StrictHttpModel):
    title: str
    description: Optional[str] = None
    format: Optional[str] = None
    platform: str
    post_date: date
    reference_notes: Optional[str] = None


class AIGenerateOut(StrictHttpModel):
    items: list[AIGeneratedItem]
