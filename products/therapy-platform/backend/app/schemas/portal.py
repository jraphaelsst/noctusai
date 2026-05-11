"""
Patient Portal Schemas — Mood tracking, journaling, homework assignments.

These schemas support patient-facing features accessible through the portal.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel


# ---------------------------------------------------------------------------
# Mood Entries
# ---------------------------------------------------------------------------

class MoodEntryCreate(StrictHttpModel):
    """Record a mood/emotional state entry."""

    rating: int = Field(..., ge=1, le=10, description="Mood rating from 1 (worst) to 10 (best)")
    emocoes: Optional[list[str]] = Field(default=None, description="List of emotion labels")
    nota: Optional[str] = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Journal Entries
# ---------------------------------------------------------------------------

class JournalEntryCreate(StrictHttpModel):
    """Create a journal entry."""

    titulo: Optional[str] = Field(default=None, max_length=300)
    conteudo: str = Field(..., min_length=1, max_length=50000)


class JournalEntryUpdate(StrictHttpModel):
    """Partial update for a journal entry."""

    titulo: Optional[str] = Field(default=None, max_length=300)
    conteudo: Optional[str] = Field(default=None, min_length=1, max_length=50000)
    is_shared_with_therapist: Optional[bool] = None


# ---------------------------------------------------------------------------
# Homework Assignments
# ---------------------------------------------------------------------------

class HomeworkAssignCreate(StrictHttpModel):
    """Therapist assigns homework to a patient."""

    patient_id: str = Field(..., min_length=1)
    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: str = Field(..., min_length=1, max_length=10000)
    data_limite: Optional[date] = None


class HomeworkSubmitCreate(StrictHttpModel):
    """Patient submits their homework response."""

    resposta_paciente: str = Field(..., min_length=1, max_length=20000)


class HomeworkReviewCreate(StrictHttpModel):
    """Therapist reviews submitted homework.

    `status` defaults to `"revisado"` because the workflow's only valid
    post-review state is `revisado`; tests don't supply it explicitly.
    """

    feedback_terapeuta: str = Field(..., min_length=1, max_length=10000)
    status: Literal["revisado"] = "revisado"
