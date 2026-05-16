"""openai_orchestrator — surface-agnostic orchestrator composing
LLMDispatcher.

Covers:
- memory_key_for / append_memory shape (validated source parity)
- FakeToolOrchestrator scripted-reply + history round-trip
- OpenAIToolOrchestrator delegating the loop to LLMDispatcher, with an
  async tool handler bridged into the sync dispatcher (no rewrite)
- factory Fake-by-default / Real-when-wired
"""

from dataclasses import dataclass
from typing import Any

import pytest

from noctusai_lib.domain.chatbot.openai_orchestrator import (
    MEMORY_PREFIX,
    FakeToolOrchestrator,
    OpenAIToolOrchestrator,
    OrchestratorTool,
    ToolOrchestrator,
    append_memory,
    make_tool_orchestrator,
    memory_key_for,
)


# ── FakeRedis ───────────────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        return items[start : end + 1 if end != -1 else None]

    def ltrim(self, key, start, end):
        items = self.lists.get(key, [])
        self.lists[key] = items[start:] if end == -1 else items[start : end + 1]

    def expire(self, key, seconds):  # noqa: ARG002
        return True

    def delete(self, key):
        self.lists.pop(key, None)


# ── memory key parity with the validated source ─────────────────────────


def test_memory_key_strips_jid_suffixes() -> None:
    assert memory_key_for("5511974693365@c.us") == f"{MEMORY_PREFIX}5511974693365"
    assert memory_key_for("33613018058989@lid") == f"{MEMORY_PREFIX}33613018058989"
    assert memory_key_for("web:abc123") == f"{MEMORY_PREFIX}web:abc123"


def test_append_memory_round_trip() -> None:
    redis = _FakeRedis()
    append_memory(redis, session_id="web:x", direction="inbound", text="ola")
    append_memory(redis, session_id="web:x", direction="outbound", text="oi")
    assert len(redis.lists[f"{MEMORY_PREFIX}web:x"]) == 2


def test_append_memory_skips_empty_text() -> None:
    redis = _FakeRedis()
    append_memory(redis, session_id="web:x", direction="inbound", text="")
    assert redis.lists == {}


# ── Fake orchestrator ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_scripted_reply_and_history() -> None:
    bot = FakeToolOrchestrator(
        session_id="web:abc", scripted_replies=["first", "second"]
    )
    assert await bot.reply("hi") == "first"
    assert await bot.reply("again") == "second"
    assert bot.load_history() == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "first"},
        {"role": "user", "content": "again"},
        {"role": "assistant", "content": "second"},
    ]
    bot.reset_history()
    assert bot.load_history() == []


def test_fake_requires_session_or_phone() -> None:
    with pytest.raises(ValueError):
        FakeToolOrchestrator()


def test_fake_legacy_phone_kwarg() -> None:
    bot = FakeToolOrchestrator(phone="5511974693365@c.us")
    assert bot.load_history() == []


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeToolOrchestrator(session_id="web:x"), ToolOrchestrator)


# ── Real orchestrator composing LLMDispatcher ───────────────────────────


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
        return _FakeResponse(choices=[_FakeChoice(message=self._scripted.pop(0))])


class _FakeChat:
    def __init__(self, scripted):
        self.completions = _FakeCompletions(scripted)


class _FakeOpenAI:
    def __init__(self, scripted):
        self.chat = _FakeChat(scripted)


@pytest.mark.asyncio
async def test_real_orchestrator_no_tool_reply_writes_memory() -> None:
    redis = _FakeRedis()
    client = _FakeOpenAI([_FakeMessage(content="  hello  ")])
    bot = OpenAIToolOrchestrator(
        redis_client=redis,
        client=client,
        model="gpt-test",
        system_prompt="sys",
        session_id="web:abc",
    )
    reply = await bot.reply("hi")
    assert reply == "hello"
    hist = bot.load_history()
    assert hist == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


@pytest.mark.asyncio
async def test_real_orchestrator_async_tool_bridged_into_dispatcher() -> None:
    redis = _FakeRedis()
    tool_call_msg = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall(
                id="c1",
                function=_FakeFunc(
                    name="lookup", arguments='{"code": "ONE0007"}'
                ),
            )
        ],
    )
    final_msg = _FakeMessage(content="done")
    client = _FakeOpenAI([tool_call_msg, final_msg])

    seen: list[dict] = []

    async def _lookup(args: dict) -> dict:
        seen.append(args)
        return {"ok": True, "code": args["code"]}

    bot = OpenAIToolOrchestrator(
        redis_client=redis,
        client=client,
        model="gpt-test",
        system_prompt="sys",
        session_id="web:abc",
        tools=[
            OrchestratorTool(
                name="lookup",
                description="look up a property",
                parameters={"type": "object", "properties": {}},
                handler=_lookup,
            )
        ],
    )
    reply = await bot.reply("find ONE0007")
    assert reply == "done"
    assert seen == [{"code": "ONE0007"}]
    assert len(client.chat.completions.calls) == 2


def test_real_requires_session_or_phone() -> None:
    with pytest.raises(ValueError):
        OpenAIToolOrchestrator(
            redis_client=_FakeRedis(),
            client=_FakeOpenAI([]),
            model="m",
            system_prompt="s",
        )


# ── Factory ─────────────────────────────────────────────────────────────


def test_factory_fake_by_default() -> None:
    bot = make_tool_orchestrator(session_id="web:x", use_fake=True)
    assert isinstance(bot, FakeToolOrchestrator)
    # No client/model/prompt → Fake.
    assert isinstance(
        make_tool_orchestrator(session_id="web:x"), FakeToolOrchestrator
    )


def test_factory_real_when_wired() -> None:
    bot = make_tool_orchestrator(
        redis_client=_FakeRedis(),
        client=_FakeOpenAI([]),
        model="gpt-test",
        system_prompt="sys",
        session_id="web:x",
    )
    assert isinstance(bot, OpenAIToolOrchestrator)
