"""
Authentication and registration schemas.

Handles registration for all three roles (patient, therapist, clinic admin)
plus login and Google OAuth flows.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class PatientRegister(BaseModel):
    """Patient registration payload."""

    nome: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=20)


class TherapistRegister(BaseModel):
    """Therapist registration payload."""

    nome: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    crp: str = Field(..., min_length=4, max_length=20, description="Registro CRP do terapeuta")
    bio: Optional[str] = Field(default=None, max_length=2000)
    specialties: list[str] = Field(default_factory=list)
    approaches: list[str] = Field(default_factory=list)
    photo_url: Optional[str] = None
    default_session_price: float = Field(..., ge=0, le=100000, description="Preço padrão da sessão")


class ClinicRegister(BaseModel):
    """Clinic admin registration payload."""

    nome: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    clinic_name: str = Field(..., min_length=2, max_length=300)
    cnpj: str = Field(..., min_length=14, max_length=18)
    responsible_person: str = Field(..., min_length=2, max_length=200)
    contact_email: EmailStr
    phone: str = Field(..., max_length=20)


class LoginRequest(BaseModel):
    """Email + password login."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class GoogleAuthRequest(BaseModel):
    """Google OAuth token exchange."""

    token: str = Field(..., min_length=1, description="Google OAuth ID token")


class ForgotPasswordRequest(BaseModel):
    """Trigger password reset email."""

    email: EmailStr
