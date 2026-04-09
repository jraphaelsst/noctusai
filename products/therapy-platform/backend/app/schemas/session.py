"""
Session Schemas — Pydantic models for video sessions, observations, patient notes, summaries.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Session Lifecycle
# ---------------------------------------------------------------------------

class SessionStartRequest(BaseModel):
    consent_given: bool = Field(
        ...,
        description="O paciente deve consentir com a gravação da sessão",
    )


class SessionEndRequest(BaseModel):
    initial_observation: Optional[str] = Field(
        None,
        description="Observação inicial do terapeuta (popup pós-sessão)",
    )


class SessionPauseRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Observations (therapist only)
# ---------------------------------------------------------------------------

class ObservationCreate(BaseModel):
    session_record_id: str
    observation_text: str = Field(..., min_length=1)


class ObservationUpdate(BaseModel):
    observation_text: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Patient Notes (patient only, strictly private)
# ---------------------------------------------------------------------------

class PatientNoteCreate(BaseModel):
    session_record_id: str
    note_text: str = Field(..., min_length=1)


class PatientNoteUpdate(BaseModel):
    note_text: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Summary Editing
# ---------------------------------------------------------------------------

class SessionSummaryEdit(BaseModel):
    summary: str
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None
