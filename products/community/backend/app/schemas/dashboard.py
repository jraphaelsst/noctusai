"""Schemas for `GET /api/dashboard` — CONTRACT.md §Cashflow + dashboard,
slice BE-C.

Every KPI/series definition is the CONTRACT's own literal wording
("Definitions (tests assert these)") — see
`app/services/dashboard_service.py` for the implementation of each.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PorPlanoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plano_id: UUID
    nome: str
    nivel_grupoterapia: str
    membros: int


class DashboardKpis(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membros_total: int
    membros_ativos: int
    por_plano: list[PorPlanoItem]
    mrr_centavos: int
    arpu_centavos: int
    em_carencia: int
    novos_mes: int
    cancelamentos_mes: int
    churn_mes_pct: float
    receita_mes_centavos: int
    saldo_mes_centavos: int
    conversao_pago_pct: float


class MensalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mes: str
    entradas_centavos: int
    saidas_centavos: int
    novos_membros: int
    cancelamentos: int
    mrr_centavos: int


class OrigemMembrosItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    origem: str
    membros: int


class StatusMembrosItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    membros: int


class GrupoterapiaDashboardItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sessao_id: UUID
    titulo: str
    inicio: datetime
    vagas_fala: int
    reservas: int


class DashboardSeries(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mensal: list[MensalItem]
    origem_membros: list[OrigemMembrosItem]
    status_membros: list[StatusMembrosItem]
    grupoterapia: list[GrupoterapiaDashboardItem]


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kpis: DashboardKpis
    series: DashboardSeries
    gerado_em: datetime
