"""Schemas for Ninho Vazio billing — projects/ninho-vazio/CONTRACT.md
§Billing — slice BE-B and §Member portal (`POST /api/portal/assinatura/cancelar`).

Every model is a `StrictHttpModel` (`extra="forbid"`): an unknown key is a
422, never silently dropped. Response models are built field-by-field
(`from_row`), so a new DB column never leaks onto the wire unannounced.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from noctusai_lib.api.schemas import StrictHttpModel
from pydantic import Field


class ConfiguracoesCobranca(StrictHttpModel):
    """`GET`/`PUT /api/cobranca/configuracoes` — request and response."""

    dias_carencia: int = Field(..., ge=0, le=60)
    automacoes_ativas: bool


class RelatorioRotina(StrictHttpModel):
    nome: str
    pulado: bool
    examinadas: int
    alteradas: list[str]
    erros: list[str]


class ExecutarRotinaResponse(StrictHttpModel):
    """`POST /api/cobranca/executar-rotina`."""

    relatorios: list[RelatorioRotina]


class PlanosPadraoResponse(StrictHttpModel):
    """`POST /api/planos/padrao` — tier names, in the contract's table order."""

    criados: list[str]
    existentes: list[str]


class CancelarAssinaturaPortalRequest(StrictHttpModel):
    """`POST /api/portal/assinatura/cancelar` body."""

    motivo: Optional[str] = Field(None, max_length=500)


class AssinaturaPortal(StrictHttpModel):
    """The member-facing `assinatura` object (CONTRACT.md §Member portal —
    shared with `GET /api/portal/minha-conta`)."""

    id: UUID
    estado: str
    metodo: str
    proxima_cobranca: Optional[date] = None
    pago_ate: Optional[datetime] = None
    carencia_ate: Optional[datetime] = None
    cancelada_em: Optional[datetime] = None
    gateway: str

    @classmethod
    def from_row(cls, row: dict) -> "AssinaturaPortal":
        return cls(**{name: row.get(name) for name in cls.model_fields})
