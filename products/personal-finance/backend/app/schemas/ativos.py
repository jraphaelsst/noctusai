from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class AtivoCreate(StrictHttpModel):
    carteira_id: str
    ticker: str = Field(..., min_length=1, max_length=20)
    nome: Optional[str] = Field(default=None, max_length=255)
    tipo: str = Field(..., pattern="^(acao|etf|fii|bdr|renda_fixa|tesouro_direto|fundo|crypto|cdb|lci_lca|debenture|outro)$")
    setor: Optional[str] = Field(default=None, max_length=100)


class AtivoUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, max_length=255)
    tipo: Optional[str] = Field(default=None, pattern="^(acao|etf|fii|bdr|renda_fixa|tesouro_direto|fundo|crypto|cdb|lci_lca|debenture|outro)$")
    setor: Optional[str] = Field(default=None, max_length=100)


class OperacaoCreate(StrictHttpModel):
    carteira_id: str
    ativo_id: Optional[str] = None
    ticker: str = Field(..., min_length=1, max_length=20)
    tipo: str = Field(..., pattern="^(compra|venda|dividendo|jcp|rendimento|split|bonificacao|amortizacao|transferencia)$")
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    quantidade: Optional[float] = Field(default=None, ge=0)
    preco_unitario: Optional[float] = Field(default=None, ge=0)
    taxas: Optional[float] = Field(default=0, ge=0)
    valor_total: float
    notas: Optional[str] = Field(default=None, max_length=500)
