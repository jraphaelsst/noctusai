"""Wire contracts for Orçamentos, Produtos e Serviços and Contratos (wave 2, slice A).

Shapes are `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-2-contract.md`
§ Shapes. Every INBOUND model is `StrictHttpModel` (`extra="forbid"`): a typo'd
field must be a 422, not a silently dropped write. Server-computed fields
(`quantidade_mensal`, `subtotal`, every total) are NOT accepted inbound — the
client cannot tell the server what a proposal costs.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "Secao",
    "Formato",
    "ProdutoServicoCreate",
    "ProdutoServicoUpdate",
    "LimitesEscopoIn",
    "OrcamentoItemIn",
    "OrcamentoCreate",
    "OrcamentoUpdate",
    "CalcularIn",
    "RecusarIn",
    "GerarContratoIn",
]

Secao = Literal["criacao_conteudo", "gestao_conta"]
Formato = Literal["feed", "carrossel", "reels", "story", "artigo", "video"]


class ProdutoServicoCreate(StrictHttpModel):
    secao: Secao
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=2000)
    preco_base: float = Field(default=0, ge=0)
    unidade: str = Field(default="unidade", min_length=1, max_length=40)
    horas_estimadas: float = Field(default=0, ge=0)
    #: The pauta format a criação product delivers (migration 020).
    formato: Formato | None = None
    ativo: bool = True
    ordem: int = Field(default=0, ge=0)


class ProdutoServicoUpdate(StrictHttpModel):
    secao: Secao | None = None
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=2000)
    preco_base: float | None = Field(default=None, ge=0)
    unidade: str | None = Field(default=None, min_length=1, max_length=40)
    horas_estimadas: float | None = Field(default=None, ge=0)
    formato: Formato | None = None
    ativo: bool | None = None
    ordem: int | None = Field(default=None, ge=0)


class LimitesEscopoIn(StrictHttpModel):
    revisoes_incluidas: int = Field(default=2, ge=0, le=100)
    valor_excedente: float = Field(default=0, ge=0)
    observacoes: str | None = Field(default=None, max_length=2000)


class OrcamentoItemIn(StrictHttpModel):
    produto_servico_id: str | None = None
    secao: Secao
    descricao: str = Field(min_length=1, max_length=300)
    preco_unitario: float = Field(ge=0)
    recorrente: bool = False
    #: Weekday bitmask: seg=1 ter=2 qua=4 qui=8 sex=16 sab=32 dom=64.
    dias_semana: int = Field(default=0, ge=0, le=127)
    qtd_por_dia: int = Field(default=0, ge=0, le=50)
    #: Used only when NOT recorrente.
    quantidade: int = Field(default=1, ge=0, le=10000)
    ordem: int | None = Field(default=None, ge=0)


class CalcularIn(StrictHttpModel):
    itens: list[OrcamentoItemIn] = Field(default_factory=list, max_length=200)
    desconto: float = Field(default=0, ge=0)


class OrcamentoCreate(StrictHttpModel):
    negocio_id: str = Field(min_length=1)
    titulo: str | None = Field(default=None, max_length=200)
    #: NULL = never expires (owner decision 2026-09-22).
    validade: date | None = None
    itens: list[OrcamentoItemIn] = Field(default_factory=list, max_length=200)
    desconto: float = Field(default=0, ge=0)
    limites_escopo: LimitesEscopoIn | None = None
    observacoes: str | None = Field(default=None, max_length=4000)


class OrcamentoUpdate(StrictHttpModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    validade: date | None = None
    itens: list[OrcamentoItemIn] | None = Field(default=None, max_length=200)
    desconto: float | None = Field(default=None, ge=0)
    limites_escopo: LimitesEscopoIn | None = None
    observacoes: str | None = Field(default=None, max_length=4000)


class RecusarIn(StrictHttpModel):
    motivo: str = Field(max_length=2000)


class GerarContratoIn(StrictHttpModel):
    modalidade_assinatura: Literal["digital", "fisica"]
    dia_vencimento: int | None = Field(default=None, ge=1, le=31)
    #: Física only: how many signed copies the closing clause declares.
    vias: int = Field(default=2, ge=1, le=10)
    #: Digital only: who signs. Defaults to the lead's e-mail.
    signatario_email: str | None = Field(default=None, max_length=200)
