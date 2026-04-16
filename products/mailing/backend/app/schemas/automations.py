"""Pydantic schemas for automations."""
from typing import Optional
from pydantic import BaseModel, Field


class AutomationCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)


class AutomationUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None


class StepCreate(BaseModel):
    tipo: str
    config: dict = Field(default_factory=dict)
    posicao: Optional[int] = None


class StepUpdate(BaseModel):
    tipo: Optional[str] = None
    config: Optional[dict] = None


class StepReorder(BaseModel):
    step_ids: list[str]


class EnrollContacts(BaseModel):
    contact_ids: list[str]
