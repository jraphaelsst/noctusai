"""
Pydantic schemas for the rewards router.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel

RewardType = Literal["cashback", "verba_mkt"]
AccrualStatus = Literal["pendente", "liberado", "utilizado", "cancelado"]
RedemptionStatus = Literal["pendente", "aprovado", "rejeitado", "pago"]


class RewardRuleOut(StrictHttpModel):
    id: str
    org_id: Optional[str] = None
    nome: str
    descricao: Optional[str] = None
    tipo: RewardType
    cashback_pct: float
    aplicavel_categorias: list[str] = Field(default_factory=list)
    aplicavel_produtos: list[str] = Field(default_factory=list)
    aplicavel_distribuidores: list[str] = Field(default_factory=list)
    valor_minimo_pedido: float = 0
    quantidade_minima: int = 0
    ativo: bool = True
    valido_de: Optional[date] = None
    valido_ate: Optional[date] = None


class RewardLedgerEntry(StrictHttpModel):
    id: str
    distributor_id: str
    regra_id: Optional[str] = None
    tipo: RewardType
    valor: float
    moeda: str = "BRL"
    source_pedido_id: Optional[str] = None
    source_relatorio_id: Optional[str] = None
    status: AccrualStatus
    descricao: Optional[str] = None
    accrued_at: Optional[datetime] = None


class RewardLedgerOut(StrictHttpModel):
    data: list[RewardLedgerEntry] = Field(default_factory=list)
    summary: dict[str, float] = Field(default_factory=dict)


class RewardRulesListOut(StrictHttpModel):
    data: list[RewardRuleOut] = Field(default_factory=list)


class RedemptionRequestIn(StrictHttpModel):
    distributor_id: str
    tipo: RewardType
    valor: float
    pedido_ref: Optional[str] = None


class RedemptionProcessIn(StrictHttpModel):
    status: Literal["aprovado", "rejeitado", "pago"]
    review_notes: Optional[str] = None


class RedemptionOut(StrictHttpModel):
    id: str
    org_id: Optional[str] = None
    distributor_id: str
    tipo: RewardType
    valor: float
    pedido_ref: Optional[str] = None
    status: RedemptionStatus
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    requested_at: Optional[datetime] = None
    requested_by: Optional[str] = None


__all__ = [
    "RewardType",
    "AccrualStatus",
    "RedemptionStatus",
    "RewardRuleOut",
    "RewardLedgerEntry",
    "RewardLedgerOut",
    "RewardRulesListOut",
    "RedemptionRequestIn",
    "RedemptionProcessIn",
    "RedemptionOut",
]
