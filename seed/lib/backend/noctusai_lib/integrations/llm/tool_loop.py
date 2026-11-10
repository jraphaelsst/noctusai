"""
The platform's single tool loop — iterate `chat_with_tools` turns, dispatching
the model's tool calls to a handler, until it answers with text or hits the
iteration cap.

Async (see `tool_calling` for the sync/async decision). `run_tool_loop_sync`
is the thin bridge for the one synchronous caller (`LLMDispatcher.reply`).

`chat` is the turn function — `async (messages, tools) -> ChatToolsResponse`.
Bind credentials/provider/org into it with `functools.partial(chat_with_tools,
model=..., api_key=..., require_explicit_key=True)`; the loop itself knows
nothing about vendors, keys, budget or usage (those live in
`chat_with_tools` and the providers).

Handlers may be sync or async and return a `ToolResult`. `audit_writer` is
best-effort: an exception is logged and the loop continues.

Idempotency: a tool call is executed AT MOST ONCE per `call_id` within a loop.
If the model (or a retried/replayed response) repeats an id, the recorded
`ToolResult` is fed back and the handler and audit writer are NOT run again -
a side-effecting tool (send a message, book a visit) must not fire twice.
"""
from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Union

from .tool_calling import (
    ChatMessage,
    ChatToolsResponse,
    LLMUsage,
    ToolCall,
    ToolResult,
    ToolSpec,
    coerce_messages,
    coerce_tools,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ITERATIONS = 5
DEFAULT_FALLBACK_REPLY = "I had trouble completing that request. Could you summarize what you need again?"

ChatFn = Callable[[list[ChatMessage], list[ToolSpec]], Awaitable[ChatToolsResponse]]
ToolHandler = Callable[[ToolCall], Union[ToolResult, Awaitable[ToolResult]]]
AuditWriter = Callable[[ToolCall, ToolResult], None]


@dataclass
class ToolLoopResult:
    text: str
    messages: list[ChatMessage]
    iterations: int
    #: True when the cap was hit without a final text reply (`text` is then the text sent alongside tool calls, else the fallback).
    exhausted: bool = False
    usage: LLMUsage = field(default_factory=LLMUsage)
    tool_calls: list[ToolCall] = field(default_factory=list)


async def run_tool_loop(
    messages: Sequence[Union[ChatMessage, dict[str, Any]]],
    tools: Optional[Sequence[Union[ToolSpec, dict[str, Any]]]],
    tool_handler: Optional[ToolHandler],
    *,
    chat: ChatFn,
    max_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    fallback_reply: str = DEFAULT_FALLBACK_REPLY,
    audit_writer: Optional[AuditWriter] = None,
) -> ToolLoopResult:
    """Run the loop. No `tools` or no `tool_handler` ⇒ one plain turn."""
    history = coerce_messages(messages)
    specs = coerce_tools(tools)
    usage = LLMUsage()

    if not specs or tool_handler is None:
        response = await chat(history, [])
        return ToolLoopResult(response.text, history, 1, usage=response.usage)

    executed: list[ToolCall] = []
    recorded: dict[str, ToolResult] = {}  # call_id -> the result of its one execution
    # Reply text a model writes in the SAME response as a tool call. If its
    # next response is empty (it already said its piece), this is the reply.
    side_texts: list[str] = []
    for iteration in range(1, max_iterations + 1):
        response = await chat(history, specs)
        usage = usage + response.usage
        if not response.tool_calls:
            text = response.text
            if not (text and text.strip()) and side_texts:
                text = "\n\n".join(side_texts)
            return ToolLoopResult(text, history, iteration, usage=usage, tool_calls=executed)

        if response.text and response.text.strip():
            side_texts.append(response.text.strip())
        history.append(response.message)
        for call in response.tool_calls:
            if call.call_id and call.call_id in recorded:
                logger.warning("tool loop: repeated tool_call_id %s (%s); replaying the recorded result", call.call_id, call.name)
                history.append(ChatMessage.tool(recorded[call.call_id]))
                continue
            executed.append(call)
            result = tool_handler(call)
            if inspect.isawaitable(result):
                result = await result
            if call.call_id:
                recorded[call.call_id] = result
            if audit_writer is not None:
                try:
                    audit_writer(call, result)
                except Exception:
                    logger.exception("audit_writer failed for tool call %s (%s)", call.call_id, call.name)
            history.append(ChatMessage.tool(result))

    logger.warning("tool loop hit max iterations (%d) without a final reply", max_iterations)
    return ToolLoopResult(
        "\n\n".join(side_texts) if side_texts else fallback_reply, history, max_iterations, exhausted=True, usage=usage, tool_calls=executed
    )


def run_tool_loop_sync(*args: Any, **kwargs: Any) -> ToolLoopResult:
    """Drive `run_tool_loop` from synchronous code. Uses `asyncio.run` on a
    thread with no running loop; from inside a running loop it runs the
    coroutine on a private loop in a helper thread (blocking the caller, as
    a sync call must)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_tool_loop(*args, **kwargs))

    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["result"] = asyncio.run(run_tool_loop(*args, **kwargs))
        except BaseException as exc:  # re-raised on the caller's thread
            box["error"] = exc

    ctx = contextvars.copy_context()  # the helper thread keeps the caller's Supabase-breaker source
    t = threading.Thread(target=lambda: ctx.run(_runner))
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["result"]
