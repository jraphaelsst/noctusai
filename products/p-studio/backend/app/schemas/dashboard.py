"""Dashboard executivo (spec § 1).

Nenhuma tabela: todos os indicadores são agregados sobre negócios, captações,
produções e lançamentos. Era exatamente isto que o protótipo não conseguia
fazer sem um backend — os nove números eram literais em `mock-data.ts`.
"""
from typing import Optional

from pydantic import BaseModel


class SerieMensal(BaseModel):
    mes: str      # "2026-07"
    label: str    # "Jul"
    valor: float


class SerieSemanal(BaseModel):
    semana: str   # "S1"
    captacoes: int


class EtapaResumo(BaseModel):
    etapa: str
    label: str
    quantidade: int
    valor: float


class DashboardOut(BaseModel):
    # Os nove indicadores da spec
    captacoes_mes: int = 0
    entregas_mes: int = 0
    servicos_andamento: int = 0
    faturamento_mes: float = 0
    a_receber: float = 0
    ticket_medio: float = 0
    clientes_ativos: int = 0
    prazo_medio_dias: Optional[float] = None
    taxa_recorrencia: float = 0

    # Séries dos gráficos
    receita_por_mes: list[SerieMensal] = []
    captacoes_por_semana: list[SerieSemanal] = []
    funil: list[EtapaResumo] = []
