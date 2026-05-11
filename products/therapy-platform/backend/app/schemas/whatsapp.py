"""
WhatsApp Therapy Schemas — Direct messaging, reminders, and reminder configuration.

Therapy product addresses messages by `patient_id` (the patient phone is
looked up server-side from `patient_profiles`). For per-appointment
reminders the appointment row is fetched server-side too — clients send
only `appointment_id`.
"""
from __future__ import annotations

from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class WhatsAppSendCreate(StrictHttpModel):
    """Send a direct WhatsApp message to a patient (therapist only)."""

    patient_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=4096)


class WhatsAppReminderCreate(StrictHttpModel):
    """Trigger an appointment-reminder send via WhatsApp."""

    appointment_id: str = Field(..., min_length=1)


class ReminderScheduleConfigure(StrictHttpModel):
    """Configure automatic appointment-reminder schedule (therapist only).

    `antecedencia_horas` — how many hours before the appointment the
    reminder fires (1..168). `is_active` enables/disables the schedule.
    """

    antecedencia_horas: int = Field(default=24, ge=1, le=168)
    is_active: bool = True
