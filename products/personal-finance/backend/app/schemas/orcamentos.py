from typing import Optional, List
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class OrcamentoItemCreate(StrictHttpModel):
    categoria_id: str
    valor_planejado: float = Field(..., gt=0)
    periodo_mes: str = Field(..., pattern=r"^\d{4}-\d{2}$")


class OrcamentoCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=255)
    metodo: Optional[str] = Field(default="zero_based", pattern="^(zero_based|envelope|50_30_20|personalizado)$")
    periodo: Optional[str] = Field(default="mensal", pattern="^(mensal|quinzenal|semanal)$")
    itens: Optional[List[OrcamentoItemCreate]] = None


class OrcamentoUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    metodo: Optional[str] = Field(default=None, pattern="^(zero_based|envelope|50_30_20|personalizado)$")
    periodo: Optional[str] = Field(default=None, pattern="^(mensal|quinzenal|semanal)$")
    ativo: Optional[bool] = None


class OrcamentoItemUpdate(StrictHttpModel):
    valor_planejado: Optional[float] = Field(default=None, gt=0)
    rollover: Optional[float] = None
