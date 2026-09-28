"""HTTP-boundary schemas for the help-chat organ (`POST /api/ajuda/chat`).

Strict by default (`StrictHttpModel`) — an unknown key in the request body
422s immediately instead of being silently ignored (see
`noctusai_lib.api.schemas.StrictHttpModel`).
"""
from __future__ import annotations

from typing import Literal

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


__all__ = ["HelpChatMessage", "HelpChatRequest"]
