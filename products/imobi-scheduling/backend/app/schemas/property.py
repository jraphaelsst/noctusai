"""Pydantic models for ``imobi_scheduling.properties`` (units within condos)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PropertyCreate(BaseModel):
    condominium_id: UUID
    code: str = Field(..., min_length=1, max_length=32)
    unit: str | None = Field(None, max_length=80)
    address_notes: str | None = None
    active: bool = True


class PropertyUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=32)
    unit: str | None = Field(None, max_length=80)
    address_notes: str | None = None
    active: bool | None = None


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    condominium_id: UUID
    code: str
    unit: str | None
    address_notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
