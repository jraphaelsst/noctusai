"""
Matching Schemas — Therapist-patient matching requests.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class MatchRequest(StrictHttpModel):
    """Request therapist matches for a patient."""

    patient_id: UUID
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=100)
