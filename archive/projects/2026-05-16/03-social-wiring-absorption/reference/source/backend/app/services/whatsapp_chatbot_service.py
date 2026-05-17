"""Back-compat re-export — the OpenAI tool-calling chatbot now lives in
:mod:`app.services.chatbot_service` and is surface-agnostic
(WhatsApp + platform chat share the same orchestration loop).

Importers can keep using ``WhatsAppChatbotService`` from here without
churning; new code should import :class:`ChatbotService` directly from
``app.services.chatbot_service``.
"""
from __future__ import annotations

from app.services.chatbot_service import (  # noqa: F401
    ChatbotService,
    ChatbotTool,
    MAX_MEMORY_ITEMS,
    MAX_TOOL_ITERATIONS,
    MEMORY_PREFIX,
    MEMORY_TTL_SECONDS,
    SYSTEM_PROMPT,
    WhatsAppChatbotService,
)

__all__ = [
    "ChatbotService",
    "ChatbotTool",
    "MAX_MEMORY_ITEMS",
    "MAX_TOOL_ITERATIONS",
    "MEMORY_PREFIX",
    "MEMORY_TTL_SECONDS",
    "SYSTEM_PROMPT",
    "WhatsAppChatbotService",
]
