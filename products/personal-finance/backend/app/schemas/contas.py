from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel
from datetime import datetime


class ContaCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=255)
    tipo: str = Field(..., pattern="^(corrente|poupanca|cartao_credito|investimento|carteira|emprestimo|outro)$")
    instituicao: Optional[str] = Field(default=None, max_length=255)
    saldo: Optional[float] = Field(default=0, ge=-99999999999999)
    moeda: Optional[str] = Field(default="BRL", max_length=3)
    cor: Optional[str] = Field(default="#6366f1", max_length=7)
    icone: Optional[str] = Field(default=None, max_length=10)


class ContaUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tipo: Optional[str] = Field(default=None, pattern="^(corrente|poupanca|cartao_credito|investimento|carteira|emprestimo|outro)$")
    instituicao: Optional[str] = Field(default=None, max_length=255)
    saldo: Optional[float] = None
    moeda: Optional[str] = Field(default=None, max_length=3)
    cor: Optional[str] = Field(default=None, max_length=7)
    icone: Optional[str] = Field(default=None, max_length=10)
    ativo: Optional[bool] = None
