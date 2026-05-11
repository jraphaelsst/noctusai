"""Pydantic models for ``imobi_scheduling.services`` — service catalog."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel


class ServiceCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str | None = None
    default_duration_minutes: int = Field(30, gt=0, le=24 * 60)
    active: bool = True


class ServiceUpdate(StrictHttpModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    description: str | None = None
    default_duration_minutes: int | None = Field(None, gt=0, le=24 * 60)
    active: bool | None = None


class ServiceOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    description: str | None
    default_duration_minutes: int
    active: bool
    created_at: datetime
    updated_at: datetime


class CrewSkillCreate(StrictHttpModel):
    """M2M link — assign a media-crew user the capability to deliver a service."""

    user_id: UUID
    service_id: UUID


class CrewSkillOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    service_id: UUID
    org_id: UUID
    created_at: datetime
