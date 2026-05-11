"""Request/response schemas for `app.routers.onboarding`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class StepComplete(StrictHttpModel):
    step: str = Field(..., description="Nome do passo a completar")
    data: Optional[dict] = Field(default=None, description="Dados opcionais do passo")


class CompanyDetailsUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    cnpj: Optional[str] = Field(default=None, max_length=18)
    telefone: Optional[str] = Field(default=None, max_length=20)
    endereco: Optional[str] = Field(default=None, max_length=500)
