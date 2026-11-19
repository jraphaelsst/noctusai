"""Chat (Geração BE-6) request bodies -- ``specs/geracao-contract.md`` sections 4.6 / 4.8.

Responses are plain dicts shaped like the TS types (``Conversa`` / ``Mensagem`` / ``Mencao`` /
``Memoria``); only inbound bodies are Pydantic (``StrictHttpModel``: ``extra="forbid"``).
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

#: DEPRECATED (estruturas-contract 6.5): there is ONE unified chat. ``headline`` / ``roteiro`` are the legacy values of
#: conversations created before it; they are still accepted on input and ignored -- every read answers ``unificado``.
Agente = Literal["headline", "roteiro", "unificado"]
MencaoTipo = Literal["pesquisa", "cerebro", "biblioteca", "headline", "estrutura"]

MAX_MENSAGEM_CHARS = 8000
MAX_REFERENCIAS = 10
MAX_TITULO_CHARS = 100
MAX_MEMORIA_CHARS = 500


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class ReferenciaIn(StrictHttpModel):
    """An ``@`` mention. ``id`` is an uuid, except ``biblioteca`` (``perfil:<uuid>`` = all videos
    of a profile) and ``pesquisa`` (a variable slug = every approved item of that variable)."""

    tipo: MencaoTipo
    id: str = Field(min_length=1, max_length=120)


class ConversaCreate(StrictHttpModel):
    marca_id: uuid.UUID
    #: accepted for one release, ignored: the conversation is always created ``unificado``
    agente: Optional[Agente] = None
    titulo: Optional[str] = Field(default=None, max_length=MAX_TITULO_CHARS)

    _t = field_validator("titulo", mode="before")(_strip)


class ConversaRename(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=MAX_TITULO_CHARS)

    _t = field_validator("titulo", mode="before")(_strip)


class MensagemCreate(StrictHttpModel):
    conteudo: str = Field(min_length=1, max_length=MAX_MENSAGEM_CHARS)
    referencias: list[ReferenciaIn] = Field(default_factory=list, max_length=MAX_REFERENCIAS)

    _c = field_validator("conteudo", mode="before")(_strip)


class EscolherIn(StrictHttpModel):
    """``POST /chat/conversas/{id}/escolher`` -- EXACTLY one of ``proposta_id`` (a headline the assistant proposed) or
    ``headline_id`` (an already-saved headline picked with ``@``). Nothing else: the defaults (duracao ``auto``, CTA at
    the start) are fixed and adjusted later in the roteiro page."""

    proposta_id: Optional[uuid.UUID] = None
    headline_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def _exatamente_um(self) -> "EscolherIn":
        if (self.proposta_id is None) == (self.headline_id is None):
            raise ValueError("Informe exatamente um entre proposta_id e headline_id")
        return self


#: One batch pick: the parser caps a reply at 10 headlines + 5 roteiros, the saga runs one claim per id.
MAX_SELECIONADAS = 10


class SelecionarIn(StrictHttpModel):
    """``POST /chat/propostas/selecionar`` -- the batch pick (``criacao-pipeline-contract.md`` 4): N proposals of the caller's
    conversations, each claimed and run through the same saga as ``escolher``. Unique ids; nothing else is accepted."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_SELECIONADAS)

    @field_validator("ids")
    @classmethod
    def _unicos(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("Os ids devem ser únicos")
        return v


class MemoriaCreate(StrictHttpModel):
    marca_id: uuid.UUID
    texto: str = Field(min_length=1, max_length=MAX_MEMORIA_CHARS)

    _t = field_validator("texto", mode="before")(_strip)


__all__ = [
    "Agente", "ConversaCreate", "ConversaRename", "EscolherIn", "MAX_MEMORIA_CHARS", "MAX_MENSAGEM_CHARS",
    "MAX_REFERENCIAS", "MAX_TITULO_CHARS", "MemoriaCreate", "MencaoTipo", "MensagemCreate", "ReferenciaIn",
]
