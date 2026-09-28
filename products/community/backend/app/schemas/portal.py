"""Schemas for `GET /api/portal/minha-conta` — contract §Member portal,
slice BE-A. `POST /api/portal/assinatura/cancelar` is slice BE-B's.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PortalMembro(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: str
    telefone: Optional[str] = None
    status: str
    entrou_em: Optional[datetime] = None


class PortalPlano(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    preco_centavos: int
    ciclo: str
    nivel_grupoterapia: Literal["nenhum", "ouvir", "falar"]


class PortalAssinatura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    estado: str
    metodo: str
    proxima_cobranca: Optional[date] = None
    pago_ate: Optional[datetime] = None
    carencia_ate: Optional[datetime] = None
    cancelada_em: Optional[datetime] = None
    gateway: str


class PortalPagamento(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    valor_centavos: int
    estado: str
    metodo: str
    vencimento: Optional[datetime] = None
    pago_em: Optional[datetime] = None
    url_fatura: Optional[str] = None


class PortalPlanoDisponivel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    descricao: Optional[str] = None
    preco_centavos: int
    ciclo: str
    nivel_grupoterapia: Literal["nenhum", "ouvir", "falar"]


class MinhaContaOut(BaseModel):
    """Response body for `GET /api/portal/minha-conta`."""

    membro: PortalMembro
    plano: Optional[PortalPlano] = None
    assinatura: Optional[PortalAssinatura] = None
    pagamentos: list[PortalPagamento]
    planos_disponiveis: list[PortalPlanoDisponivel]
