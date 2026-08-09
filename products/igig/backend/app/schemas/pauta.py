"""Pydantic contracts for Módulo 3 — calendário editorial e copywriting."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "Formato",
    "Funil",
    "PautaCreate",
    "PautaUpdate",
    "PautaOut",
    "CalendarioResponse",
    "PecaOut",
]

#: Mirrors the CHECK constraints on both backends. Kept as Literals so an
#: invalid value is a readable 422 at the edge rather than a DB error.
Formato = Literal["feed", "carrossel", "reels", "story", "artigo", "video"]
Funil = Literal["topo", "meio", "fundo"]


class PautaCreate(StrictHttpModel):
    cliente_id: str
    titulo: str = Field(min_length=1, max_length=200)
    marca_id: str | None = None
    formato: Formato | None = None
    funil: Funil | None = None
    linha_editorial: str | None = Field(default=None, max_length=80)
    copy_texto: str | None = None
    direcao_video: str | None = None
    canal: str | None = Field(default=None, max_length=60)
    data_publicacao: str | None = None


class PautaUpdate(StrictHttpModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    marca_id: str | None = None
    formato: Formato | None = None
    funil: Funil | None = None
    linha_editorial: str | None = Field(default=None, max_length=80)
    copy_texto: str | None = None
    direcao_video: str | None = None
    canal: str | None = Field(default=None, max_length=60)
    #: Rescheduling from the calendar's drag-and-drop lands here.
    data_publicacao: str | None = None


class PecaOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    pauta_id: str
    storage_key: str
    nome_arquivo: str | None = None
    mime_type: str | None = None
    tamanho_bytes: int | None = None
    ordem: int = 0


class PautaOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    cliente_id: str
    marca_id: str | None = None
    titulo: str
    formato: str | None = None
    funil: str | None = None
    linha_editorial: str | None = None
    copy_texto: str | None = None
    direcao_video: str | None = None
    canal: str | None = None
    data_publicacao: str | None = None
    publicado_em: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    #: Live character count for the legenda. Computed server-side so the
    #: calendar's list view can sort/flag on it without every client
    #: re-deriving the rule — and so "what counts as a character" has one
    #: definition rather than one per screen.
    caracteres_copy: int = 0


class CalendarioResponse(BaseModel):
    """A date window of pautas.

    `inicio`/`fim` are echoed back so a client rendering a month grid can
    verify it got the window it asked for rather than assuming.
    """

    inicio: str
    fim: str
    itens: list[PautaOut]
