"""OpenAI tool-loop dispatcher — runs the chat-completion + tool-call
loop until the model produces a text reply or hits the iteration cap.

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

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ITERATIONS = 5
DEFAULT_FALLBACK_REPLY = (
    "I had trouble completing that request. Could you summarize what you need again?"
)


@dataclass(frozen=True)
class ToolCall:
    """Normalized OpenAI tool-call from the model."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """Tool-handler return value. `content` is sent back to the model
    as the tool message body — typically a JSON string but plain text
    is fine."""

    call_id: str
    content: str


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
        if tools is None or tool_handler is None:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages
            )
            return (response.choices[0].message.content or "").strip()

        writer = audit_writer if audit_writer is not None else _noop_audit_writer
        # Local mutable copy — we append to it across iterations.
        loop_messages = list(messages)

        for _iteration in range(self.max_tool_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=loop_messages,
                tools=tools,
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []

            if not tool_calls:
                return (message.content or "").strip()

            loop_messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                arguments_raw = tc.function.arguments or "{}"
                try:
                    arguments = json.loads(arguments_raw)
                except json.JSONDecodeError:
                    arguments = {}
                call = ToolCall(call_id=tc.id, name=tc.function.name, arguments=arguments)
                result = tool_handler(call)
                try:
                    writer(call, result)
                except Exception:
                    logger.exception(
                        "audit_writer failed for tool call %s (%s)",
                        call.call_id,
                        call.name,
                    )
                loop_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "content": result.content,
                    }
                )

        logger.warning(
            "LLMDispatcher tool loop hit max iterations (%d) without a final reply",
            self.max_tool_iterations,
        )
        return self.fallback_reply
