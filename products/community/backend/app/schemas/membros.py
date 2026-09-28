"""Schemas for the `membros` domain — contract §Membros."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

_PHONE_RE = r"^\+[1-9]\d{7,14}$"

MEMBRO_STATUSES = ("pendente", "ativo", "atrasado", "pausado", "cancelado")


class MembroCreate(BaseModel):
    """Request body for `POST /api/membros`."""

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    telefone: str | None = Field(None, pattern=_PHONE_RE)
    status: str = Field("pendente", pattern="^(" + "|".join(MEMBRO_STATUSES) + ")$")
    plano_id: UUID | None = None
    origem: str = Field(..., pattern="^(checkout|aplicacao|convite)$")
    tags: list[str] = Field(default_factory=list)
    observacoes: str | None = Field(None, max_length=2000)


class MembroUpdate(BaseModel):
    """Request body for `PATCH /api/membros/{id}` — partial update."""

    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(None, min_length=1, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = Field(None, pattern=_PHONE_RE)
    plano_id: UUID | None = None
    tags: list[str] | None = None
    observacoes: str | None = Field(None, max_length=2000)


class MembroStatusUpdate(BaseModel):
    """Request body for `POST /api/membros/{id}/status`."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., pattern="^(" + "|".join(MEMBRO_STATUSES) + ")$")
    motivo: str | None = Field(None, max_length=500)


class Membro(BaseModel):
    """Response body for list / detail / create / update / status."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: str
    telefone: str | None = None
    status: str
    plano_id: UUID | None = None
    plano_nome: str | None = None
    origem: str
    tags: list[str]
    user_id: UUID | None = None
    observacoes: str | None = None
    entrou_em: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MembroResumo(BaseModel):
    """Per-status counts for the tab badges — contract §Membros."""

    pendente: int = 0
    ativo: int = 0
    atrasado: int = 0
    pausado: int = 0
    cancelado: int = 0


class MembroListResponse(BaseModel):
    """Paginated list response for `GET /api/membros`."""

    items: list[Membro]
    total: int
    resumo: MembroResumo


# ── Relationship timeline — contract §Identity, slice BE-A ─────────────

EVENTO_TIPOS_CRIAVEIS = ("nota", "contato")


class EventoCreate(BaseModel):
    """Request body for `POST /api/membros/{id}/eventos`."""

    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(..., pattern="^(" + "|".join(EVENTO_TIPOS_CRIAVEIS) + ")$")
    descricao: str = Field(..., min_length=1, max_length=2000)


class Evento(BaseModel):
    """Response body for a `community.membro_eventos` row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo: str
    descricao: str
    dados: dict
    autor_id: UUID | None = None
    autor_nome: str | None = None
    created_at: datetime


class EventoListResponse(BaseModel):
    """Paginated list response for `GET /api/membros/{id}/eventos`."""

    items: list[Evento]
    total: int


# ── Access provisioning — contract §Identity, slice BE-A ───────────────


class AcessoOut(BaseModel):
    """Response body for `POST /api/membros/{id}/acesso` (201)."""

    email: str
    senha_temporaria: str
