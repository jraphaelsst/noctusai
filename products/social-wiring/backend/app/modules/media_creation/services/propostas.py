"""Server-side validation of the chat agent's headline proposals (estruturas-contract.md section 8.5).

PURE parser/validator: no DB access, no writes. UNI-1a persists ``cs_chat_propostas`` +
``cs_chat_proposta_estruturas`` + the events in the same pass that saves the assistant message.
This is the Python port of the FE ``components/geracao/chat/citacoes.ts :: extrairHeadlines`` -- the single
derivation (the FE parser is retired by FE-2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import UUID


@dataclass(frozen=True)
class EstruturaCitavel:
    id: UUID
    codigo: str  # the N shown to the model as "estrutura #N"
    formato: str


@dataclass(frozen=True)
class PropostaValidada:
    ordem: int
    headline: str
    gatilho: str | None
    estrutura_ids: tuple[UUID, ...]  # [0] = principal, len 1..3


@dataclass(frozen=True)
class ResultadoPropostas:
    propostas: tuple[PropostaValidada, ...]
    eventos: tuple[dict, ...]  # {"tipo": "citacao_rejeitada"|"formato_misturado"|"placeholder_remanescente", "contagem": int}


def extrair_propostas(texto: str, codigos_permitidos: Mapping[str, EstruturaCitavel]) -> ResultadoPropostas:
    raise NotImplementedError("EST-4a: implemented in the next commit (signature pinned for UNI-1a)")


__all__ = ["EstruturaCitavel", "PropostaValidada", "ResultadoPropostas", "extrair_propostas"]
