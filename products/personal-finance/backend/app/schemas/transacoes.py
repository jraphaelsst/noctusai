from typing import Optional, List
from pydantic import BaseModel, Field


class TransacaoCreate(BaseModel):
    conta_id: str
    categoria_id: Optional[str] = None
    conta_destino_id: Optional[str] = None
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    valor: float = Field(..., gt=0)
    tipo: str = Field(..., pattern="^(receita|despesa|transferencia)$")
    descricao: Optional[str] = Field(default=None, max_length=500)
    comerciante: Optional[str] = Field(default=None, max_length=255)
    notas: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[str]] = None


class TransacaoUpdate(BaseModel):
    conta_id: Optional[str] = None
    categoria_id: Optional[str] = None
    conta_destino_id: Optional[str] = None
    data: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    valor: Optional[float] = Field(default=None, gt=0)
    tipo: Optional[str] = Field(default=None, pattern="^(receita|despesa|transferencia)$")
    descricao: Optional[str] = Field(default=None, max_length=500)
    comerciante: Optional[str] = Field(default=None, max_length=255)
    notas: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[str]] = None
