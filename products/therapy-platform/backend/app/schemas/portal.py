"""
Patient Portal Schemas — Mood tracking, journaling, homework assignments.

These schemas support patient-facing features accessible through the portal.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Mood Entries
# ---------------------------------------------------------------------------

class MoodEntryCreate(BaseModel):
    """Record a mood/emotional state entry."""

    rating: int = Field(..., ge=1, le=10, description="Mood rating from 1 (worst) to 10 (best)")
    emocoes: Optional[list[str]] = Field(default=None, description="List of emotion labels")
    nota: Optional[str] = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Journal Entries
# ---------------------------------------------------------------------------

class JournalEntryCreate(BaseModel):
    """Create a journal entry."""

    titulo: Optional[str] = Field(default=None, max_length=300)
    conteudo: str = Field(..., min_length=1, max_length=50000)


class JournalEntryUpdate(BaseModel):
    """Partial update for a journal entry."""

    titulo: Optional[str] = Field(default=None, max_length=300)
    conteudo: Optional[str] = Field(default=None, min_length=1, max_length=50000)
    is_shared_with_therapist: Optional[bool] = None


# ---------------------------------------------------------------------------
# Homework Assignments
# ---------------------------------------------------------------------------

class HomeworkAssignCreate(BaseModel):
    """Therapist assigns homework to a patient."""

    patient_id: UUID
    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: str = Field(..., min_length=1, max_length=10000)
    data_limite: Optional[date] = None


class HomeworkSubmitCreate(BaseModel):
    """Patient submits their homework response."""

    resposta_paciente: str = Field(..., min_length=1, max_length=20000)


class HomeworkReviewCreate(BaseModel):
    """Therapist reviews submitted homework."""

    feedback_terapeuta: str = Field(..., min_length=1, max_length=10000)
    status: Literal["revisado"]
