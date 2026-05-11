"""Pydantic models for Maps routing-cache + per-day route-group containers."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel

RouteGroupStatus = Literal["not_started", "pending", "optimized", "failed"]


class RouteGroupCreate(StrictHttpModel):
    date: date
    media_crew_user_id: UUID | None = None
    office_start_location: str | None = Field(None, max_length=255)
    office_end_location: str | None = Field(None, max_length=255)
    optimization_status: RouteGroupStatus = "not_started"


class RouteGroupUpdate(StrictHttpModel):
    media_crew_user_id: UUID | None = None
    office_start_location: str | None = Field(None, max_length=255)
    office_end_location: str | None = Field(None, max_length=255)
    optimization_status: RouteGroupStatus | None = None


class RouteGroupOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    date: date
    media_crew_user_id: UUID | None
    office_start_location: str | None
    office_end_location: str | None
    optimization_status: RouteGroupStatus
    created_at: datetime
    updated_at: datetime


class RouteCacheUpsert(StrictHttpModel):
    """Cache an origin→destination routing result from Google Maps."""

    origin_place_id: str = Field(..., min_length=1)
    destination_place_id: str = Field(..., min_length=1)
    origin_label: str | None = None
    destination_label: str | None = None
    distance_meters: int | None = Field(None, ge=0)
    duration_seconds: int | None = Field(None, ge=0)
    payload: dict[str, Any] | None = None
    provider: str = "google_maps"
    expires_at: datetime | None = None


class RouteOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    origin_place_id: str
    destination_place_id: str
    origin_label: str | None
    destination_label: str | None
    distance_meters: int | None
    duration_seconds: int | None
    payload: dict[str, Any] | None
    provider: str
    fetched_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
