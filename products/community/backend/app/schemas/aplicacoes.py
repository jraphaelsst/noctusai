"""Schemas for the `aplicacoes` domain (manager-defined questions +
public submissions + review) — contract §Aplicações."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.membros import Membro

_PHONE_RE = r"^\+[1-9]\d{7,14}$"

PERGUNTA_TIPOS = ("texto", "texto_longo", "escolha_unica", "escolha_multipla", "booleano")
APLICACAO_STATUSES = ("pendente", "aprovada", "rejeitada")


# ── Perguntas (manager-defined questions) ───────────────────────────────


class PerguntaCreate(BaseModel):
    """Request body for `POST /api/aplicacoes/perguntas`."""

    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(..., min_length=1, max_length=500)
    tipo: str = Field(..., pattern="^(" + "|".join(PERGUNTA_TIPOS) + ")$")
    opcoes: list[str] = Field(default_factory=list)
    obrigatoria: bool = True
    ordem: int = 0
    ativa: bool = True


class PerguntaUpdate(BaseModel):
    """Request body for `PATCH /api/aplicacoes/perguntas/{id}` — partial update."""

    model_config = ConfigDict(extra="forbid")

    pergunta: str | None = Field(None, min_length=1, max_length=500)
    tipo: str | None = Field(None, pattern="^(" + "|".join(PERGUNTA_TIPOS) + ")$")
    opcoes: list[str] | None = None
    obrigatoria: bool | None = None
    ordem: int | None = None
    ativa: bool | None = None


class Pergunta(BaseModel):
    """Response body for a question."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pergunta: str
    tipo: str
    opcoes: list[str]
    obrigatoria: bool
    ordem: int
    ativa: bool


class PerguntaListResponse(BaseModel):
    items: list[Pergunta]
    total: int


# ── Aplicações (submissions) ────────────────────────────────────────────


class AplicacaoPublicaCreate(BaseModel):
    """Request body for the PUBLIC `POST /api/aplicacoes`."""

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    telefone: str | None = Field(None, pattern=_PHONE_RE)
    respostas: dict[str, Any] = Field(default_factory=dict)


class AplicacaoPublicaOut(BaseModel):
    """Response body for the PUBLIC `POST /api/aplicacoes`."""

    id: UUID
    status: str


class Aplicacao(BaseModel):
    """Response body for list / detail / review actions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: str
    telefone: str | None = None
    respostas: dict[str, Any]
    status: str
    motivo: str | None = None
    revisado_em: datetime | None = None
    membro_id: UUID | None = None
    created_at: datetime


class AplicacaoResumo(BaseModel):
    pendente: int = 0
    aprovada: int = 0
    rejeitada: int = 0


class AplicacaoListResponse(BaseModel):
    items: list[Aplicacao]
    total: int
    resumo: AplicacaoResumo


class AplicacaoAprovarRequest(BaseModel):
    """Request body for `POST /api/aplicacoes/{id}/aprovar`."""

    model_config = ConfigDict(extra="forbid")

    plano_id: UUID | None = None
    ativar: bool = False


class AplicacaoAprovarResponse(BaseModel):
    aplicacao: Aplicacao
    membro: Membro


class AplicacaoRejeitarRequest(BaseModel):
    """Request body for `POST /api/aplicacoes/{id}/rejeitar`."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(..., min_length=1, max_length=500)
