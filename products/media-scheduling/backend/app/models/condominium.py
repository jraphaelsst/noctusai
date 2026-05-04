"""`media_scheduling.condominiums` row shape (minimal).

Phase 4 reads `id`, `name`, `address`, `latitude`, `longitude` for routing
lookup + calendar event-mapping.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Condominium(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
