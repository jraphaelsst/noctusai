"""Chat (Geração BE-6) request bodies -- ``specs/geracao-contract.md`` sections 4.6 / 4.8.

Responses are plain dicts shaped like the TS types (``Conversa`` / ``Mensagem`` / ``Mencao`` /
``Memoria``); only inbound bodies are Pydantic (``StrictHttpModel``: ``extra="forbid"``).
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

Agente = Literal["headline", "roteiro"]
MencaoTipo = Literal["pesquisa", "cerebro", "biblioteca", "headline"]

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
    agente: Agente
    titulo: Optional[str] = Field(default=None, max_length=MAX_TITULO_CHARS)

    _t = field_validator("titulo", mode="before")(_strip)


class ConversaRename(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=MAX_TITULO_CHARS)

    _t = field_validator("titulo", mode="before")(_strip)


class MensagemCreate(StrictHttpModel):
    conteudo: str = Field(min_length=1, max_length=MAX_MENSAGEM_CHARS)
    referencias: list[ReferenciaIn] = Field(default_factory=list, max_length=MAX_REFERENCIAS)

    _c = field_validator("conteudo", mode="before")(_strip)


class MemoriaCreate(StrictHttpModel):
    marca_id: uuid.UUID
    texto: str = Field(min_length=1, max_length=MAX_MEMORIA_CHARS)

    _t = field_validator("texto", mode="before")(_strip)


__all__ = [
    "Agente", "ConversaCreate", "ConversaRename", "MAX_MEMORIA_CHARS", "MAX_MENSAGEM_CHARS",
    "MAX_REFERENCIAS", "MAX_TITULO_CHARS", "MemoriaCreate", "MencaoTipo", "MensagemCreate", "ReferenciaIn",
]
