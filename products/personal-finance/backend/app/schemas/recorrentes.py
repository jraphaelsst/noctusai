from typing import Optional
from pydantic import BaseModel, Field


class RecorrenteCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    valor: float = Field(..., gt=0)
    conta_id: Optional[str] = None
    categoria_id: Optional[str] = None
    tipo: str = Field(..., pattern="^(receita|despesa)$")
    frequencia: str = Field(..., pattern="^(semanal|quinzenal|mensal|bimestral|trimestral|semestral|anual)$")
    dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    proxima_data: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_automatico: Optional[bool] = False
    comerciante: Optional[str] = Field(default=None, max_length=255)
    lembrete_dias: Optional[int] = Field(default=3, ge=0, le=30)


class RecorrenteUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    valor: Optional[float] = Field(default=None, gt=0)
    conta_id: Optional[str] = None
    categoria_id: Optional[str] = None
    tipo: Optional[str] = Field(default=None, pattern="^(receita|despesa)$")
    frequencia: Optional[str] = Field(default=None, pattern="^(semanal|quinzenal|mensal|bimestral|trimestral|semestral|anual)$")
    dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    proxima_data: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_automatico: Optional[bool] = None
    comerciante: Optional[str] = Field(default=None, max_length=255)
    lembrete_dias: Optional[int] = Field(default=None, ge=0, le=30)
    ativo: Optional[bool] = None
