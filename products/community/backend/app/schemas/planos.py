"""Schemas for the `planos` (paid tiers) domain — contract §Planos.

Pydantic strict at the HTTP boundary: every inbound model rejects extra
fields (`extra="forbid"`) rather than silently dropping them.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Entitlements(BaseModel):
    """Entitlements shape (v1, additive later) — contract §Tables."""

    model_config = ConfigDict(extra="forbid")

    feed: bool = False
    forum: bool = False
    chat: bool = False
    eventos: bool = False
    conteudo_ids: list[str] = Field(default_factory=list)
    grupos_whatsapp: list[str] = Field(default_factory=list)
    conteudo_todos: bool = False


class PlanoCreate(BaseModel):
    """Request body for `POST /api/planos`."""

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=80)
    descricao: str | None = Field(None, max_length=500)
    preco_centavos: int = Field(..., ge=0)
    ciclo: str = Field(..., pattern="^(mensal|anual)$")
    entitlements: Entitlements = Field(default_factory=Entitlements)
    ordem: int = 0
    ativo: bool = True


class PlanoUpdate(BaseModel):
    """Request body for `PATCH /api/planos/{id}` — partial update."""

    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(None, min_length=1, max_length=80)
    descricao: str | None = Field(None, max_length=500)
    preco_centavos: int | None = Field(None, ge=0)
    ciclo: str | None = Field(None, pattern="^(mensal|anual)$")
    entitlements: Entitlements | None = None
    ordem: int | None = None
    ativo: bool | None = None


class Plano(BaseModel):
    """Response body for list / detail / create / update."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    descricao: str | None = None
    preco_centavos: int
    ciclo: str
    entitlements: Entitlements
    ativo: bool
    ordem: int
    membros_ativos: int
    created_at: datetime
    updated_at: datetime


class PlanoListResponse(BaseModel):
    """Paginated list response for `GET /api/planos`."""

    items: list[Plano]
    total: int
