"""
Provider-neutral tool calling — `chat_with_tools` (slice S0 of the Lais contract).

SYNC vs ASYNC (decision): **async**. Every seed provider is async and the
agents runtime is async, so `chat_with_tools` is a coroutine. There is no
sync twin of the entry point; the one sync caller (`LLMDispatcher.reply`,
which owns an injected sync OpenAI client) bridges with
`tool_loop.run_tool_loop_sync`.

`chat_with_tools` performs ONE model turn: messages + tool specs in, text +
tool calls + usage + finish reason out. The iteration (call tools, feed the
results back) is `tool_loop.run_tool_loop` — the single tool loop of the
platform; `LLMDispatcher`, `OpenAIToolOrchestrator` and social-wiring's
`ChatbotService` all run on it.

Normalized types live here (no provider imports, so providers can import
them): `ChatMessage`, `ToolSpec`, `ToolCall`, `ToolResult`, `LLMUsage`,
`ChatToolsResponse`. Each provider maps them to/from its wire shape in pure,
network-free functions (`openai_provider.build_openai_request` /
`parse_openai_response`, the anthropic twins) so the mapping is testable
against recorded fixtures.

Credentials (B1, per-org keys): pass `api_key=` explicitly. With
`require_explicit_key=True` the seed resolves NOTHING itself — no
`LLMConfig.key_provider`, no platform setting, no env — and raises
`LLMNotConfigured` when `api_key` is empty (fail closed). Without it the
legacy behaviour holds: explicit `api_key` wins, else `key_provider`.
Budget enforcement and `llm_usage` recording apply on both paths.

Gemini: tool calling is not implemented (see
`gemini_provider.GeminiProvider.chat_with_tools`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Sequence, Union

from .exceptions import LLMNotConfigured

Role = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "tool_calls", "length", "other"]
#: "auto" | "none" | "required" | a specific tool name.
ToolChoice = str


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call. `parameters` is a JSON-schema object."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    #: The caller's original OpenAI-shaped dict, when the spec was built from
    #: one (`from_openai`). The OpenAI mapping sends it verbatim so a caller
    #: that already speaks OpenAI sees no wire change.
    openai_raw: Optional[dict[str, Any]] = field(default=None, compare=False, repr=False)

    @classmethod
    def from_openai(cls, tool: dict[str, Any]) -> "ToolSpec":
        fn = tool.get("function") or {}
        return cls(
            name=fn.get("name", ""),
            description=fn.get("description", "") or "",
            parameters=fn.get("parameters") or {"type": "object", "properties": {}},
            openai_raw=tool,
        )


@dataclass(frozen=True)
class ToolCall:
    """A tool call requested by the model."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    #: Raw argument string as the vendor sent it (OpenAI), echoed back
    #: verbatim in history. `None` ⇒ serialized from `arguments`.
    raw_arguments: Optional[str] = field(default=None, compare=False, repr=False)

    @property
    def id(self) -> str:
        return self.call_id


@dataclass(frozen=True)
class ToolResult:
    """A tool handler's return value, fed back as a `tool` message."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ChatMessage:
    """One normalized conversation message.

    `tool_calls` is only meaningful on `assistant`; `tool_call_id` only on
    `tool`. `cache=True` on a system message asks Anthropic for an
    ephemeral prompt-cache breakpoint (ignored by OpenAI, which caches
    automatically).
    """

    role: Role
    content: Optional[str] = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: Optional[str] = None
    is_error: bool = False
    cache: bool = False

    @classmethod
    def system(cls, content: str, *, cache: bool = False) -> "ChatMessage":
        return cls("system", content, cache=cache)

    @classmethod
    def user(cls, content: str) -> "ChatMessage":
        return cls("user", content)

    @classmethod
    def assistant(cls, content: Optional[str] = None, tool_calls: Sequence[ToolCall] = ()) -> "ChatMessage":
        return cls("assistant", content, tuple(tool_calls))

    @classmethod
    def tool(cls, result: ToolResult) -> "ChatMessage":
        return cls("tool", result.content, tool_call_id=result.call_id, is_error=result.is_error)


@dataclass(frozen=True)
class LLMUsage:
    """Token accounting for one turn. `cost_usd` is None when the seed's
    catalog has no price for the model (never a fabricated 0)."""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_creation_tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    def __add__(self, other: "LLMUsage") -> "LLMUsage":
        def _s(a: Optional[int], b: Optional[int]) -> Optional[int]:
            return None if a is None and b is None else (a or 0) + (b or 0)

        costs = [c for c in (self.cost_usd, other.cost_usd) if c is not None]
        return LLMUsage(
            _s(self.prompt_tokens, other.prompt_tokens),
            _s(self.completion_tokens, other.completion_tokens),
            _s(self.cache_read_tokens, other.cache_read_tokens),
            _s(self.cache_creation_tokens, other.cache_creation_tokens),
            sum(costs) if costs else None,
        )


@dataclass(frozen=True)
class ChatToolsResponse:
    """Result of one `chat_with_tools` turn."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: LLMUsage = field(default_factory=LLMUsage)
    finish_reason: FinishReason = "stop"
    model_version: Optional[str] = None
    #: Unstripped assistant content, for faithful history echo.
    content_raw: Optional[str] = field(default=None, compare=False, repr=False)

    @property
    def message(self) -> ChatMessage:
        """The assistant turn, ready to append to the history."""
        content = self.content_raw if self.content_raw is not None else (self.text or None)
        return ChatMessage.assistant(content, self.tool_calls)


class ToolCallingNotImplemented(Exception):
    """The provider has no tool-calling implementation (typed, never silent)."""

    def __init__(self, provider: str):
        super().__init__(f"Provider {provider!r} does not implement tool calling (chat_with_tools).")
        self.provider = provider


# ── coercion: dict-shaped (OpenAI-style) callers → normalized types ──────────


def coerce_message(msg: Union[ChatMessage, dict[str, Any]]) -> ChatMessage:
    if isinstance(msg, ChatMessage):
        return msg
    role = msg.get("role")
    if role not in ("system", "user", "assistant", "tool"):
        raise ValueError(f"unsupported message role: {role!r}")
    calls: list[ToolCall] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw = fn.get("arguments")
        calls.append(ToolCall(tc.get("id", ""), fn.get("name", ""), parse_arguments(raw), raw if isinstance(raw, str) else None))
    content = msg.get("content")
    if content is not None and not isinstance(content, str):
        # Block-shaped content: keep the text blocks only (tool calling is text-in/text-out).
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ChatMessage(
        role,
        content,
        tuple(calls),
        msg.get("tool_call_id"),
        cache=bool(msg.get("cache_control")),
    )


def coerce_messages(messages: Sequence[Union[ChatMessage, dict[str, Any]]]) -> list[ChatMessage]:
    return [coerce_message(m) for m in messages]


def coerce_tools(tools: Optional[Sequence[Union[ToolSpec, dict[str, Any]]]]) -> list[ToolSpec]:
    return [t if isinstance(t, ToolSpec) else ToolSpec.from_openai(t) for t in (tools or [])]


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Tool-call arguments → dict. Invalid / non-object JSON ⇒ `{}` (the
    dispatcher's historical, tested behaviour)."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


# ── entry point ──────────────────────────────────────────────────────────────


async def chat_with_tools(
    messages: Sequence[Union[ChatMessage, dict[str, Any]]],
    tools: Optional[Sequence[Union[ToolSpec, dict[str, Any]]]] = None,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    api_key: Optional[str] = None,
    require_explicit_key: bool = False,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    tool_choice: ToolChoice = "auto",
    provider_impl: Optional[Any] = None,
) -> ChatToolsResponse:
    """One tool-calling model turn through the configured provider.

    Args:
        messages: `ChatMessage`s (OpenAI-shaped dicts are coerced).
        tools: `ToolSpec`s (OpenAI-shaped dicts are coerced).
        provider / model: default to `LLMConfig` defaults.
        api_key: explicit credential from the caller (per-org, B1).
        require_explicit_key: org-only mode — `api_key` MUST be non-empty;
            `LLMConfig.key_provider` / env / platform settings are never
            consulted. Fails closed with `LLMNotConfigured`.
        tool_choice: "auto" | "none" | "required" | a tool name.
        provider_impl: a ready provider-like object exposing
            `chat_with_tools` (used by `OpenAIClientAdapter` for callers that
            own an SDK client). Bypasses config, key resolution and budget —
            those belong to the registry path.

    Raises:
        LLMNotConfigured, LLMAPIError, LLMBudgetExceeded,
        ToolCallingNotImplemented.
    """
    msgs = coerce_messages(messages)
    specs = coerce_tools(tools)

    if provider_impl is not None:
        return await provider_impl.chat_with_tools(
            msgs, specs, model=model or "", api_key=api_key or "", temperature=temperature,
            max_tokens=max_tokens, tool_choice=tool_choice, org_id=org_id,
        )

    from .budget import enforce_budget
    from .client import get_llm_config, get_provider, resolve_api_key

    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_chat_model
    if require_explicit_key:
        if not api_key:
            raise LLMNotConfigured(effective_provider)
        key = api_key
    else:
        key = api_key or resolve_api_key(effective_provider, org_id)

    await enforce_budget(org_id)

    prov = get_provider(effective_provider)
    impl = getattr(prov, "chat_with_tools", None)
    if impl is None:
        raise ToolCallingNotImplemented(effective_provider)
    from .usage import metered_call

    return await metered_call(
        lambda: impl(
            msgs, specs, model=effective_model, api_key=key, temperature=temperature,
            max_tokens=max_tokens, tool_choice=tool_choice, org_id=org_id,
        ),
        provider=effective_provider, model=effective_model, operation="chat", org_id=org_id,
    )


def build_usage(
    provider: str,
    model: str,
    *,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cache_read_tokens: Optional[int] = None,
    cache_creation_tokens: Optional[int] = None,
) -> LLMUsage:
    """`LLMUsage` with `cost_usd` from the seed catalog — None when the model
    has no complete price (never a made-up number)."""
    from .models import is_priced, models_for
    from .usage import estimate_cost_usd

    entry = next((m for m in models_for(provider) if m.id == model), None)
    cost: Optional[float] = None
    if entry is not None and is_priced(entry):
        cost = estimate_cost_usd(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_creation_input_tokens=cache_creation_tokens,
            cache_read_input_tokens=cache_read_tokens,
        )
    return LLMUsage(prompt_tokens, completion_tokens, cache_read_tokens, cache_creation_tokens, cost)
