"""A TEST-ONLY mirror of agents' `ChannelContexto` request schema (`products/agents/backend/app/schemas/channels.py`).

SW must never import agents at runtime (cross-product), but a contexto SW renders that agents' `extra="forbid"`
schema rejects is a 422 and a lead left without a reply (julia-v2 W0). So the tests validate against this copy, and
`tests/services/test_julia_contexto_agents_schema.py` fails the day the real schema and this copy disagree
(drift test) -- update this file from the agents file when it does.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from noctusai_lib.api import StrictHttpModel
from pydantic import Field, model_validator

CONTEXTO_MAX_CHARS = 80_000
Operacao = Literal["compra", "aluguel"]
FerramentaName = Literal["buscar_imoveis", "detalhes_imovel", "horarios_visita", "consultar_empreendimento"]
AcaoName = Literal[
    "salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "captacao", "encerrar", "consentimento_credito", "handoff"
]


class ContextoPergunta(StrictHttpModel):
    chave: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=300)
    dica: str | None = Field(default=None, max_length=600)
    categoria: str = Field(..., min_length=1, max_length=64)
    qualificatoria: bool
    operacao: Operacao | None = None


class ContextoCredito(StrictHttpModel):
    ativo: bool
    consentimento: bool | None = None


class ContextoEstado(StrictHttpModel):
    slots: dict[str, str] = Field(default_factory=dict)
    operacao: Literal["compra", "aluguel", "administracao"] | None = None
    interacao_id: UUID
    encerrado: bool
    credito: ContextoCredito | None = None


class ChannelContexto(StrictHttpModel):
    hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    conhecimento_md: str = Field(default="", max_length=60_000)
    perguntas: list[ContextoPergunta] = Field(default_factory=list, max_length=8)
    estado: ContextoEstado
    ferramentas: list[FerramentaName] = Field(default_factory=list)
    acoes: list[AcaoName] = Field(default_factory=list)
    agora: datetime
    fuso: Literal["America/Sao_Paulo"]

    @model_validator(mode="after")
    def _size_cap(self) -> "ChannelContexto":
        if len(self.model_dump_json()) > CONTEXTO_MAX_CHARS:
            raise ValueError("contexto_grande")
        return self
