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
- `OpenAIToolOrchestrator` + `FakeToolOrchestrator` + `ToolOrchestrator`
  + `OrchestratorTool` + `make_tool_orchestrator` + `memory_key_for`
  + `append_memory` (social-wiring-absorption W1.E1 — openai_orchestrator.py;
  composes `LLMDispatcher`, surface-agnostic, session_id-keyed).
- `MessageStore` + `SupabaseMessageStore` + `FakeMessageStore`
  + `StoredMessage` + `DuplicateMessage` + `make_message_store`
  (W1.E1 — message_store.py; durable conversation_messages +
  UNIQUE(provider_message_id) dedup oracle).
- `ResponseRegistry` + `FakeResponseRegistry` + `make_response_registry`
  + `json_shape` + `shape_fingerprint` + `sample_key`
  (W1.E1 — response_registry.py; vendor-neutral connector-shape registry).
- `compute_content_stats` + `SchemaHint`
  (W1.E1 — content_stats.py; LLM-counting-trap fix, pure-logic).

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
from noctusai_lib.domain.chatbot.content_stats import (
    SchemaHint,
    compute_content_stats,
)
from noctusai_lib.domain.chatbot.llm_dispatcher import (
    AuditWriter,
    LLMDispatcher,
    ToolCall,
    ToolHandler,
    ToolResult,
)
from noctusai_lib.domain.chatbot.message_store import (
    DuplicateMessage,
    FakeMessageStore,
    MessageStore,
    StoredMessage,
    SupabaseMessageStore,
    make_message_store,
)
from noctusai_lib.domain.chatbot.openai_orchestrator import (
    FakeToolOrchestrator,
    OpenAIToolOrchestrator,
    OrchestratorTool,
    ToolOrchestrator,
    append_memory,
    make_tool_orchestrator,
    memory_key_for,
)
from noctusai_lib.domain.chatbot.response_registry import (
    FakeResponseRegistry,
    ResponseRegistry,
    json_shape,
    make_response_registry,
    sample_key,
    shape_fingerprint,
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
from noctusai_lib.domain.chatbot.prompt_fragments import (
    URL_IMMUTABILITY_FRAGMENT,
    with_url_immutability,
)

__all__ = [
    "AuditWriter",
    "BufferReader",
    "ConversationBufferService",
    "ConversationProcessor",
    "ConversationWorker",
    "DuplicateMessage",
    "FakeMessageStore",
    "FakeResponseRegistry",
    "FakeToolOrchestrator",
    "LLMDispatcher",
    "MessageStore",
    "OpenAIToolOrchestrator",
    "OrchestratorTool",
    "QueuedConversationMessage",
    "RedisBufferClient",
    "ResponseRegistry",
    "SchemaHint",
    "StoredMessage",
    "SupabaseMessageStore",
    "ToolCall",
    "ToolHandler",
    "ToolOrchestrator",
    "ToolResult",
    "URL_IMMUTABILITY_FRAGMENT",
    "append_memory",
    "compute_content_stats",
    "format_conversation_for_transcript",
    "json_shape",
    "make_in_memory_buffer_client",
    "make_message_store",
    "make_response_registry",
    "make_tool_orchestrator",
    "memory_key_for",
    "memory_to_chat_messages",
    "sample_key",
    "shape_fingerprint",
    "summarize_conversation",
    "with_url_immutability",
]
