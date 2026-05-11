"""
Therapist profile schemas.
"""
from __future__ import annotations

from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class TherapistProfileUpdate(StrictHttpModel):
    """Fields a therapist can update on their own profile."""

    bio: Optional[str] = Field(default=None, max_length=2000)
    specialties: Optional[list[str]] = None
    approaches: Optional[list[str]] = None
    photo_url: Optional[str] = None
    default_session_price: Optional[float] = Field(default=None, ge=0, le=100000)
    session_duration_minutes: Optional[int] = Field(default=None, ge=15, le=240)


class TherapistProfileResponse(StrictHttpModel):
    """Therapist profile detail response."""

    user_id: str
    clinic_id: Optional[str] = None
    crp: str
    bio: Optional[str] = None
    specialties: list[str] = Field(default_factory=list)
    approaches: list[str] = Field(default_factory=list)
    photo_url: Optional[str] = None
    default_session_price: Optional[float] = None
    session_duration_minutes: int = 50
    is_approved: bool = False
    created_at: Optional[str] = None
    is_active: bool = True


class TherapistDirectoryFilters(StrictHttpModel):
    """Query filters for therapist directory listing."""

    specialty: Optional[str] = None
    approach: Optional[str] = None
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    min_rating: Optional[float] = Field(default=None, ge=1, le=5)
    clinic_id: Optional[str] = None
    busca: Optional[str] = None
