from typing import Optional
from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)


class WatchlistItemCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    nome: Optional[str] = Field(default=None, max_length=255)
    alerta_preco_acima: Optional[float] = Field(default=None, gt=0)
    alerta_preco_abaixo: Optional[float] = Field(default=None, gt=0)
    notas: Optional[str] = Field(default=None, max_length=500)
