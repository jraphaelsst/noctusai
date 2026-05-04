"""Tools registry — payload shape, dispatch, error handling.

Ported from `whatsapp-google-scheduling/tests/test_openai_tools_registry.py`.

Source-side: a hand-rolled `ToolRegistry` class with `to_openai_payload()`
+ `dispatch(call, context)` method.
Product-side: the seed `LLMDispatcher` is the registry — `register_scheduling_tools`
attaches `tool_payload` (OpenAI shape), `tool_handler` (Callable[[ToolCall], ToolResult]),
and `tool_registry` to it. Same contract:
  - The registered tool's name/description/parameters round-trip into the
    OpenAI `tools=[...]` payload.
  - Dispatch invokes the handler with parsed args and serializes the
    result as JSON in `ToolResult.content`.
  - Unknown tool names → `{"error": "unknown_tool", "name": <name>}`.
  - Handler exceptions → `{"error": "tool_exception", "message": ...}`.

Test approach: register a one-off custom roster (an `add` tool + a `boom`
tool) so the registry mechanics are exercised in isolation from the real
scheduling tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from noctusai_lib.domain.chatbot import LLMDispatcher, ToolCall, ToolResult

from app.services.scheduling_tools import (
    SchedulingToolHandler,
    ToolContext,
    register_scheduling_tools,
    to_openai_tool_payload,
)


# ---------------------------------------------------------------------------
# Mock tools — minimal SchedulingToolHandler-shaped objects.
# ---------------------------------------------------------------------------


@dataclass
class _AdderTool:
    name: str = "add"
    description: str = "Adds two integers."
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }
    )

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        return ToolResult(
            call_id=args.get("__call_id", ""),
            content=json.dumps({"sum": args["a"] + args["b"]}),
        )


@dataclass
class _BrokenTool:
    name: str = "broken"
    description: str = "Always raises."
    parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    def __call__(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        raise RuntimeError("intentional")


def _empty_context() -> ToolContext:
    """Stub ToolContext — never inspected by the mock tools above."""
    return ToolContext(
        supabase=object(),  # type: ignore[arg-type]
        calendar_writer=object(),  # type: ignore[arg-type]
        routing_lookup=object(),  # type: ignore[arg-type]
        timezone_name="America/Sao_Paulo",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_to_openai_payload_emits_function_tool_shape() -> None:
    payload = to_openai_tool_payload([_AdderTool()])

    assert payload == [
        {
            "type": "function",
            "function": {
                "name": "add",
                "description": "Adds two integers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
            },
        }
    ]


def test_dispatch_runs_handler_and_serializes_result_as_json() -> None:
    dispatcher = LLMDispatcher(client=None, model="gpt-4o-mini")
    register_scheduling_tools(
        dispatcher,
        context_provider=_empty_context,
        tools=[_AdderTool()],
    )

    handler = dispatcher.tool_handler  # type: ignore[attr-defined]
    result = handler(
        ToolCall(call_id="call_1", name="add", arguments={"a": 2, "b": 3})
    )

    assert result.call_id == "call_1"
    assert json.loads(result.content) == {"sum": 5}


def test_dispatch_returns_unknown_tool_error_when_name_not_registered() -> None:
    dispatcher = LLMDispatcher(client=None, model="gpt-4o-mini")
    register_scheduling_tools(
        dispatcher,
        context_provider=_empty_context,
        tools=[_AdderTool()],
    )

    handler = dispatcher.tool_handler  # type: ignore[attr-defined]
    result = handler(ToolCall(call_id="x", name="missing", arguments={}))

    assert json.loads(result.content) == {
        "error": "unknown_tool",
        "name": "missing",
    }


def test_dispatch_captures_handler_exceptions_as_error_payload() -> None:
    dispatcher = LLMDispatcher(client=None, model="gpt-4o-mini")
    register_scheduling_tools(
        dispatcher,
        context_provider=_empty_context,
        tools=[_BrokenTool()],
    )

    handler = dispatcher.tool_handler  # type: ignore[attr-defined]
    result = handler(ToolCall(call_id="boom", name="broken", arguments={}))

    payload = json.loads(result.content)
    assert payload["error"] == "tool_exception"
    assert "intentional" in payload["message"]


def test_register_attaches_payload_and_registry_to_dispatcher() -> None:
    """`tool_registry` introspection seam — admin views need this."""
    dispatcher = LLMDispatcher(client=None, model="gpt-4o-mini")
    roster: list[SchedulingToolHandler] = [_AdderTool()]
    register_scheduling_tools(
        dispatcher, context_provider=_empty_context, tools=roster
    )

    assert dispatcher.tool_registry is roster  # type: ignore[attr-defined]
    payload = dispatcher.tool_payload  # type: ignore[attr-defined]
    assert isinstance(payload, list) and payload[0]["function"]["name"] == "add"
