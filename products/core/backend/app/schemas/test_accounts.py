"""Request/response schemas for `app.routers.test_accounts`."""
from __future__ import annotations

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class TestAccountCreate(StrictHttpModel):
    nome: str = Field(..., max_length=200, description="Nome do usuário de teste")
    email: str = Field(..., description="Email do usuário de teste")
    password: str = Field(..., min_length=6, description="Senha do usuário de teste")
    empresa: str = Field(..., max_length=200, description="Nome da organização de teste")
