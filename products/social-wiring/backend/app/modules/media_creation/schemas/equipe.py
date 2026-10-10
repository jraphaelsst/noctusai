"""Equipe (the card hub's member source) — request schemas (esteira-contract.md 2.2 / 5.2)."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

Cor = Literal["primary", "secondary", "success", "warning", "destructive", "muted"]


class MembroCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=80)
    funcao: Optional[str] = Field(default=None, max_length=60)
    cor: Optional[Cor] = None
    user_id: Optional[uuid.UUID] = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("O nome não pode ser vazio.")
        return v


class MembroUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    funcao: Optional[str] = Field(default=None, max_length=60)
    cor: Optional[Cor] = None
    user_id: Optional[uuid.UUID] = None
    ativo: Optional[bool] = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("O nome não pode ser vazio.")
        return v
