"""
Clinical Schemas — Anamnese, treatment plans, goals, evolution notes.

Supports structured clinical documentation for therapist-patient relationships.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator
from noctusai_lib.api import StrictHttpModel


# ---------------------------------------------------------------------------
# Anamnese
# ---------------------------------------------------------------------------

class AnamneseCreate(StrictHttpModel):
    """Initial clinical anamnesis for a patient."""

    queixa_principal: str = Field(..., min_length=1, max_length=5000, description="Queixa principal do paciente")
    historia_pregressa: Optional[str] = Field(default=None, max_length=10000)
    historico_familiar: Optional[str] = Field(default=None, max_length=10000)
    medicacoes: Optional[str] = Field(default=None, max_length=5000)
    observacoes: Optional[str] = Field(default=None, max_length=10000)


class AnamneseUpdate(StrictHttpModel):
    """Partial update for anamnesis."""

    queixa_principal: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    historia_pregressa: Optional[str] = Field(default=None, max_length=10000)
    historico_familiar: Optional[str] = Field(default=None, max_length=10000)
    medicacoes: Optional[str] = Field(default=None, max_length=5000)
    observacoes: Optional[str] = Field(default=None, max_length=10000)


# ---------------------------------------------------------------------------
# Treatment Plans
# ---------------------------------------------------------------------------

class TreatmentPlanCreate(StrictHttpModel):
    """Create a treatment plan for a patient."""

    titulo: str = Field(..., min_length=1, max_length=300)
    descricao: Optional[str] = Field(default=None, max_length=10000)
    data_inicio: date
    data_revisao: Optional[date] = None


class TreatmentPlanUpdate(StrictHttpModel):
    """Partial update for treatment plan."""

    titulo: Optional[str] = Field(default=None, min_length=1, max_length=300)
    descricao: Optional[str] = Field(default=None, max_length=10000)
    data_inicio: Optional[date] = None
    data_revisao: Optional[date] = None
    status: Optional[Literal["ativo", "concluido", "cancelado"]] = None


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

class GoalCreate(StrictHttpModel):
    """Create a therapeutic goal within a treatment plan."""

    descricao: str = Field(..., min_length=1, max_length=2000)
    prazo: Optional[date] = None


class GoalUpdate(StrictHttpModel):
    """Partial update for a goal.

    Valid `status` values mirror the DB enum
    `treatment_plan_goals.status` — `em_andamento` (note: spelled
    "em_andamento", not "em_progresso") aligns with the column literal.
    """

    descricao: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    status: Optional[Literal["pendente", "em_andamento", "concluido", "cancelado"]] = None
    observacoes: Optional[str] = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# Evolution Notes (SOAP or free-form)
# ---------------------------------------------------------------------------

class EvolutionNoteCreate(StrictHttpModel):
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


class EvolutionNoteUpdate(StrictHttpModel):
    """Partial update for an evolution note."""

    subjetivo: Optional[str] = Field(default=None, max_length=10000)
    objetivo: Optional[str] = Field(default=None, max_length=10000)
    avaliacao: Optional[str] = Field(default=None, max_length=10000)
    plano: Optional[str] = Field(default=None, max_length=10000)
    conteudo_livre: Optional[str] = Field(default=None, max_length=20000)


# ---------------------------------------------------------------------------
# Anamnese — write payloads carry `patient_id` to address the patient.
# ---------------------------------------------------------------------------

class AnamneseCreateWithPatient(AnamneseCreate):
    """`AnamneseCreate` shape plus the addressed `patient_id`.

    The therapist supplies `patient_id` at the HTTP boundary; uniqueness
    is enforced server-side per `(patient_id, therapist_id)` pair.
    """

    patient_id: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Treatment plans — write payload carries `patient_id`.
# ---------------------------------------------------------------------------

class TreatmentPlanCreateWithPatient(TreatmentPlanCreate):
    """`TreatmentPlanCreate` shape plus `patient_id`."""

    patient_id: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Evolution notes — write payload carries `patient_id`.
# ---------------------------------------------------------------------------

class EvolutionNoteCreateWithPatient(EvolutionNoteCreate):
    """`EvolutionNoteCreate` shape plus `patient_id`."""

    patient_id: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Crisis Alert review
# ---------------------------------------------------------------------------

class CrisisAlertReview(StrictHttpModel):
    """Therapist or admin reviews a crisis alert.

    `status` is the post-review verdict; `notas_revisao` is an optional
    review note captured for audit / patient-care continuity.
    """

    status: Literal["revisado", "falso_positivo", "encaminhado"]
    notas_revisao: Optional[str] = Field(default=None, max_length=10000)
