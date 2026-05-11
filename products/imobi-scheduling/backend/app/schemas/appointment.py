"""Pydantic models for the appointment lifecycle.

Three entities here: ``AppointmentRequest`` (collecting-details state),
``AppointmentRequestService`` (M2M with services), and ``Appointment``
(confirmed booking). The conversation flow transitions from request →
appointment after the bot and user converge on a slot.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AppointmentRequestStatus = Literal[
    "collecting_details",
    "pending_confirmation",
    "confirmed",
    "cancelled",
    "expired",
]

AppointmentStatus = Literal[
    "scheduled",
    "completed",
    "cancelled",
    "no_show",
    "rescheduled",
]


class AppointmentRequestCreate(BaseModel):
    requester_user_id: UUID
    property_id: UUID | None = None
    condominium_id: UUID | None = None
    requested_date: date | None = None
    requested_time_window: str | None = Field(None, max_length=40)
    status: AppointmentRequestStatus = "collecting_details"
    notes: str | None = None


class AppointmentRequestUpdate(BaseModel):
    property_id: UUID | None = None
    condominium_id: UUID | None = None
    requested_date: date | None = None
    requested_time_window: str | None = Field(None, max_length=40)
    status: AppointmentRequestStatus | None = None
    notes: str | None = None


class AppointmentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    requester_user_id: UUID
    property_id: UUID | None
    condominium_id: UUID | None
    requested_date: date | None
    requested_time_window: str | None
    status: AppointmentRequestStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AppointmentCreate(BaseModel):
    appointment_request_id: UUID | None = None
    property_id: UUID
    condominium_id: UUID
    media_crew_user_id: UUID | None = None
    route_group_id: UUID | None = None
    google_calendar_event_id: str | None = Field(None, max_length=255)
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus = "scheduled"

    @model_validator(mode="after")
    def _end_after_start(self) -> "AppointmentCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be strictly greater than start_at")
        return self


class AppointmentUpdate(BaseModel):
    media_crew_user_id: UUID | None = None
    route_group_id: UUID | None = None
    google_calendar_event_id: str | None = Field(None, max_length=255)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: AppointmentStatus | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "AppointmentUpdate":
        if self.start_at is not None and self.end_at is not None and self.end_at <= self.start_at:
            raise ValueError("end_at must be strictly greater than start_at")
        return self


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    appointment_request_id: UUID | None
    google_calendar_event_id: str | None
    property_id: UUID
    condominium_id: UUID
    media_crew_user_id: UUID | None
    route_group_id: UUID | None
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    created_at: datetime
    updated_at: datetime
