"""Help chat — the reusable "AI specialist bubble" seam.

A single opt-in router factory (`create_help_chat_router`) that any product
mounts to get a floating, always-available chat where the signed-in user
talks to an AI specialist scoped to THAT product's own knowledge — nothing
else (no customer-data access; knowledge-only). A product enables it with
one `app.include_router(create_help_chat_router(...))` call plus a
knowledge markdown file; the frontend counterpart is
`@noctusai/lib`'s `HelpChatBubble` organ
(`seed/lib/frontend/src/components/help-chat/`).

See `seed/lib/backend/noctusai_lib/domain/help_chat/README.md` for the full
usage guide (knowledge-file format, streaming/error contract, budget +
rate-limit behaviour).
"""
from .router import HelpChatStreamFn, create_help_chat_router
from .schemas import HelpChatAvaliacaoRequest, HelpChatMessage, HelpChatRequest
from .service import (
    ERROR_IA_INDISPONIVEL,
    ERROR_IA_NAO_CONFIGURADA,
    ERROR_LIMITE_DE_MENSAGENS,
    ERROR_ORCAMENTO_IA_EXCEDIDO,
    HelpChatKnowledgeMissing,
    HelpChatRateLimiter,
    MARCADOR_CONCLUSAO,
    MarcadorFilter,
    build_conversation_messages,
    build_system_prompt,
    load_knowledge,
)
from .store import (
    FakeHelpChatStore,
    HelpChatConversaAlheia,
    HelpChatStore,
    HelpChatStoreError,
    SupabaseHelpChatStore,
    make_help_chat_store,
)

__all__ = [
    "FakeHelpChatStore",
    "HelpChatAvaliacaoRequest",
    "HelpChatConversaAlheia",
    "HelpChatStore",
    "HelpChatStoreError",
    "MARCADOR_CONCLUSAO",
    "MarcadorFilter",
    "SupabaseHelpChatStore",
    "make_help_chat_store",
    "create_help_chat_router",
    "HelpChatStreamFn",
    "HelpChatMessage",
    "HelpChatRequest",
    "HelpChatKnowledgeMissing",
    "HelpChatRateLimiter",
    "build_conversation_messages",
    "build_system_prompt",
    "load_knowledge",
    "ERROR_IA_INDISPONIVEL",
    "ERROR_IA_NAO_CONFIGURADA",
    "ERROR_LIMITE_DE_MENSAGENS",
    "ERROR_ORCAMENTO_IA_EXCEDIDO",
]
