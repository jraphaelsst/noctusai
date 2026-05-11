"""
Scheduling Schemas — Pydantic models for availability, appointments, recurring schedules.
"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


# ---------------------------------------------------------------------------
# Availability Slots
# ---------------------------------------------------------------------------

class AvailabilitySlotCreate(StrictHttpModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Sunday … 6=Saturday")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM")
    is_recurring: bool = True
    specific_date: Optional[str] = None
    is_blocked: bool = False


class AvailabilitySlotUpdate(StrictHttpModel):
    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    is_blocked: Optional[bool] = None


class BlockDatesRequest(StrictHttpModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

class AppointmentCreate(StrictHttpModel):
    therapist_id: str
    scheduled_start: str = Field(..., description="ISO 8601 datetime")
    scheduled_end: Optional[str] = Field(None, description="ISO 8601 datetime")
    notes: Optional[str] = None


class AppointmentCancel(StrictHttpModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Recurring Schedules
# ---------------------------------------------------------------------------

class RecurringScheduleCreate(StrictHttpModel):
    therapist_id: str
    patient_id: str
    frequency: Literal["weekly", "biweekly", "monthly", "custom"]
    custom_interval_weeks: Optional[int] = Field(None, ge=1)
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    duration_minutes: int = Field(50, ge=10, le=240)
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_condition: Literal["indefinite", "after_n_occurrences", "on_date"]
    end_after_n: Optional[int] = Field(None, ge=1)
    end_on_date: Optional[str] = None


class RecurringScheduleUpdate(StrictHttpModel):
    frequency: Optional[Literal["weekly", "biweekly", "monthly", "custom"]] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = Field(None, ge=10, le=240)
    end_condition: Optional[Literal["indefinite", "after_n_occurrences", "on_date"]] = None
    end_after_n: Optional[int] = Field(None, ge=1)
    end_on_date: Optional[str] = None


class RecurringChangeRequest(StrictHttpModel):
    new_day_of_week: Optional[int] = Field(None, ge=0, le=6)
    new_start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    new_frequency: Optional[Literal["weekly", "biweekly", "monthly", "custom"]] = None
    reason: str
