"""Pydantic contracts for the Cliente surface (Módulo 1).

``StrictHttpModel`` on the request side means an unknown key is a 422 rather
than a silently ignored field — the platform default per
``KB § PATTERNS/backend/pydantic-strict-http.md``. A typo'd field name that
silently does nothing is the failure this prevents.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "StatusCliente",
    "ClienteCreate",
    "ClienteUpdate",
    "ClienteOut",
    "ClienteListResponse",
]

#: Mirrors the CHECK constraint in both schema files. Keeping it a Literal
#: means an invalid status is rejected at the HTTP boundary with a readable
#: 422 instead of reaching the DB and coming back as a constraint error.
StatusCliente = Literal["prospect", "ativo", "inativo", "inadimplente"]


class ClienteCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=200)
    nicho: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    origem: str | None = Field(default=None, max_length=120)
    observacoes: str | None = None
    # Not settable on create: a client always enters the funnel as a prospect
    # and is promoted by the Módulo 1 signature automation, never by hand at
    # creation time.


class ClienteUpdate(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    nicho: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    origem: str | None = Field(default=None, max_length=120)
    observacoes: str | None = None
    status: StatusCliente | None = None


class ClienteOut(BaseModel):
    """Response shape. Tolerant of extra columns so a schema addition doesn't
    break the endpoint before the model catches up."""

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    nome: str
    nicho: str | None = None
    email: str | None = None
    telefone: str | None = None
    status: str = "prospect"
    origem: str | None = None
    observacoes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ClienteListResponse(BaseModel):
    itens: list[ClienteOut]
    total: int
