"""Chatbot framework — Redis-backed conversation buffer + debounce + worker
+ LLM tool-loop dispatcher + optional summary.

Lifted 2026-05-03 by `projects/whatsapp-seed-absorption/` Phases 3-6 from
`whatsapp-google-scheduling/app/services/{conversation_buffer_service,
openai/conversation,openai/summary,openai/mappers}.py` +
`app/workers/conversation_worker.py`.

Provider-agnostic by design — channel-neutral. Pair with
`noctusai_lib.integrations.whatsapp` (or any future Twilio / Cloud API
connector) for the inbound + outbound side.

Public surface:
- `ConversationBufferService` + `QueuedConversationMessage` + `RedisBufferClient`
  (Phase 3 — buffer.py).
- `ConversationWorker` + `ConversationProcessor` + `BufferReader` (Phase 4 — worker.py).
- `LLMDispatcher` + `ToolCall` + `ToolResult` + `ToolHandler` + `AuditWriter`
  (Phase 5 — llm_dispatcher.py).
- `memory_to_chat_messages` + `format_conversation_for_transcript`
  (Phase 5 — mappers.py).
- `summarize_conversation` (Phase 6 — summary.py; opt-in capability).

LLM-input helpers (`image_bytes_to_data_url`, `audio_bytes_to_named_buffer`)
moved to `noctusai_lib.integrations.llm.inputs` — vendor-shape, not
chatbot-domain.
"""

from noctusai_lib.domain.chatbot.buffer import (
    ConversationBufferService,
    QueuedConversationMessage,
    RedisBufferClient,
    make_in_memory_buffer_client,
)
from noctusai_lib.domain.chatbot.llm_dispatcher import (
    AuditWriter,
    LLMDispatcher,
    ToolCall,
    ToolHandler,
    ToolResult,
)
from noctusai_lib.domain.chatbot.mappers import (
    format_conversation_for_transcript,
    memory_to_chat_messages,
)
from noctusai_lib.domain.chatbot.summary import summarize_conversation
from noctusai_lib.domain.chatbot.worker import (
    BufferReader,
    ConversationProcessor,
    ConversationWorker,
)

__all__ = [
    "AuditWriter",
    "BufferReader",
    "ConversationBufferService",
    "ConversationProcessor",
    "ConversationWorker",
    "LLMDispatcher",
    "QueuedConversationMessage",
    "RedisBufferClient",
    "ToolCall",
    "ToolHandler",
    "ToolResult",
    "format_conversation_for_transcript",
    "make_in_memory_buffer_client",
    "memory_to_chat_messages",
    "summarize_conversation",
]
