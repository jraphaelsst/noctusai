"""
Session Schemas — Pydantic models for video sessions, observations, patient notes, summaries.
"""
from __future__ import annotations

from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


# ---------------------------------------------------------------------------
# Session Lifecycle
# ---------------------------------------------------------------------------

class SessionStartRequest(StrictHttpModel):
    consent_given: bool = Field(
        ...,
        description="O paciente deve consentir com a gravação da sessão",
    )


class SessionEndRequest(StrictHttpModel):
    initial_observation: Optional[str] = Field(
        None,
        description="Observação inicial do terapeuta (popup pós-sessão)",
    )


class SessionPauseRequest(StrictHttpModel):
    reason: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Observations (therapist only)
# ---------------------------------------------------------------------------

class ObservationCreate(StrictHttpModel):
    session_record_id: str
    observation_text: str = Field(..., min_length=1)


class ObservationUpdate(StrictHttpModel):
    observation_text: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Patient Notes
# Access (compliance-audit-reconciliation 2026-04-22 Q1 decision, encoded
# in RLS migration 007_clinical_data_privacy.sql):
#   - Patient: read/write their own notes.
#   - Therapist-of-session: read (therapist-readable per product decision).
#   - platform_admin / clinic_admin: NO access (dropped 2026-04-22).
# ---------------------------------------------------------------------------

class PatientNoteCreate(StrictHttpModel):
    session_record_id: str
    note_text: str = Field(..., min_length=1)


class PatientNoteUpdate(StrictHttpModel):
    note_text: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Summary Editing
# ---------------------------------------------------------------------------

class SessionSummaryEdit(StrictHttpModel):
    summary: str
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None
