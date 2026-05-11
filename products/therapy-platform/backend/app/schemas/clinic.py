"""
Clinic schemas — profile, settings, therapist config, invitations.
"""
from __future__ import annotations

from typing import Optional
from pydantic import EmailStr, Field
from noctusai_lib.api import StrictHttpModel


class ClinicUpdate(StrictHttpModel):
    """Fields a clinic admin can update on the clinic profile."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=300)
    cnpj: Optional[str] = Field(default=None, min_length=14, max_length=18)
    responsible_person: Optional[str] = Field(default=None, min_length=2, max_length=200)
    contact_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    logo_url: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=5000)
    tagline: Optional[str] = Field(default=None, max_length=300)
    specialties_offered: Optional[list[str]] = None


class ClinicResponse(StrictHttpModel):
    """Clinic profile detail response."""

    id: str
    name: str
    cnpj: Optional[str] = None
    responsible_person: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    tagline: Optional[str] = None
    specialties_offered: list[str] = Field(default_factory=list)
    is_approved: bool = False
    created_at: Optional[str] = None
    is_active: bool = True


class ClinicSettingsUpdate(StrictHttpModel):
    """Clinic financial & notification settings."""

    bank_name: Optional[str] = Field(default=None, max_length=100)
    bank_agency: Optional[str] = Field(default=None, max_length=20)
    bank_account: Optional[str] = Field(default=None, max_length=30)
    pix_key: Optional[str] = Field(default=None, max_length=100)
    notification_email_to: Optional[EmailStr] = None
    default_commission_pct_clinic_sourced: Optional[float] = Field(default=None, ge=0, le=100)
    default_commission_pct_therapist_sourced: Optional[float] = Field(default=None, ge=0, le=100)


class ClinicTherapistConfigUpdate(StrictHttpModel):
    """Per-therapist configuration within a clinic."""

    pricing_policy: Optional[str] = Field(default=None, description="clinic_sets | therapist_sets")
    commission_override_clinic_sourced: Optional[float] = Field(default=None, ge=0, le=100)
    commission_override_therapist_sourced: Optional[float] = Field(default=None, ge=0, le=100)
    clinic_set_default_price: Optional[float] = Field(default=None, ge=0, le=100000)


class TherapistInvite(StrictHttpModel):
    """Invite a therapist to join the clinic."""

    email: EmailStr
    nome: str = Field(..., min_length=2, max_length=200)
