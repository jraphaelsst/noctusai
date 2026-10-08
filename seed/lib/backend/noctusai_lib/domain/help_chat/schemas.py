"""HTTP-boundary schemas for the help-chat organ (`POST /api/ajuda/chat` and
`POST /api/ajuda/avaliacao`).

Strict by default (`StrictHttpModel`) — an unknown key in the request body
422s immediately instead of being silently ignored (see
`noctusai_lib.api.schemas.StrictHttpModel`).
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class HelpChatMessage(StrictHttpModel):
    role: Literal["user", "assistant"]
    content: str


class HelpChatRequest(StrictHttpModel):
    messages: list[HelpChatMessage]
    #: The frontend's current route pathname (`window.location.pathname`),
    #: e.g. `/negocios/123`. Optional — a product embedding the bubble
    #: outside a router, or an early first render, may omit it.
    pagina_atual: str | None = None
    #: Identifies the conversation for storage + rating. The frontend always
    #: sends it (one uuid per "Nova conversa"); when absent the server
    #: generates one so the request still works (its turns are then stored
    #: under a conversation the client cannot rate).
    conversa_id: UUID | None = None


class HelpChatAvaliacaoRequest(StrictHttpModel):
    """End-of-attendance rating: 1-5 + optional comment. Last rating wins."""

    conversa_id: UUID
    nota: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)
    #: `concluido` = the model closed the attendance; `inatividade` = the
    #: person went idle and the frontend asked for the rating.
    motivo: Literal["concluido", "inatividade"]


__all__ = ["HelpChatAvaliacaoRequest", "HelpChatMessage", "HelpChatRequest"]
