"""`chat_with_tools` — provider-neutral tool calling (Lais slice S0).

Each provider's mapping is tested against RECORDED wire fixtures, no network:
the request the provider builds is asserted verbatim and the response is
parsed from a payload shaped exactly like the vendor's (validated through the
vendor SDK's own response model). The FakeProvider is deterministic. Stubs are
DI stubs of the vendor SDK client (the provider's own per-key pool), never
patches of our own code.
"""
from __future__ import annotations

import pytest
from anthropic.types import Message as AnthropicMessage
from openai.types.chat import ChatCompletion

from noctusai_lib.integrations.llm import (
    ChatMessage,
    FakeProvider,
    InMemoryUsageSink,
    LLMConfig,
    LLMNotConfigured,
    ToolCall,
    ToolCallingNotImplemented,
    ToolResult,
    ToolSpec,
    chat_with_tools,
    configure_llm,
    register,
    run_tool_loop,
)
from noctusai_lib.integrations.llm import client as _llm_client
from noctusai_lib.integrations.llm import registry as _registry
from noctusai_lib.integrations.llm.providers.anthropic_provider import (
    AnthropicProvider,
    build_anthropic_request,
    parse_anthropic_response,
)
from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider
from noctusai_lib.integrations.llm.providers.openai_provider import (
    OpenAIProvider,
    build_openai_request,
    parse_openai_response,
)

LOOKUP = ToolSpec(
    "lookup_property",
    "Find a property by code",
    {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
)

HISTORY = [
    ChatMessage.system("You are Julia.", cache=True),
    ChatMessage.user("find ONE0007"),
    ChatMessage.assistant("Looking.", [ToolCall("call_1", "lookup_property", {"code": "ONE0007"})]),
    ChatMessage.tool(ToolResult("call_1", '{"ok": true}')),
]

# ── recorded OpenAI fixtures ────────────────────────────────────────────────

OPENAI_TOOL_TURN = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup_property", "arguments": '{"code": "ONE0007"}'},
                    }
                ],
            },
        }
    ],
    "usage": {
        "prompt_tokens": 1000,
        "completion_tokens": 20,
        "total_tokens": 1020,
        "prompt_tokens_details": {"cached_tokens": 600},
    },
}

OPENAI_TEXT_TURN = {
    "id": "chatcmpl-2",
    "object": "chat.completion",
    "created": 2,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "  Found it!  "}}
    ],
    "usage": {"prompt_tokens": 50, "completion_tokens": 3, "total_tokens": 53},
}

# ── recorded Anthropic fixtures ─────────────────────────────────────────────

ANTHROPIC_TOOL_TURN = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250929",
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "content": [
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "toolu_1", "name": "lookup_property", "input": {"code": "ONE0007"}},
    ],
    "usage": {
        "input_tokens": 100,
        "output_tokens": 30,
        "cache_read_input_tokens": 400,
        "cache_creation_input_tokens": 0,
    },
}

ANTHROPIC_TEXT_TURN = {
    "id": "msg_2",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250929",
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "content": [{"type": "text", "text": "Found it!"}],
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


# ── OpenAI ──────────────────────────────────────────────────────────────────


def test_openai_request_mapping():
    req = build_openai_request(HISTORY, [LOOKUP], model="gpt-4o-mini", temperature=0.2, max_tokens=300)
    assert req == {
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": "You are Julia."},
            {"role": "user", "content": "find ONE0007"},
            {
                "role": "assistant",
                "content": "Looking.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup_property", "arguments": '{"code": "ONE0007"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup_property",
                    "description": "Find a property by code",
                    "parameters": LOOKUP.parameters,
                },
            }
        ],
    }


def test_openai_tool_choice_and_no_tools():
    req = build_openai_request(HISTORY, [LOOKUP], model="m", tool_choice="lookup_property")
    assert req["tool_choice"] == {"type": "function", "function": {"name": "lookup_property"}}
    assert "tools" not in build_openai_request(HISTORY, [], model="m", tool_choice="required")


def test_openai_response_parsing_tool_turn():
    r = parse_openai_response(ChatCompletion.model_validate(OPENAI_TOOL_TURN), model="gpt-4o-mini")
    assert r.finish_reason == "tool_calls"
    assert r.tool_calls == (ToolCall("call_1", "lookup_property", {"code": "ONE0007"}),)
    assert r.text == ""
    assert (r.usage.prompt_tokens, r.usage.completion_tokens, r.usage.cache_read_tokens) == (1000, 20, 600)
    assert r.usage.cost_usd is not None and r.usage.cost_usd > 0  # gpt-4o-mini is priced
    assert r.model_version == "gpt-4o-mini-2024-07-18"
    # history echo keeps the vendor's raw argument string
    assert r.message.tool_calls[0].raw_arguments == '{"code": "ONE0007"}'


def test_openai_response_parsing_text_turn_and_unpriced_cost():
    r = parse_openai_response(ChatCompletion.model_validate(OPENAI_TEXT_TURN), model="not-in-catalog")
    assert (r.text, r.finish_reason, r.tool_calls) == ("Found it!", "stop", ())
    assert r.usage.cost_usd is None


@pytest.mark.asyncio
async def test_openai_provider_end_to_end_with_stub_client():
    sent: dict = {}

    class _Completions:
        async def create(self, **kwargs):
            sent.update(kwargs)
            return ChatCompletion.model_validate(OPENAI_TOOL_TURN)

    class _Client:
        class chat:  # noqa: N801 — mirrors the SDK attribute path
            completions = _Completions()

    provider = OpenAIProvider()
    provider._clients["k"] = _Client()  # the provider's own per-key client pool
    r = await provider.chat_with_tools(HISTORY, [LOOKUP], model="gpt-4o-mini", api_key="k")
    assert sent["tools"][0]["function"]["name"] == "lookup_property"
    assert r.tool_calls[0].name == "lookup_property"
    with pytest.raises(LLMNotConfigured):
        await provider.chat_with_tools(HISTORY, [LOOKUP], model="m", api_key="")


# ── Anthropic ───────────────────────────────────────────────────────────────


def test_anthropic_request_mapping():
    req = build_anthropic_request(HISTORY, [LOOKUP], model="claude-sonnet-4-5", max_tokens=300)
    assert req == {
        "model": "claude-sonnet-4-5",
        "max_tokens": 300,
        "system": [{"type": "text", "text": "You are Julia.", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {"role": "user", "content": "find ONE0007"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Looking."},
                    {"type": "tool_use", "id": "call_1", "name": "lookup_property", "input": {"code": "ONE0007"}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": '{"ok": true}'}],
            },
        ],
        "tools": [
            {"name": "lookup_property", "description": "Find a property by code", "input_schema": LOOKUP.parameters}
        ],
    }


def test_anthropic_merges_parallel_tool_results_and_flags_errors():
    msgs = [
        ChatMessage.user("go"),
        ChatMessage.assistant(None, [ToolCall("a", "t1", {}), ToolCall("b", "t2", {})]),
        ChatMessage.tool(ToolResult("a", "ok")),
        ChatMessage.tool(ToolResult("b", "boom", is_error=True)),
    ]
    req = build_anthropic_request(msgs, [], model="m")
    assert req["system"] == "" and "tools" not in req
    last = req["messages"][-1]
    assert [b["tool_use_id"] for b in last["content"]] == ["a", "b"]
    assert last["content"][1]["is_error"] is True
    assert build_anthropic_request(msgs, [LOOKUP], model="m", tool_choice="required")["tool_choice"] == {"type": "any"}


def test_anthropic_response_parsing_tool_turn():
    r = parse_anthropic_response(AnthropicMessage.model_validate(ANTHROPIC_TOOL_TURN), model="claude-sonnet-4-5")
    assert r.finish_reason == "tool_calls"
    assert r.text == "Looking."
    assert r.tool_calls == (ToolCall("toolu_1", "lookup_property", {"code": "ONE0007"}),)
    u = r.usage
    assert (u.prompt_tokens, u.completion_tokens, u.cache_read_tokens, u.cache_creation_tokens) == (100, 30, 400, 0)


def test_anthropic_response_parsing_text_turn_and_length():
    r = parse_anthropic_response(AnthropicMessage.model_validate(ANTHROPIC_TEXT_TURN), model="x")
    assert (r.text, r.finish_reason, r.tool_calls) == ("Found it!", "stop", ())
    cut = dict(ANTHROPIC_TEXT_TURN, stop_reason="max_tokens")
    assert parse_anthropic_response(AnthropicMessage.model_validate(cut), model="x").finish_reason == "length"


@pytest.mark.asyncio
async def test_anthropic_provider_end_to_end_records_usage():
    sent: dict = {}

    class _Messages:
        async def create(self, **kwargs):
            sent.update(kwargs)
            return AnthropicMessage.model_validate(ANTHROPIC_TOOL_TURN)

    class _Client:
        messages = _Messages()

    sink = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=sink))
    try:
        provider = AnthropicProvider()
        provider._clients["k"] = _Client()
        r = await provider.chat_with_tools(HISTORY, [LOOKUP], model="claude-sonnet-4-5", api_key="k", org_id="org-1")
    finally:
        _llm_client._active_config = None
    assert "temperature" not in sent and sent["tools"][0]["name"] == "lookup_property"
    assert r.tool_calls[0].call_id == "toolu_1"
    assert len(sink.events) == 1 and sink.events[0].org_id == "org-1"
    assert sink.events[0].cache_read_input_tokens == 400


# ── Gemini ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gemini_raises_typed_not_implemented():
    with pytest.raises(ToolCallingNotImplemented):
        await GeminiProvider().chat_with_tools([], [])


# ── Fake provider ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_provider_is_scriptable_and_deterministic():
    def script():
        return FakeProvider(tool_responses=[[ToolCall("c1", "lookup_property", {"code": "X"})], "done"])

    outs = []
    for _ in range(2):
        fake = script()
        a = await fake.chat_with_tools(HISTORY, [LOOKUP], model="m", api_key="k")
        b = await fake.chat_with_tools(HISTORY, [LOOKUP], model="m", api_key="k")
        c = await fake.chat_with_tools(HISTORY, [LOOKUP], model="m", api_key="k")  # exhausted
        outs.append((a, b, c))
        assert [call["method"] for call in fake.calls] == ["chat_with_tools"] * 3
    assert outs[0] == outs[1]
    a, b, c = outs[0]
    assert a.finish_reason == "tool_calls" and a.tool_calls[0].arguments == {"code": "X"}
    assert (b.text, b.finish_reason) == ("done", "stop")
    assert c.text.startswith("[FAKE]")


# ── entry point: credentials + dispatch ─────────────────────────────────────


@pytest.fixture
def fake_registered():
    fake = FakeProvider(tool_responses=["hi"])
    register("fake", lambda: fake)  # the registry maps name → factory
    keys: list = []

    def key_provider(provider, org_id=None):
        keys.append((provider, org_id))
        return "platform-key"

    configure_llm(LLMConfig(key_provider=key_provider, default_provider="fake", default_chat_model="m"))
    yield fake, keys
    _llm_client._active_config = None
    _llm_client._provider_cache.clear()
    _registry._PROVIDERS.pop("fake", None)


@pytest.mark.asyncio
async def test_default_path_resolves_key_via_key_provider(fake_registered):
    fake, keys = fake_registered
    await chat_with_tools([ChatMessage.user("x")], org_id="o1")
    assert keys == [("fake", "o1")]
    assert fake.calls[0]["api_key"] == "platform-key"


@pytest.mark.asyncio
async def test_explicit_key_wins_and_skips_resolution(fake_registered):
    fake, keys = fake_registered
    await chat_with_tools([ChatMessage.user("x")], api_key="org-key")
    assert keys == [] and fake.calls[0]["api_key"] == "org-key"


@pytest.mark.asyncio
async def test_org_only_mode_fails_closed_without_explicit_key(fake_registered):
    fake, keys = fake_registered
    with pytest.raises(LLMNotConfigured):
        await chat_with_tools([ChatMessage.user("x")], org_id="o1", require_explicit_key=True)
    assert keys == [] and fake.calls == []  # never fell back to the platform key
    await chat_with_tools([ChatMessage.user("x")], api_key="org-key", require_explicit_key=True)
    assert fake.calls[0]["api_key"] == "org-key"


@pytest.mark.asyncio
async def test_provider_without_tool_calling_is_typed_error(fake_registered):
    class _NoTools:
        name = "plain"

    register("plain", _NoTools)
    try:
        with pytest.raises(ToolCallingNotImplemented):
            await chat_with_tools([ChatMessage.user("x")], provider="plain", api_key="k")
    finally:
        _registry._PROVIDERS.pop("plain", None)


@pytest.mark.asyncio
async def test_run_tool_loop_over_fake(fake_registered):
    fake, _ = fake_registered
    fake._tool_turns.clear()
    fake._tool_turns.extend([[ToolCall("c1", "lookup_property", {"code": "X"})], "all done"])

    async def chat(msgs, specs):
        return await chat_with_tools(msgs, specs, api_key="k")

    async def handler(call):
        return ToolResult(call.call_id, '{"found": true}')

    out = await run_tool_loop([ChatMessage.user("go")], [LOOKUP], handler, chat=chat)
    assert out.text == "all done" and out.iterations == 2 and not out.exhausted
    assert [m.role for m in out.messages] == ["user", "assistant", "tool"]
