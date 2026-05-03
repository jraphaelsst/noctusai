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
- `memory_to_chat_messages` + `format_conversation_for_transcript` +
  `image_bytes_to_data_url` + `audio_bytes_to_named_buffer`
  (Phase 5 — mappers.py).
- `summarize_conversation` (Phase 6 — summary.py; opt-in capability).
"""

from noctusai_lib.domain.conversation.buffer import (
    ConversationBufferService,
    QueuedConversationMessage,
    RedisBufferClient,
)
from noctusai_lib.domain.conversation.llm_dispatcher import (
    AuditWriter,
    LLMDispatcher,
    ToolCall,
    ToolHandler,
    ToolResult,
)
from noctusai_lib.domain.conversation.mappers import (
    audio_bytes_to_named_buffer,
    format_conversation_for_transcript,
    image_bytes_to_data_url,
    memory_to_chat_messages,
)
from noctusai_lib.domain.conversation.summary import summarize_conversation
from noctusai_lib.domain.conversation.worker import (
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
    "audio_bytes_to_named_buffer",
    "format_conversation_for_transcript",
    "image_bytes_to_data_url",
    "memory_to_chat_messages",
    "summarize_conversation",
]
