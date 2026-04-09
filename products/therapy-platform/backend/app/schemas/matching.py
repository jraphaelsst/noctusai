"""
Matching Schemas — Therapist-patient matching requests.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    """Request therapist matches for a patient."""

    patient_id: UUID
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=100)
