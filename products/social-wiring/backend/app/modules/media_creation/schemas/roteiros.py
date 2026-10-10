"""Roteiros (Roteiro Avançado) — request schemas, strict at the HTTP boundary.

Contract: ``projects/core-studio/specs/geracao-contract.md`` section 4.5 (#32-#40). The response
shapes are the plain dicts of ``roteiro_service.present_*`` (TS types in contract 4.8).

``fonte`` accepts the three contract values so ``web`` / ``link`` reach the service and answer the
contract's 422 "Fonte ainda não disponível" (not a generic enum error).
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

Fonte = Literal["ia", "web", "link"]
Duracao = Literal["auto", "1", "2", "3"]

MAX_HEADLINE = 1000
MAX_INSTRUCOES = 5000
MAX_RESPOSTA = 1000
MAX_CONTEUDO = 30000
MAX_NOME = 160


class RoteiroCreate(StrictHttpModel):
    marca_id: uuid.UUID
    headline_id: Optional[uuid.UUID] = None
    headline_texto: str = Field(min_length=1, max_length=MAX_HEADLINE)
    instrucoes: str = Field(default="", max_length=MAX_INSTRUCOES)
    fonte: Fonte = "ia"
    duracao: Duracao = "auto"
    brain_id: Optional[uuid.UUID] = None
    viral_id: Optional[uuid.UUID] = None
    gerar_perguntas: bool = True


class Resposta(StrictHttpModel):
    id: str = Field(min_length=1, max_length=64)
    resposta: str = Field(default="", max_length=MAX_RESPOSTA)


class RespostasUpdate(StrictHttpModel):
    respostas: list[Resposta] = Field(max_length=5)


class GerarRequest(StrictHttpModel):
    pular_perguntas: bool = False


class RoteiroUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=MAX_NOME)
    conteudo: Optional[str] = Field(default=None, max_length=MAX_CONTEUDO)
    expected_versao: int = Field(ge=1)

    @model_validator(mode="after")
    def _algo_a_salvar(self) -> "RoteiroUpdate":
        if self.nome is None and self.conteudo is None:
            raise ValueError("Informe o nome ou o conteúdo a salvar")
        if self.nome is not None and not self.nome.strip():
            raise ValueError("O nome não pode ser vazio")
        return self


class FeedbackRequest(StrictHttpModel):
    feedback: Literal["gostei", "nao_gostei"]
    motivo: Optional[str] = Field(default=None, max_length=1000)


class ReprocessarRequest(StrictHttpModel):
    instrucoes_adicionais: Optional[str] = Field(default=None, max_length=2000)


class ExcluirRequest(StrictHttpModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
