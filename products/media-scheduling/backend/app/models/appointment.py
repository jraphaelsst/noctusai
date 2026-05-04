"""`media_scheduling.appointments` row shape (minimal).

Phase 4 reads `start_at`, `end_at`, `condominium_id`, `status` for
existing-intervals fetch (SchedulingEngine input) + inserts on confirm.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Appointment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_request_id: int | None = None
    google_calendar_event_id: str | None = None
    start_at: datetime
    end_at: datetime
    property_id: int
    condominium_id: int
    route_group_id: int | None = None
    status: str = "scheduled"
    created_at: datetime | None = None
    updated_at: datetime | None = None
