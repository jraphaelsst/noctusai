"""Schemas for the grupoterapia (group therapy sessions) domain — contract
§Grupoterapia (slice BE-D).

Pydantic strict at the HTTP boundary: every inbound model rejects extra
fields (`extra="forbid"`) rather than silently dropping them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

StatusSessao = Literal["agendada", "realizada", "cancelada"]
StatusReserva = Literal["confirmada", "cancelada"]
NivelGrupoterapia = Literal["nenhum", "ouvir", "falar"]
AcessoGrupoterapia = Literal["bloqueado", "ouvir", "falar"]


# ── Staff ────────────────────────────────────────────────────────────────


class SessaoCreate(BaseModel):
    """Request body for `POST /api/grupoterapia/sessoes`."""

    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(..., min_length=1, max_length=120)
    descricao: str | None = Field(None, max_length=2000)
    inicio: datetime
    duracao_minutos: int = Field(default=90, ge=15, le=480)
    link_sala: str | None = Field(None, max_length=500)
    vagas_fala: int = Field(default=8, ge=0, le=100)


class SessaoUpdate(BaseModel):
    """Request body for `PATCH /api/grupoterapia/sessoes/{id}` — partial update."""

    model_config = ConfigDict(extra="forbid")

    titulo: str | None = Field(None, min_length=1, max_length=120)
    descricao: str | None = Field(None, max_length=2000)
    inicio: datetime | None = None
    duracao_minutos: int | None = Field(None, ge=15, le=480)
    link_sala: str | None = Field(None, max_length=500)
    vagas_fala: int | None = Field(None, ge=0, le=100)
    status: StatusSessao | None = None


class Sessao(BaseModel):
    """Response body for list / detail / create / update — contract shape."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    titulo: str
    descricao: str | None = None
    inicio: datetime
    duracao_minutos: int
    link_sala: str | None = None
    vagas_fala: int
    status: StatusSessao
    reservas: int
    created_at: datetime
    updated_at: datetime


class SessaoListResponse(BaseModel):
    items: list[Sessao]
    total: int


class Reserva(BaseModel):
    """One row of `GET /api/grupoterapia/sessoes/{id}/reservas`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membro_id: UUID
    membro_nome: str | None = None
    status: StatusReserva
    created_at: datetime


class ReservaListResponse(BaseModel):
    items: list[Reserva]
    total: int


# ── Member portal ───────────────────────────────────────────────────────


class SessaoPortalItem(BaseModel):
    """One row of `GET /api/portal/grupoterapia` — contract shape."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    titulo: str
    descricao: str | None = None
    inicio: datetime
    duracao_minutos: int
    status: StatusSessao
    vagas_fala: int
    vagas_restantes: int
    minha_reserva: bool
    acesso: AcessoGrupoterapia
    link_sala: str | None = None


class SessaoPortalListResponse(BaseModel):
    nivel: NivelGrupoterapia
    items: list[SessaoPortalItem]


class ReservaStatus(BaseModel):
    """Response body for `POST /api/portal/grupoterapia/{id}/reserva`."""

    status: Literal["confirmada"]
