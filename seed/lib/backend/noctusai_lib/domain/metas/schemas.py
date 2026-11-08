"""Metas HTTP bodies -- `StrictHttpModel` (`extra="forbid"`): a misspelt field is a 422, never silently dropped."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api.schemas import StrictHttpModel


class PeriodBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=20)
    starts_on: date
    ends_on: date
    parent_id: Optional[UUID] = None


class PeriodPatch(StrictHttpModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    kind: Optional[str] = Field(None, min_length=1, max_length=20)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    parent_id: Optional[UUID] = None
    status: Optional[Literal["open", "review", "closed"]] = None


class PeriodGenerate(StrictHttpModel):
    kind: str = Field(min_length=1, max_length=20)
    starts_on: date
    ends_on: date


class TeamBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=40)
    leader_id: Optional[UUID] = None


class TeamPatch(StrictHttpModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=40)
    leader_id: Optional[UUID] = None


class MemberBody(StrictHttpModel):
    user_id: UUID
    role: Literal["leader", "member"] = "member"


class MemberPatch(StrictHttpModel):
    role: Literal["leader", "member"]


class GoalBody(StrictHttpModel):
    scope: Literal["individual", "team", "company"]
    subject_id: Optional[UUID] = None
    category: str = Field(min_length=1, max_length=41)
    title: Optional[str] = Field(None, max_length=200)
    target: float = Field(ge=0)
    period_id: Optional[UUID] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=2000)


class GoalPatch(StrictHttpModel):
    title: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)
    target: Optional[float] = Field(None, ge=0)
    status: Optional[str] = Field(None, max_length=20)


class ContributionBody(StrictHttpModel):
    amount: float
    at: Optional[date] = None
    note: Optional[str] = Field(None, max_length=500)


class RuleBody(StrictHttpModel):
    event_type: str = Field(min_length=1, max_length=41)
    modality: Optional[str] = Field(None, max_length=41)
    points: float
    description: Optional[str] = Field(None, max_length=300)
    period_id: Optional[UUID] = None


class SettingsBody(StrictHttpModel):
    value_per_point: Optional[float] = Field(None, gt=0)
    weight_points: Optional[float] = Field(None, ge=0)
    weight_value: Optional[float] = Field(None, ge=0)
    default_ranking_metric: Optional[Literal["points", "value", "unified"]] = None


class EventBody(StrictHttpModel):
    member_id: Optional[UUID] = None
    event_type: str = Field(min_length=1, max_length=41)
    modality: Optional[str] = Field(None, max_length=41)
    occurred_on: Optional[date] = None
    value: Optional[float] = Field(None, ge=0)
    fraction: float = Field(1.0, gt=0, le=1)
    points: Optional[float] = None
    ref_kind: Optional[str] = Field(None, max_length=40)
    ref_id: Optional[UUID] = None
    notes: Optional[str] = Field(None, max_length=1000)
    dedupe_key: Optional[str] = Field(None, min_length=1, max_length=200)


class EventPatch(StrictHttpModel):
    points: Optional[float] = None
    value: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=1000)


class CloseBody(StrictHttpModel):
    period_id: UUID
