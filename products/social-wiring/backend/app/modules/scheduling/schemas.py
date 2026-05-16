"""Pydantic HTTP-boundary models for the social-wiring ``scheduling``
module. Absorbed from ``imobi-scheduling`` (Wave 2.3).

All inherit the seed ``StrictHttpModel`` (``extra="forbid"`` → 422 on
unknown keys) per ``KB § PATTERNS/pydantic-strict-http.md``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from noctusai_lib.api import StrictHttpModel

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

UserRole = Literal["real_estate_agent", "media_crew", "admin"]
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
PendingChatStatus = Literal["pending", "resolved", "rejected"]


# ---------------------------------------------------------------------------
# Users (scheduling-domain staff + media crew)
# ---------------------------------------------------------------------------


class UserCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=120)
    role: UserRole
    phone_number: str = Field(..., min_length=8, max_length=32)
    email: str | None = Field(None, max_length=255)
    linked_identity: str | None = Field(None, max_length=128)
    active: bool = True


class UserUpdate(StrictHttpModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    role: UserRole | None = None
    email: str | None = Field(None, max_length=255)
    linked_identity: str | None = Field(None, max_length=128)
    active: bool | None = None


class UserOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    auth_user_id: UUID | None
    name: str
    role: UserRole
    phone_number: str
    email: str | None
    linked_identity: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Condominiums
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class PropertyCreate(StrictHttpModel):
    condominium_id: UUID
    code: str = Field(..., min_length=1, max_length=32)
    unit: str | None = Field(None, max_length=80)
    address_notes: str | None = None
    active: bool = True


class PropertyUpdate(StrictHttpModel):
    code: str | None = Field(None, min_length=1, max_length=32)
    unit: str | None = Field(None, max_length=80)
    address_notes: str | None = None
    active: bool | None = None


class PropertyOut(StrictHttpModel):
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


# ---------------------------------------------------------------------------
# Services + crew skills
# ---------------------------------------------------------------------------


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
    user_id: UUID
    service_id: UUID


class CrewSkillOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    service_id: UUID
    org_id: UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Appointment lifecycle
# ---------------------------------------------------------------------------


class AppointmentRequestCreate(StrictHttpModel):
    requester_user_id: UUID
    property_id: UUID | None = None
    condominium_id: UUID | None = None
    requested_date: date | None = None
    requested_time_window: str | None = Field(None, max_length=40)
    status: AppointmentRequestStatus = "collecting_details"
    notes: str | None = None


class AppointmentRequestUpdate(StrictHttpModel):
    property_id: UUID | None = None
    condominium_id: UUID | None = None
    requested_date: date | None = None
    requested_time_window: str | None = Field(None, max_length=40)
    status: AppointmentRequestStatus | None = None
    notes: str | None = None


class AppointmentRequestOut(StrictHttpModel):
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


class AppointmentCreate(StrictHttpModel):
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


class AppointmentUpdate(StrictHttpModel):
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


class AppointmentOut(StrictHttpModel):
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


# ---------------------------------------------------------------------------
# Pending chat identities (LID deferred-auth admin surface)
# ---------------------------------------------------------------------------


class PendingChatIdentityResolve(StrictHttpModel):
    status: PendingChatStatus
    resolved_to_user_id: UUID | None = None


class PendingChatIdentityOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    chat_id: str
    push_name: str | None
    phone_hint: str | None
    status: PendingChatStatus
    captured_at: datetime
    resolved_at: datetime | None
    resolved_to_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Tool-driven scheduling operations (chat-layer composition surface)
# ---------------------------------------------------------------------------


class ProposeRequest(StrictHttpModel):
    property_code: str = Field(..., min_length=1, max_length=32)
    requested_date: date
    time_window: Literal["morning", "afternoon", "any"] = "any"


class ProposedSlotOut(StrictHttpModel):
    start_at: str
    end_at: str
    duration_minutes: int
    score: float


class ProposeResponse(StrictHttpModel):
    property_code: str
    slots: list[ProposedSlotOut]


__all__ = [
    "AppointmentCreate",
    "AppointmentOut",
    "AppointmentRequestCreate",
    "AppointmentRequestOut",
    "AppointmentRequestStatus",
    "AppointmentRequestUpdate",
    "AppointmentStatus",
    "AppointmentUpdate",
    "CondominiumCreate",
    "CondominiumOut",
    "CondominiumUpdate",
    "CrewSkillCreate",
    "CrewSkillOut",
    "PendingChatIdentityOut",
    "PendingChatIdentityResolve",
    "PendingChatStatus",
    "ProposeRequest",
    "ProposeResponse",
    "ProposedSlotOut",
    "PropertyCreate",
    "PropertyOut",
    "PropertyUpdate",
    "ServiceCreate",
    "ServiceOut",
    "ServiceUpdate",
    "UserCreate",
    "UserOut",
    "UserRole",
    "UserUpdate",
]
