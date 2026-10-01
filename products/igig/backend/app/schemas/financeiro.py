"""Contracts for Módulo 6 — financeiro, excedentes e DRE."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "FaturaCreate", "FaturaUpdate", "FaturaItemUpdate", "FaturaOut", "FaturaItemCreate", "FaturaItemOut",
    "ExcedenteOut", "DREOut", "InadimplenteOut",
    "GerarCompetenciaIn", "GerarCompetenciaOut", "ResumoFinanceiroOut",
    "EnviarFaturaOut",
]

TipoItem = Literal["mensalidade", "excedente", "desconto", "avulso"]


class FaturaCreate(StrictHttpModel):
    cliente_id: str
    contrato_id: str | None = None
    #: 'YYYY-MM' — the month being billed, not the due date.
    competencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    #: A real date — validated here so a malformed value 422s instead of
    #: falling through to the persistence layer's broad `PersistenceError`
    #: catch, which would misreport it as a duplicate invoice (finding #7).
    vencimento: date | None = None


class FaturaUpdate(StrictHttpModel):
    """PATCH body — only the header fields a person may correct by hand.
    `valor_total` is derived from the lines and `status` moves through the
    action endpoints, so neither is accepted here."""

    competencia: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    vencimento: date | None = None


class FaturaItemUpdate(StrictHttpModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=200)
    quantidade: int | None = Field(default=None, ge=1)
    valor_unit: float | None = Field(default=None, ge=0)


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
    enviada_em: str | None = None


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


class GerarCompetenciaIn(StrictHttpModel):
    #: 'YYYY-MM' — the invoice month being closed.
    competencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class GerarCompetenciaOut(BaseModel):
    #: Invoices this call actually created.
    criadas: list[FaturaOut] = Field(default_factory=list)
    #: Contracts that already had a (non-cancelled) invoice for the month —
    #: reported, not re-billed. Idempotency made visible to the caller.
    existentes: list[FaturaOut] = Field(default_factory=list)


class ResumoFinanceiroOut(BaseModel):
    competencia: str | None = None
    mrr: float
    a_receber: float
    recebido: float
    inadimplente_valor: float
    inadimplente_qtd: int


class EnviarFaturaOut(BaseModel):
    fatura: FaturaOut
    message_id: str
