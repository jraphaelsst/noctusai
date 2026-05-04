"""`media_scheduling.properties` row shape (minimal)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Property(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    condominium_id: int
    unit: str | None = None
    address_notes: str | None = None
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
