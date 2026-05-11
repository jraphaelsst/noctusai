"""
Patient profile schemas.
"""
from __future__ import annotations

from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class PatientProfileUpdate(StrictHttpModel):
    """Fields a patient can update on their own profile."""

    phone: Optional[str] = Field(default=None, max_length=20)
    photo_url: Optional[str] = None


class PatientProfileResponse(StrictHttpModel):
    """Patient profile detail response."""

    user_id: str
    current_therapist_id: Optional[str] = None
    origin: Optional[str] = None
    clinic_id: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool = True
