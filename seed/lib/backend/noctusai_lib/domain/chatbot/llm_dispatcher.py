"""OpenAI tool-loop dispatcher — runs the chat-completion + tool-call
loop until the model produces a text reply or hits the iteration cap.

Since Lais S0 the loop is NOT implemented here: `reply` is a synchronous
facade over the platform's single tool loop
(`integrations.llm.tool_loop.run_tool_loop`) driving `chat_with_tools`
through an `OpenAIClientAdapter` around the injected client — same wire
calls as before, one loop instead of four.

Ported from
`whatsapp-google-scheduling/app/services/openai/conversation.py:ConversationGptService`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 5.

Seed contract:

    dispatcher = LLMDispatcher(client=openai_client, model="gpt-4o-mini")
    reply_text = dispatcher.reply(
        messages=[{"role": "system", ...}, {"role": "user", ...}, ...],
        tools=tools_payload,        # OpenAI-shaped list[dict] | None
        tool_handler=lambda call: ToolResult(call_id=call.call_id, content=...),
        audit_writer=lambda call, result: audit_record_db.insert(...),  # optional
    )

Pre-built `messages` (system blocks + memory_to_chat_messages output)
let the seed dispatcher stay product-agnostic: pt-BR system prompts,
pt-BR user-context blocks, etc. all live in the consumer.

`audit_writer` is the seam for `noctusai_lib.domain.ai.tool_audit` (see
`KB § PATTERNS/llm-tool-audit.md`). Default no-op so the dispatcher
works even when the consumer doesn't (yet) wire audit persistence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIClientAdapter
from noctusai_lib.integrations.llm.tool_calling import (
    ToolCall,
    ToolResult,
    chat_with_tools,
)
from noctusai_lib.integrations.llm.tool_loop import (
    DEFAULT_FALLBACK_REPLY,
    DEFAULT_MAX_TOOL_ITERATIONS,
    run_tool_loop_sync,
)

logger = logging.getLogger(__name__)

# `ToolCall` / `ToolResult` are the seed-wide normalized types
# (`integrations.llm.tool_calling`), re-exported here for existing importers.
__all__ = [
    "DEFAULT_FALLBACK_REPLY",
    "DEFAULT_MAX_TOOL_ITERATIONS",
    "AuditWriter",
    "LLMDispatcher",
    "ToolCall",
    "ToolHandler",
    "ToolResult",
]

ToolHandler = Callable[[ToolCall], ToolResult]
AuditWriter = Callable[[ToolCall, ToolResult], None]


def _noop_audit_writer(call: ToolCall, result: ToolResult) -> None:
    """Default audit writer — does nothing. Replace with
    `noctusai_lib.domain.ai.tool_audit.make_audit_writer(...)` to
    persist tool-call audit rows."""


class LLMDispatcher:
    """Stateless OpenAI tool-loop dispatcher. Safe to share across
    requests (the OpenAI client itself is the only shared state)."""

    def __init__(
        self,
        client: Any,
        model: str,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
        fallback_reply: str = DEFAULT_FALLBACK_REPLY,
    ):
        self.client = client
        self.model = model
        self.max_tool_iterations = max_tool_iterations
        self.fallback_reply = fallback_reply

    def reply(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_handler: ToolHandler | None = None,
        audit_writer: AuditWriter | None = None,
    ) -> str:
        """Run the chat loop. Returns the final assistant text (stripped).

        - If `tools` is None or `tool_handler` is None, the dispatcher
          makes a single non-tool-using completion call.
        - Otherwise, loops up to `max_tool_iterations` times: on each
          iteration, asks the model; if the model calls tools, dispatches
          them via `tool_handler` and feeds results back; if the model
          replies with text, returns it.
        - On loop exhaustion, returns `fallback_reply` and logs a warning.
        """
        writer = audit_writer if audit_writer is not None else _noop_audit_writer
        adapter = OpenAIClientAdapter(self.client)

        async def _chat(msgs, specs):
            return await chat_with_tools(
                msgs, specs, model=self.model, provider_impl=adapter
            )

        result = run_tool_loop_sync(
            messages,
            tools,
            tool_handler,
            chat=_chat,
            max_iterations=self.max_tool_iterations,
            fallback_reply=self.fallback_reply,
            audit_writer=writer,
        )
        return result.text
