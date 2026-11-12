"""Assignment HTTP bodies -- `StrictHttpModel` (`extra="forbid"`)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api.schemas import StrictHttpModel

_SLUG = r"^[a-z][a-z0-9_]{0,39}$"


class SettingsBody(StrictHttpModel):
    strategy: Optional[str] = Field(None, min_length=2, max_length=40)
    default_team_id: Optional[UUID] = None
    keep_last: Optional[bool] = None


class TeamBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=60)
    auto: bool = True
    org_unit_id: Optional[UUID] = None


class TeamPatch(StrictHttpModel):
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    auto: Optional[bool] = None
    org_unit_id: Optional[UUID] = None


class MemberBody(StrictHttpModel):
    user_id: UUID
    active: bool = True
    capacity: Optional[int] = Field(None, ge=1, le=100000)
    ooo_from: Optional[datetime] = None
    ooo_until: Optional[datetime] = None


class MemberPatch(StrictHttpModel):
    active: Optional[bool] = None
    #: explicit null = unlimited
    capacity: Optional[int] = Field(None, ge=1, le=100000)
    ooo_from: Optional[datetime] = None
    ooo_until: Optional[datetime] = None


class OrderBody(StrictHttpModel):
    order: list[UUID] = Field(max_length=500)


class RuleBody(StrictHttpModel):
    kind: str = Field(min_length=1, max_length=20)
    match_value: str = Field(min_length=1, max_length=120)
    team_id: UUID


class AssignBody(StrictHttpModel):
    subject_kind: str = Field(pattern=_SLUG)
    subject_id: UUID
    source: Optional[str] = Field(None, max_length=120)
    org_unit_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    note: Optional[str] = Field(None, max_length=500)


class ReassignBody(StrictHttpModel):
    subject_kind: str = Field(pattern=_SLUG)
    subject_id: UUID
    to_user_id: UUID
    team_id: Optional[UUID] = None
    note: Optional[str] = Field(None, max_length=500)


class ReleaseBody(StrictHttpModel):
    subject_kind: str = Field(pattern=_SLUG)
    subject_id: UUID
    note: Optional[str] = Field(None, max_length=500)


__all__ = ["AssignBody", "MemberBody", "MemberPatch", "OrderBody", "ReassignBody", "ReleaseBody", "RuleBody", "SettingsBody", "TeamBody", "TeamPatch"]
