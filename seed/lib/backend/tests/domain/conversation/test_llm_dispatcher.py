"""LLMDispatcher tests — mocks the OpenAI client; exercises the
single-call path, the tool-loop path, audit_writer invocation, audit
exception swallowing, and max-iteration fallback.
"""

import json
from dataclasses import dataclass
from typing import Any

from noctusai_lib.domain.conversation.llm_dispatcher import (
    LLMDispatcher,
    ToolCall,
    ToolResult,
)


# ---- Fake OpenAI client ----------------------------------------------------


@dataclass
class _FakeFunc:
    name: str
    arguments: str


@dataclass
class _FakeToolCall:
    id: str
    function: _FakeFunc


@dataclass
class _FakeMessage:
    content: str | None = None
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]


class _FakeCompletions:
    def __init__(self, scripted: list[_FakeMessage]):
        self._scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs) -> _FakeResponse:
        self.calls.append(kwargs)
        message = self._scripted.pop(0)
        return _FakeResponse(choices=[_FakeChoice(message=message)])


class _FakeChat:
    def __init__(self, scripted: list[_FakeMessage]):
        self.completions = _FakeCompletions(scripted)


class _FakeClient:
    def __init__(self, scripted: list[_FakeMessage]):
        self.chat = _FakeChat(scripted)


# ---- Tests -----------------------------------------------------------------


def test_no_tool_path_returns_text_reply() -> None:
    client = _FakeClient([_FakeMessage(content="  hello world  ")])
    dispatcher = LLMDispatcher(client=client, model="gpt-test")

    reply = dispatcher.reply(messages=[{"role": "user", "content": "hi"}])

    assert reply == "hello world"  # whitespace stripped
    assert len(client.chat.completions.calls) == 1
    # Tools NOT passed when no tool_handler given
    assert "tools" not in client.chat.completions.calls[0]


def test_tool_loop_dispatches_then_returns_final_reply() -> None:
    # Script: model calls one tool → then replies with text.
    tool_call_msg = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall(
                id="call-1",
                function=_FakeFunc(name="lookup_property", arguments='{"code": "ONE0007"}'),
            )
        ],
    )
    final_msg = _FakeMessage(content="Found it!")
    client = _FakeClient([tool_call_msg, final_msg])
    dispatcher = LLMDispatcher(client=client, model="gpt-test")

    handled: list[ToolCall] = []

    def handler(call: ToolCall) -> ToolResult:
        handled.append(call)
        return ToolResult(call_id=call.call_id, content=json.dumps({"ok": True}))

    reply = dispatcher.reply(
        messages=[{"role": "user", "content": "find ONE0007"}],
        tools=[{"type": "function", "function": {"name": "lookup_property"}}],
        tool_handler=handler,
    )

    assert reply == "Found it!"
    assert len(handled) == 1
    assert handled[0].name == "lookup_property"
    assert handled[0].arguments == {"code": "ONE0007"}
    assert len(client.chat.completions.calls) == 2
    # Second call should include the assistant tool_calls + tool result.
    second_messages = client.chat.completions.calls[1]["messages"]
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in second_messages)
    assert any(
        m.get("role") == "tool" and m.get("tool_call_id") == "call-1"
        for m in second_messages
    )


def test_audit_writer_called_per_tool_call() -> None:
    tool_call_msg = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall(id="c1", function=_FakeFunc(name="t1", arguments="{}")),
            _FakeToolCall(id="c2", function=_FakeFunc(name="t2", arguments="{}")),
        ],
    )
    final_msg = _FakeMessage(content="done")
    client = _FakeClient([tool_call_msg, final_msg])
    dispatcher = LLMDispatcher(client=client, model="gpt-test")

    audited: list[tuple[str, str]] = []

    def handler(call: ToolCall) -> ToolResult:
        return ToolResult(call_id=call.call_id, content="ok")

    def auditor(call: ToolCall, result: ToolResult) -> None:
        audited.append((call.name, result.content))

    dispatcher.reply(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"type": "function", "function": {"name": "t1"}}],
        tool_handler=handler,
        audit_writer=auditor,
    )

    assert audited == [("t1", "ok"), ("t2", "ok")]


def test_audit_writer_exception_is_swallowed_and_loop_continues() -> None:
    tool_call_msg = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall(id="c1", function=_FakeFunc(name="t1", arguments="{}"))
        ],
    )
    final_msg = _FakeMessage(content="done")
    client = _FakeClient([tool_call_msg, final_msg])
    dispatcher = LLMDispatcher(client=client, model="gpt-test")

    def handler(call: ToolCall) -> ToolResult:
        return ToolResult(call_id=call.call_id, content="ok")

    def failing_auditor(call: ToolCall, result: ToolResult) -> None:
        raise RuntimeError("audit DB down")

    reply = dispatcher.reply(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"type": "function", "function": {"name": "t1"}}],
        tool_handler=handler,
        audit_writer=failing_auditor,
    )

    assert reply == "done"  # loop continued past audit failure


def test_max_iterations_returns_fallback_reply() -> None:
    # Build a script where the model ALWAYS calls a tool — never replies.
    forever_tool_call = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall(id="c", function=_FakeFunc(name="loop", arguments="{}"))
        ],
    )
    # max_tool_iterations=2 → 2 tool-calling turns, then exhaust.
    client = _FakeClient([forever_tool_call, forever_tool_call])
    dispatcher = LLMDispatcher(
        client=client,
        model="gpt-test",
        max_tool_iterations=2,
        fallback_reply="FALLBACK",
    )

    def handler(call: ToolCall) -> ToolResult:
        return ToolResult(call_id=call.call_id, content="ok")

    reply = dispatcher.reply(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"type": "function", "function": {"name": "loop"}}],
        tool_handler=handler,
    )

    assert reply == "FALLBACK"
    assert len(client.chat.completions.calls) == 2


def test_invalid_json_arguments_default_to_empty_dict() -> None:
    tool_call_msg = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall(
                id="c1",
                function=_FakeFunc(name="t", arguments="not json"),
            )
        ],
    )
    final_msg = _FakeMessage(content="done")
    client = _FakeClient([tool_call_msg, final_msg])
    dispatcher = LLMDispatcher(client=client, model="gpt-test")

    captured: list[ToolCall] = []

    def handler(call: ToolCall) -> ToolResult:
        captured.append(call)
        return ToolResult(call_id=call.call_id, content="ok")

    dispatcher.reply(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"type": "function", "function": {"name": "t"}}],
        tool_handler=handler,
    )

    assert captured[0].arguments == {}
