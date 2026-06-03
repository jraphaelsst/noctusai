"""
Pydantic schemas for the /api/crm endpoints (leads, funil, scoring,
lead activities, public capture).

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import EmailStr, Field

from noctusai_lib.api import StrictHttpModel

TemperatureLiteral = Literal["cold", "warm", "hot"]


# ---------------------------------------------------------------------------
# Lead inbound
# ---------------------------------------------------------------------------

class LeadCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    company: Optional[str] = Field(default=None, max_length=255)
    source: Optional[str] = Field(default=None, max_length=100)
    stage_id: Optional[UUID] = None
    value: Optional[float] = Field(default=None, ge=0)
    owner_id: Optional[UUID] = None
    next_contact: Optional[str] = None   # ISO 8601 datetime string
    client_id: Optional[UUID] = None
    qualification_source: Optional[str] = None  # form_id
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class LeadUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    company: Optional[str] = Field(default=None, max_length=255)
    source: Optional[str] = Field(default=None, max_length=100)
    stage_id: Optional[UUID] = None
    value: Optional[float] = Field(default=None, ge=0)
    owner_id: Optional[UUID] = None
    next_contact: Optional[str] = None
    client_id: Optional[UUID] = None
    qualification_source: Optional[str] = None
    custom_fields: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None


class StageMoveRequest(StrictHttpModel):
    stage_id: UUID


# ---------------------------------------------------------------------------
# Activity inbound
# ---------------------------------------------------------------------------

class ActivityCreate(StrictHttpModel):
    type: str = Field(..., min_length=1, max_length=100)
    note: Optional[str] = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Public capture inbound — less strict (unknown keys → custom_fields)
# ---------------------------------------------------------------------------

class LeadCaptureRequest(StrictHttpModel):
    """Public lead capture: known keys mapped to columns; rest → custom_fields.

    extra="allow" is intentional here — the service maps unknown keys
    to custom_fields JSONB rather than rejecting them. This is the only
    inbound model that allows extras.
    """
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    company: Optional[str] = Field(default=None, max_length=255)
    source: Optional[str] = Field(default=None, max_length=100)
    value: Optional[float] = Field(default=None, ge=0)
    stage_id: Optional[UUID] = None

    model_config = {"extra": "allow"}  # unknown fields forwarded to custom_fields


# ---------------------------------------------------------------------------
# Scoring rules inbound
# ---------------------------------------------------------------------------

class ScoringRuleCreate(StrictHttpModel):
    form_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    score: int = Field(..., ge=-2, le=2)
    is_blocker: bool = False


class ScoringRuleUpdate(StrictHttpModel):
    score: Optional[int] = Field(default=None, ge=-2, le=2)
    is_blocker: Optional[bool] = None
    answer: Optional[str] = None


# ---------------------------------------------------------------------------
# Outbound (extra="ignore" — DB can return extra columns safely)
# ---------------------------------------------------------------------------

class LeadOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    source: Optional[str] = None
    stage_id: Optional[UUID] = None
    temperature: Optional[TemperatureLiteral] = None
    qualification_score: Optional[int] = None
    qualification_source: Optional[str] = None
    value: Optional[float] = None
    owner_id: Optional[UUID] = None
    next_contact: Optional[str] = None
    client_id: Optional[UUID] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    won_at: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"extra": "ignore"}


class ActivityOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    lead_id: UUID
    type: str
    note: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: str

    model_config = {"extra": "ignore"}


class ScoringResultOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    lead_id: UUID
    score_total: int
    qualification: Optional[TemperatureLiteral] = None
    answers_detail: dict[str, Any] = Field(default_factory=dict)
    scored_at: str

    model_config = {"extra": "ignore"}


class ScoringRuleOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    form_id: str
    question: str
    answer: str
    score: int
    is_blocker: bool
    created_at: str

    model_config = {"extra": "ignore"}
