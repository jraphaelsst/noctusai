"""Request/response schemas for `app.routers.onboarding`."""
from __future__ import annotations

from typing import Literal, Optional

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
    org_type: Optional[Literal["individual", "company"]] = Field(
        default=None,
        description="Org type — 'individual' or 'company'. Updates the organization record.",
    )
    number_of_users: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of users (>= 1). Required when org_type='company'.",
    )
