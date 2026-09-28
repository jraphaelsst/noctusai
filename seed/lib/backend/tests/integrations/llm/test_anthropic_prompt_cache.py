"""Anthropic prompt-cache wiring — the bug this file guards against.

`chat.build_cached_messages(..., provider="anthropic")` marks its system
message with a top-level `{"cache_control": {"type": "ephemeral"}}` key. That
marker is a seed-internal convention, not itself valid Anthropic wire shape —
Anthropic only recognizes `cache_control` INSIDE a system content block.
`AnthropicProvider._split_system_and_messages` is the translation seam, and
before this fix it read only `content` (str or list-of-blocks text) and threw
the `cache_control` key away — so a cached call and an uncached call produced
the byte-identical `system=` string, and no Anthropic consumer ever got a
cache write or a cache hit.

Also covers: usage accounting reads `cache_creation_input_tokens` /
`cache_read_input_tokens` off the SDK response (sync + stream) and prices
them into `cost_estimate_usd` at Anthropic's published multipliers.

Pure DI stubs — no monkeypatching of our own code (CLAUDE.md §1 / `KB §
PATTERNS/compliance/testing.md`); mirrors `test_anthropic_no_temperature.py`.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm import (
    InMemoryUsageSink,
    LLMConfig,
    build_cached_messages,
    configure_llm,
)
from noctusai_lib.integrations.llm import client as _llm_client
from noctusai_lib.integrations.llm.providers.anthropic_provider import (
    AnthropicProvider,
    _split_system_and_messages,
)
from noctusai_lib.integrations.llm.usage import estimate_cost_usd


def _reset_llm_config() -> None:
    """Uninstall the config this file installed so it never leaks into a
    sibling test file that expects none — same discipline as
    `test_gemini_embeddings.py`'s `_reset_llm_config`."""
    _llm_client._active_config = None


# ---------------------------------------------------------------------------
# `_split_system_and_messages` — the translation seam, in isolation
# ---------------------------------------------------------------------------


class TestSplitSystemAndMessages:
    def test_plain_string_system_stays_a_string(self):
        """No `cache_control` anywhere → byte-identical to the pre-fix shape.
        Non-cached callers must see zero behaviour change."""
        system, rest = _split_system_and_messages(
            [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]
        )
        assert system == "be terse"
        assert rest == [{"role": "user", "content": "hi"}]

    def test_no_system_message_returns_empty_string(self):
        system, rest = _split_system_and_messages([{"role": "user", "content": "hi"}])
        assert system == ""
        assert rest == [{"role": "user", "content": "hi"}]

    def test_multiple_plain_system_messages_still_concatenate(self):
        """Pre-existing multi-system-message join behaviour is preserved
        when none of them carry cache_control."""
        system, _ = _split_system_and_messages(
            [
                {"role": "system", "content": "part one"},
                {"role": "system", "content": "part two"},
                {"role": "user", "content": "hi"},
            ]
        )
        assert system == "part one\n\npart two"

    def test_cache_control_on_string_system_becomes_a_content_block_list(self):
        """THE BUG: a `cache_control`-marked system message must reach the
        SDK as `[{"type": "text", "text": ..., "cache_control": {...}}]`,
        never silently collapsed back to a plain string."""
        system, rest = _split_system_and_messages(
            [
                {
                    "role": "system",
                    "content": "stable instructions",
                    "cache_control": {"type": "ephemeral"},
                },
                {"role": "user", "content": "hi"},
            ]
        )
        assert system == [
            {
                "type": "text",
                "text": "stable instructions",
                "cache_control": {"type": "ephemeral"},
            }
        ]
        assert rest == [{"role": "user", "content": "hi"}]

    def test_cache_control_preserved_on_already_block_shaped_system_content(self):
        """A caller that already hands block-shaped system content with its
        own per-block cache_control keeps it — including blocks that have
        none, which come back bare (no key injected)."""
        system, _ = _split_system_and_messages(
            [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": "cached part",
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": "uncached part"},
                    ],
                }
            ]
        )
        assert system == [
            {"type": "text", "text": "cached part", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "uncached part"},
        ]

    def test_non_system_messages_pass_through_unchanged_including_cache_control(self):
        """User/assistant messages were never the bug — content-block
        cache_control on them already survived via plain passthrough. This
        pins that it still does after the rewrite."""
        user_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "big doc", "cache_control": {"type": "ephemeral"}}
            ],
        }
        _, rest = _split_system_and_messages([user_msg])
        assert rest == [user_msg]

    def test_empty_text_blocks_are_dropped_from_the_block_form(self):
        system, _ = _split_system_and_messages(
            [
                {
                    "role": "system",
                    "content": "",
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "role": "system",
                    "content": "real content",
                    "cache_control": {"type": "ephemeral"},
                },
            ]
        )
        assert system == [
            {"type": "text", "text": "real content", "cache_control": {"type": "ephemeral"}}
        ]


# ---------------------------------------------------------------------------
# Provider-level fakes — mirrors `test_anthropic_no_temperature.py`
# ---------------------------------------------------------------------------


class _Usage:
    def __init__(
        self,
        input_tokens=10,
        output_tokens=5,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _Block:
    def __init__(self, text="ok"):
        self.text = text


class _Message:
    def __init__(self, usage=None, content=None):
        self.content = content or [_Block()]
        self.usage = usage if usage is not None else _Usage()


class _Stream:
    def __init__(self, final_message=None):
        self._final_message = final_message or _Message()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            yield "ok"

        return gen()

    async def get_final_message(self):
        return self._final_message


class _Messages:
    def __init__(self, final_message=None):
        self.sent: dict = {}
        self._final_message = final_message

    async def create(self, **kwargs):
        self.sent = kwargs
        return self._final_message or _Message()

    def stream(self, **kwargs):
        self.sent = kwargs
        return _Stream(self._final_message)


class _Client:
    def __init__(self, final_message=None):
        self.messages = _Messages(final_message)


def _provider(final_message=None) -> tuple[AnthropicProvider, _Client]:
    client = _Client(final_message)
    provider = AnthropicProvider()
    provider._clients["k"] = client
    return provider, client


# ---------------------------------------------------------------------------
# chat_completion / chat_completion_stream — the SDK actually receives the
# cache blocks (and non-cached calls are unchanged)
# ---------------------------------------------------------------------------


class TestChatCompletionSendsCacheBlocks:
    @pytest.mark.asyncio
    async def test_uncached_system_message_sent_as_plain_string(self):
        """Regression guard: a caller not opting into caching must see the
        exact pre-fix `system=` shape."""
        provider, client = _provider()
        await provider.chat_completion(
            [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}],
            model="m",
            api_key="k",
        )
        assert client.messages.sent["system"] == "be terse"

    @pytest.mark.asyncio
    async def test_cached_system_message_sent_as_content_block_list(self):
        """`build_cached_messages(..., provider="anthropic")` output must
        reach the SDK with the cache_control breakpoint intact."""
        provider, client = _provider()
        messages = build_cached_messages(
            "A" * 5000, "what is x?", provider="anthropic"
        )
        await provider.chat_completion(messages, model="m", api_key="k")

        sent_system = client.messages.sent["system"]
        assert isinstance(sent_system, list)
        assert sent_system == [
            {
                "type": "text",
                "text": "A" * 5000,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        # The dynamic user turn must still be the only non-system message.
        assert client.messages.sent["messages"] == [
            {"role": "user", "content": "what is x?"}
        ]

    @pytest.mark.asyncio
    async def test_json_response_format_appends_uncached_block_to_cached_system(self):
        """The JSON-mode instruction must not crash on a list-shaped system
        (str + list would TypeError) and must not disturb the cached block."""
        provider, client = _provider()
        messages = build_cached_messages("A" * 5000, "q", provider="anthropic")
        await provider.chat_completion(
            messages, model="m", api_key="k", response_format={"type": "json_object"}
        )

        sent_system = client.messages.sent["system"]
        assert sent_system[0] == {
            "type": "text",
            "text": "A" * 5000,
            "cache_control": {"type": "ephemeral"},
        }
        assert sent_system[1]["type"] == "text"
        assert "JSON" in sent_system[1]["text"]
        assert "cache_control" not in sent_system[1]

    @pytest.mark.asyncio
    async def test_json_response_format_on_plain_string_system_unchanged(self):
        """Non-cached path keeps the pre-fix string-concatenation shape."""
        provider, client = _provider()
        await provider.chat_completion(
            [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}],
            model="m",
            api_key="k",
            response_format={"type": "json_object"},
        )
        sent_system = client.messages.sent["system"]
        assert isinstance(sent_system, str)
        assert sent_system.startswith("be terse\n\n")
        assert "JSON" in sent_system

    @pytest.mark.asyncio
    async def test_stream_uncached_system_message_sent_as_plain_string(self):
        provider, client = _provider()
        chunks = [
            c
            async for c in provider.chat_completion_stream(
                [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}],
                model="m",
                api_key="k",
            )
        ]
        assert chunks == ["ok"]
        assert client.messages.sent["system"] == "be terse"

    @pytest.mark.asyncio
    async def test_stream_cached_system_message_sent_as_content_block_list(self):
        provider, client = _provider()
        messages = build_cached_messages("B" * 5000, "what is x?", provider="anthropic")
        chunks = [
            c
            async for c in provider.chat_completion_stream(messages, model="m", api_key="k")
        ]
        assert chunks == ["ok"]
        sent_system = client.messages.sent["system"]
        assert sent_system == [
            {
                "type": "text",
                "text": "B" * 5000,
                "cache_control": {"type": "ephemeral"},
            }
        ]


# ---------------------------------------------------------------------------
# Usage accounting: cache_creation_input_tokens / cache_read_input_tokens
# ---------------------------------------------------------------------------


@pytest.fixture
def sink():
    s = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda _p, _o=None: None, usage_sink=s))
    yield s
    _reset_llm_config()


class TestUsageAccountingReadsCacheTokens:
    @pytest.mark.asyncio
    async def test_chat_completion_records_cache_tokens_from_response_usage(self, sink):
        final = _Message(
            usage=_Usage(
                input_tokens=100,
                output_tokens=20,
                cache_creation_input_tokens=500,
                cache_read_input_tokens=1000,
            )
        )
        provider, _client = _provider(final_message=final)
        await provider.chat_completion(
            [{"role": "user", "content": "hi"}], model="claude-haiku-4-5", api_key="k"
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.cache_creation_input_tokens == 500
        assert event.cache_read_input_tokens == 1000
        # claude-haiku-4-5: $1/$5 per 1M (see models.py). Cache write @1.25x,
        # cache read @0.1x the $1 input rate, additive to the normal
        # prompt/completion cost.
        expected = (
            100 * 1.00 + 20 * 5.00 + 500 * 1.00 * 1.25 + 1000 * 1.00 * 0.1
        ) / 1_000_000.0
        assert event.cost_estimate_usd == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_chat_completion_stream_records_cache_tokens_from_final_message(self, sink):
        final = _Message(
            usage=_Usage(
                input_tokens=50,
                output_tokens=10,
                cache_creation_input_tokens=200,
                cache_read_input_tokens=0,
            )
        )
        provider, _client = _provider(final_message=final)
        chunks = [
            c
            async for c in provider.chat_completion_stream(
                [{"role": "user", "content": "hi"}], model="claude-haiku-4-5", api_key="k"
            )
        ]
        assert chunks == ["ok"]

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.cache_creation_input_tokens == 200
        assert event.cache_read_input_tokens == 0

    @pytest.mark.asyncio
    async def test_no_cache_usage_leaves_fields_none_and_cost_unaffected(self, sink):
        """A response with no cache activity (`None` on both fields, the
        shape every non-caching call gets) must reproduce the exact
        pre-cache-accounting cost — zero regression for the common case."""
        final = _Message(usage=_Usage(input_tokens=100, output_tokens=20))
        provider, _client = _provider(final_message=final)
        await provider.chat_completion(
            [{"role": "user", "content": "hi"}], model="claude-haiku-4-5", api_key="k"
        )

        event = sink.events[0]
        assert event.cache_creation_input_tokens is None
        assert event.cache_read_input_tokens is None
        assert event.cost_estimate_usd == pytest.approx((100 * 1.00 + 20 * 5.00) / 1_000_000.0)


class TestEstimateCostUsdCacheMultipliers:
    def test_anthropic_cache_write_and_read_priced_off_input_rate(self):
        cost = estimate_cost_usd(
            provider="anthropic",
            model="claude-haiku-4-5",
            prompt_tokens=0,
            completion_tokens=0,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
        )
        # $1/1M input rate: write @1.25x = $1.25, read @0.1x = $0.10.
        assert cost == pytest.approx(1.25 + 0.10)

    def test_cache_tokens_ignored_for_non_anthropic_providers(self):
        """The multiplier is Anthropic's own pricing rule — it must not
        silently apply to a different vendor's rate card."""
        cost = estimate_cost_usd(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=0,
            completion_tokens=0,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
        )
        assert cost == 0.0

    def test_omitting_cache_tokens_reproduces_prior_text_only_cost(self):
        """Every pre-existing call site (which passes neither kwarg)
        continues to see the identical result."""
        cost = estimate_cost_usd(
            provider="anthropic",
            model="claude-haiku-4-5",
            prompt_tokens=1000,
            completion_tokens=200,
        )
        assert cost == pytest.approx((1000 * 1.00 + 200 * 5.00) / 1_000_000.0)
