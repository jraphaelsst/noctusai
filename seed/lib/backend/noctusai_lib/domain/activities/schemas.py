"""Request bodies for the activities routes (`StrictHttpModel`, `extra="forbid"`: an unknown field is a 422, never dropped)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from .types import ACTIVITY_KINDS, ACTIVITY_OUTCOMES

_SLUG = r"^[a-z][a-z0-9_]*$"
Kind = Literal[ACTIVITY_KINDS]  # type: ignore[valid-type]
Outcome = Literal[ACTIVITY_OUTCOMES]  # type: ignore[valid-type]


class ActivityBody(StrictHttpModel):
    entity_kind: str = Field(min_length=1, max_length=60, pattern=_SLUG)
    entity_id: UUID
    type_slug: str = Field(min_length=1, max_length=60, pattern=_SLUG)
    title: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=4000)
    due_at: Optional[datetime] = None
    assignee_id: Optional[UUID] = None
    org_unit_id: Optional[UUID] = None


class ActivityPatch(StrictHttpModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=4000)


class CompleteBody(StrictHttpModel):
    outcome: Outcome = "realizada"


class ReassignBody(StrictHttpModel):
    assignee_id: Optional[UUID] = None


class RescheduleBody(StrictHttpModel):
    due_at: Optional[datetime] = None


class TypeBody(StrictHttpModel):
    slug: str = Field(min_length=1, max_length=60, pattern=_SLUG)
    label: str = Field(min_length=1, max_length=80)
    kind: Kind
    position: int = Field(default=0, ge=0, le=10_000)


class TypePatch(StrictHttpModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=80)
    position: Optional[int] = Field(default=None, ge=0, le=10_000)
    active: Optional[bool] = None
