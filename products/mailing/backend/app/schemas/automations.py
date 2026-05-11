"""Pydantic schemas for automations."""
from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class AutomationCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)


class AutomationUpdate(StrictHttpModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None


class StepCreate(StrictHttpModel):
    tipo: str
    config: dict = Field(default_factory=dict)
    posicao: Optional[int] = None


class StepUpdate(StrictHttpModel):
    tipo: Optional[str] = None
    config: Optional[dict] = None


class StepReorder(StrictHttpModel):
    step_ids: list[str]


class EnrollContacts(StrictHttpModel):
    contact_ids: list[str]
