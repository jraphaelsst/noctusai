"""
Settings schemas — platform settings, AI prompts, branding, therapist/patient preferences, LGPD.
"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


class PlatformSettingUpdate(BaseModel):
    """Update a single platform-level setting (admin only)."""

    key: str
    value: str


class AIPromptUpdate(BaseModel):
    """Update an AI prompt template (admin only, versioned)."""

    prompt_key: str
    prompt_text: str = Field(..., min_length=10)


class ClinicBrandingUpdate(BaseModel):
    """Update clinic visual branding (clinic admin)."""

    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None


class TherapistSettingsUpdate(BaseModel):
    """Update therapist-specific settings (bank, keys, notifications)."""

    bank_name: Optional[str] = None
    bank_agency: Optional[str] = None
    bank_account: Optional[str] = None
    pix_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    notification_email_to: Optional[str] = None


class PatientSettingsUpdate(BaseModel):
    """Update patient preferences."""

    phone: Optional[str] = None
    photo_url: Optional[str] = None
    notification_preferences: Optional[dict] = None


class DataDeletionRequest(BaseModel):
    """LGPD data deletion confirmation. Must type exact phrase."""

    confirmation: Literal["CONFIRMAR EXCLUSAO"] = Field(
        ...,
        description="Deve ser exatamente 'CONFIRMAR EXCLUSAO'",
    )
