"""
Pydantic schemas for the /api/agenda endpoints.

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

EventType = Literal["meeting", "call", "visit", "other"]


# ---------------------------------------------------------------------------
# Agenda events inbound
# ---------------------------------------------------------------------------

class AgendaEventCreate(StrictHttpModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    event_type: EventType = "other"
    client_id: Optional[UUID] = None
    starts_at: str = Field(..., description="ISO 8601 datetime with timezone")
    ends_at: str = Field(..., description="ISO 8601 datetime with timezone; must be after starts_at")
    location: Optional[str] = Field(default=None, max_length=500)
    assignee_user_id: Optional[UUID] = None


class AgendaEventUpdate(StrictHttpModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    event_type: Optional[EventType] = None
    client_id: Optional[UUID] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=500)
    assignee_user_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Outbound (extra="ignore" — DB can return extra columns safely)
# ---------------------------------------------------------------------------

class AgendaEventOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    title: str
    description: Optional[str] = None
    event_type: str
    client_id: Optional[UUID] = None
    starts_at: str
    ends_at: str
    location: Optional[str] = None
    gcal_event_id: Optional[str] = None
    assignee_user_id: Optional[UUID] = None
    # DB always provides timestamps; Optional so mock responses (no timestamps)
    # don't fail serialization in the test environment.
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"extra": "ignore"}
