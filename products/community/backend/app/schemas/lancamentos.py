"""Schemas for the `lancamentos` (cashflow) domain — CONTRACT.md §Cashflow
+ dashboard, slice BE-C.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LANCAMENTO_TIPOS = ("entrada", "saida")
LANCAMENTO_ORIGENS = ("pagamento", "estorno", "manual")

#: Default categories always offered alongside whatever categories are
#: actually in use — CONTRACT.md §Cashflow: "(distinct, plus defaults
#: assinatura, estorno, plataforma, marketing, equipe, impostos, outros)".
DEFAULT_CATEGORIAS = (
    "assinatura", "estorno", "plataforma", "marketing", "equipe", "impostos", "outros",
)


class LancamentoCreate(BaseModel):
    """Request body for `POST /api/lancamentos`.

    `origem` is never accepted from the caller — the service forces it
    to `"manual"` (contract: "origem forced to manual").
    """

    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(..., pattern="^(" + "|".join(LANCAMENTO_TIPOS) + ")$")
    categoria: str = Field(..., min_length=1, max_length=60)
    descricao: str | None = Field(None, max_length=300)
    valor_centavos: int = Field(..., gt=0)
    data: date


class LancamentoUpdate(BaseModel):
    """Request body for `PATCH /api/lancamentos/{id}` — partial update.

    Only rows with `origem='manual'` accept this (contract 409 gate,
    enforced by the service, not here).
    """

    model_config = ConfigDict(extra="forbid")

    tipo: str | None = Field(None, pattern="^(" + "|".join(LANCAMENTO_TIPOS) + ")$")
    categoria: str | None = Field(None, min_length=1, max_length=60)
    descricao: str | None = Field(None, max_length=300)
    valor_centavos: int | None = Field(None, gt=0)
    data: date | None = None


class Lancamento(BaseModel):
    """Response body — list item / create / update."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo: str
    categoria: str
    descricao: str | None = None
    valor_centavos: int
    data: date
    origem: str
    pagamento_id: UUID | None = None
    membro_id: UUID | None = None
    membro_nome: str | None = None
    created_at: datetime


class LancamentoTotais(BaseModel):
    """Aggregated totals over the WHOLE filtered set (not just the page)."""

    entradas_centavos: int
    saidas_centavos: int
    saldo_centavos: int


class LancamentoListResponse(BaseModel):
    """Response body for `GET /api/lancamentos`."""

    items: list[Lancamento]
    total: int
    totais: LancamentoTotais


class CategoriasResponse(BaseModel):
    """Response body for `GET /api/lancamentos/categorias`."""

    items: list[str]
