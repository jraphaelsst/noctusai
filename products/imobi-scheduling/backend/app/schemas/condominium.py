"""Pydantic models for ``imobi_scheduling.condominiums``."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel


class CondominiumCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=160)
    address: str = Field(..., min_length=1, max_length=255)
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    notes: str | None = None
    active: bool = True


class CondominiumUpdate(StrictHttpModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    address: str | None = Field(None, min_length=1, max_length=255)
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    notes: str | None = None
    active: bool | None = None


class CondominiumOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    address: str
    latitude: float | None
    longitude: float | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
