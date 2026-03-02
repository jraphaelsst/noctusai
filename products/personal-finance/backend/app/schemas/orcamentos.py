from typing import Optional, List
from pydantic import BaseModel, Field


class OrcamentoItemCreate(BaseModel):
    categoria_id: str
    valor_planejado: float = Field(..., gt=0)
    periodo_mes: str = Field(..., pattern=r"^\d{4}-\d{2}$")


class OrcamentoCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    metodo: Optional[str] = Field(default="zero_based", pattern="^(zero_based|envelope|50_30_20|personalizado)$")
    periodo: Optional[str] = Field(default="mensal", pattern="^(mensal|quinzenal|semanal)$")
    itens: Optional[List[OrcamentoItemCreate]] = None


class OrcamentoUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    metodo: Optional[str] = Field(default=None, pattern="^(zero_based|envelope|50_30_20|personalizado)$")
    periodo: Optional[str] = Field(default=None, pattern="^(mensal|quinzenal|semanal)$")
    ativo: Optional[bool] = None


class OrcamentoItemUpdate(BaseModel):
    valor_planejado: Optional[float] = Field(default=None, gt=0)
    rollover: Optional[float] = None
