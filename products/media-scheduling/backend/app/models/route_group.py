"""`media_scheduling.route_groups` row shape.

Phase 2 mapping in PROJECT.md §5 calls this `routes` but the Supabase table
is `route_groups` — the Phase 2 Improvements block flagged the doc drift.
This module follows the table.
"""
from __future__ import annotations

from datetime import date as date_cls, datetime

from pydantic import BaseModel, ConfigDict


class RouteGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date_cls
    media_crew_user_id: int | None = None
    office_start_location: str | None = None
    office_end_location: str | None = None
    optimization_status: str = "not_started"
    created_at: datetime | None = None
    updated_at: datetime | None = None
