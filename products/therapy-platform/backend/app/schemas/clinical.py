"""
Clinical Schemas — Anamnese, treatment plans, goals, evolution notes.

Supports structured clinical documentation for therapist-patient relationships.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Anamnese
# ---------------------------------------------------------------------------

class AnamneseCreate(BaseModel):
    """Initial clinical anamnesis for a patient."""

    queixa_principal: str = Field(..., min_length=1, max_length=5000, description="Queixa principal do paciente")
    historia_pregressa: Optional[str] = Field(default=None, max_length=10000)
    historico_familiar: Optional[str] = Field(default=None, max_length=10000)
    medicacoes: Optional[str] = Field(default=None, max_length=5000)
    observacoes: Optional[str] = Field(default=None, max_length=10000)


class AnamneseUpdate(BaseModel):
    """Partial update for anamnesis."""

    queixa_principal: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    historia_pregressa: Optional[str] = Field(default=None, max_length=10000)
    historico_familiar: Optional[str] = Field(default=None, max_length=10000)
    medicacoes: Optional[str] = Field(default=None, max_length=5000)
    observacoes: Optional[str] = Field(default=None, max_length=10000)


# ---------------------------------------------------------------------------
# Treatment Plans
# ---------------------------------------------------------------------------

class TreatmentPlanCreate(BaseModel):
    """Create a treatment plan for a patient."""

    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: Optional[str] = Field(default=None, max_length=10000)
    data_inicio: date
    data_revisao: Optional[date] = None


class TreatmentPlanUpdate(BaseModel):
    """Partial update for treatment plan."""

    titulo: Optional[str] = Field(default=None, min_length=1, max_length=300)
    descricao: Optional[str] = Field(default=None, max_length=10000)
    data_inicio: Optional[date] = None
    data_revisao: Optional[date] = None
    status: Optional[Literal["ativo", "concluido", "cancelado"]] = None


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

class GoalCreate(BaseModel):
    """Create a therapeutic goal within a treatment plan."""

    descricao: str = Field(..., min_length=1, max_length=2000)
    prazo: Optional[date] = None


class GoalUpdate(BaseModel):
    """Partial update for a goal."""

    descricao: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    status: Optional[Literal["pendente", "em_progresso", "concluido", "cancelado"]] = None
    observacoes: Optional[str] = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# Evolution Notes (SOAP or free-form)
# ---------------------------------------------------------------------------

class EvolutionNoteCreate(BaseModel):
    """Create an evolution note for a session.

    If formato='soap', at least subjetivo is required.
    If formato='livre', conteudo_livre is required.
    """

    appointment_id: Optional[UUID] = None
    formato: Literal["soap", "livre"]
    subjetivo: Optional[str] = Field(default=None, max_length=10000)
    objetivo: Optional[str] = Field(default=None, max_length=10000)
    avaliacao: Optional[str] = Field(default=None, max_length=10000)
    plano: Optional[str] = Field(default=None, max_length=10000)
    conteudo_livre: Optional[str] = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def validate_format_fields(self):
        if self.formato == "soap":
            if not self.subjetivo or not self.subjetivo.strip():
                raise ValueError("Campo 'subjetivo' é obrigatório para formato SOAP")
        elif self.formato == "livre":
            if not self.conteudo_livre or not self.conteudo_livre.strip():
                raise ValueError("Campo 'conteudo_livre' é obrigatório para formato livre")
        return self


class EvolutionNoteUpdate(BaseModel):
    """Partial update for an evolution note."""

    subjetivo: Optional[str] = Field(default=None, max_length=10000)
    objetivo: Optional[str] = Field(default=None, max_length=10000)
    avaliacao: Optional[str] = Field(default=None, max_length=10000)
    plano: Optional[str] = Field(default=None, max_length=10000)
    conteudo_livre: Optional[str] = Field(default=None, max_length=20000)
