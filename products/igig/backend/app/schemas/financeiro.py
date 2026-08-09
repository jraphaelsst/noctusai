"""Contracts for Módulo 6 — financeiro, excedentes e DRE."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "FaturaCreate", "FaturaOut", "FaturaItemCreate", "FaturaItemOut",
    "ExcedenteOut", "DREOut", "InadimplenteOut",
]

TipoItem = Literal["mensalidade", "excedente", "desconto", "avulso"]


class FaturaCreate(StrictHttpModel):
    cliente_id: str
    contrato_id: str | None = None
    #: 'YYYY-MM' — the month being billed, not the due date.
    competencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    vencimento: str | None = None


class FaturaItemCreate(StrictHttpModel):
    descricao: str = Field(min_length=1, max_length=200)
    tipo: TipoItem = "mensalidade"
    quantidade: int = Field(default=1, ge=1)
    valor_unit: float = Field(default=0, ge=0)


class FaturaItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    fatura_id: str
    descricao: str
    tipo: str
    quantidade: int
    valor_unit: float


class FaturaOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    cliente_id: str
    contrato_id: str | None = None
    competencia: str
    valor_total: float = 0
    vencimento: str | None = None
    status: str = "aberta"
    pago_em: str | None = None


class ExcedenteOut(BaseModel):
    cliente_id: str
    cliente_nome: str
    contrato_id: str
    competencia: str
    contratados: int
    entregues: int
    excedentes: int
    valor_unitario: float
    valor_total: float
    #: The invoice this lands on — the month AFTER the work, per the spec.
    competencia_cobranca: str


class DREOut(BaseModel):
    cliente_id: str
    cliente_nome: str
    receita: float
    custo: float
    margem: float
    margem_percentual: float
    #: Non-empty ⇒ the margin is OVERSTATED (some hours could not be costed).
    alertas: list[str] = Field(default_factory=list)


class InadimplenteOut(BaseModel):
    fatura_id: str
    cliente_id: str
    competencia: str
    valor_total: float
    vencimento: str
    dias_atraso: int
