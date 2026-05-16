"""Surface-agnostic OpenAI tool-orchestration chatbot.

Reconciled 2026-05-16 from the live-validated
`youtube-crawler/app/services/chatbot_service.py:ChatbotService`
(`projects/social-wiring-absorption/` W1.E1, manifests
`whatsapp-chatbot-service` + `platform-chat-agent`). That service ran
live end-to-end against real OpenAI/Vista/WAHA + the platform `/chat`
page across 13 commits.

Key reconcile decisions (sibling-validated wins per project §3.2,
seed-shape generalizations applied per §3.3):

  - **Compose, don't rewrite, the loop.** The validated `ChatbotService`
    inlined its own OpenAI completion + tool-call loop. The seed
    already ships a clean, tested
    :class:`~noctusai_lib.domain.chatbot.llm_dispatcher.LLMDispatcher`
    that IS exactly that loop (single-call path, tool-loop path,
    audit_writer seam, max-iteration fallback, invalid-JSON handling).
    Per the W1.E1 brief this orchestrator **composes** `LLMDispatcher`
    rather than duplicating the loop — the orchestrator owns
    session/memory/intake/tool-registry; the dispatcher owns the
    completion+tool iteration. Behaviour preserved; loop de-duplicated
    (the seed had two copies of the same loop — this closes it).
  - **session_id, not phone.** The opaque key the validated code
    already used (WhatsApp passes the phone JID; platform chat passes
    ``web:<uuid>``). Legacy ``phone=`` kwarg retained as the validated
    source kept it (zero-refactor for the WhatsApp router).
  - **System prompt is a constructor arg.** The validated source
    hardcoded a pt-BR real-estate `SYSTEM_PROMPT`. Per the
    `mappers.py` precedent ("system prompts are product-specific") the
    seed takes ``system_prompt`` from the consumer — the real-estate
    prompt stays in the social-wiring product.
  - **Tool surface is a Protocol.** The validated source hardcoded ~20
    real-estate/Vista/Drive/Meta tools delegating to a concrete
    `WhatsAppIntakeService`. The seed extracts a
    :class:`ChatbotIntake`-style seam: the consumer supplies a list of
    :class:`OrchestratorTool` (name + description + JSON-schema params +
    async handler). The product owns its tools; the orchestrator stays
    generic.
  - **Fake+Real+factory.** This is an IO module (OpenAI). Ships
    :class:`OpenAIToolOrchestrator` (Real, composes `LLMDispatcher`
    over `AsyncOpenAI`-shaped client) + :class:`FakeToolOrchestrator`
    (scripted replies / scripted tool calls, no network) + a factory —
    per `KB § PATTERNS/seed-fake-real-adapter.md`.

The Redis memory shape (``conversation:memory:{clean_session_id}``,
JID-suffix stripping, RPUSH/LTRIM/EXPIRE) is preserved verbatim from
the validated source so it stays interoperable with the seed
:class:`~noctusai_lib.domain.chatbot.buffer.ConversationBufferService`
(same ``conversation:memory:`` prefix — the validated source itself
unified onto that prefix during the workspace session).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from noctusai_lib.domain.chatbot.llm_dispatcher import (
    DEFAULT_MAX_TOOL_ITERATIONS,
    LLMDispatcher,
    ToolCall,
    ToolResult,
)

logger = logging.getLogger(__name__)

MEMORY_PREFIX = "conversation:memory:"
MEMORY_TTL_SECONDS = 60 * 60
MAX_MEMORY_ITEMS = 40
DEFAULT_FALLBACK_REPLY = (
    "I had trouble completing that request. Could you summarize what "
    "you need again?"
)


def memory_key_for(session_id: str) -> str:
    """Canonical Redis key for a conversation's memory list.

    Strips the WAHA JID suffixes so the same phone always lands on the
    same key regardless of the event shape WAHA emits. Prefix is
    unified with ``ConversationBufferService.memory_prefix`` so the
    buffer worker + the inline orchestrator path share memory state.
    Preserved verbatim from the validated source."""
    clean = (
        session_id.replace("@c.us", "")
        .replace("@s.whatsapp.net", "")
        .replace("@lid", "")
    )
    return f"{MEMORY_PREFIX}{clean}"


def append_memory(
    redis_client: Any, *, session_id: str, direction: str, text: str
) -> None:
    """Append an inbound/outbound text entry to a conversation's memory.

    Called from every outbound boundary so the agent's recall is
    complete — mirrors the validated source's `append_memory` (invoked
    after EVERY successful send, not just orchestrator replies)."""
    if not text:
        return
    key = memory_key_for(session_id)
    payload = json.dumps(
        {"direction": direction, "text": text, "timestamp": time.time()},
        separators=(",", ":"),
    )
    redis_client.rpush(key, payload)
    redis_client.ltrim(key, -MAX_MEMORY_ITEMS, -1)
    redis_client.expire(key, MEMORY_TTL_SECONDS)


@dataclass(frozen=True)
class OrchestratorTool:
    """One tool the consumer exposes to the model. ``handler`` is an
    async callable taking the parsed arguments dict and returning a
    JSON-serializable result dict (the orchestrator serializes it into
    the tool message body)."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@runtime_checkable
class ToolOrchestrator(Protocol):
    """The chatbot-orchestration surface. Real + Fake both satisfy it.
    `@runtime_checkable` per the seed adapter convention."""

    async def reply(
        self,
        inbound_text: str,
        *,
        append_inbound: bool = True,
        append_outbound: bool = True,
    ) -> str:
        """Generate a reply for ``inbound_text``, threading short-term
        Redis memory + the consumer's tool surface."""
        ...

    def load_history(self) -> list[dict[str, str]]:
        """Read-only memory view for a chat UI."""
        ...

    def reset_history(self) -> None:
        """Forget the conversation's memory."""
        ...


def _tools_payload(tools: dict[str, OrchestratorTool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools.values()
    ]


class OpenAIToolOrchestrator:
    """Real orchestrator — composes :class:`LLMDispatcher` over an
    OpenAI-shaped client, threads Redis memory, and dispatches tools
    to the consumer-supplied async handlers.

    ``session_id`` is an opaque conversation key. WhatsApp passes the
    sender phone JID; platform chat passes ``web:<uuid>``.
    """

    def __init__(
        self,
        *,
        redis_client: Any,
        client: Any,
        model: str,
        system_prompt: str,
        tools: list[OrchestratorTool] | None = None,
        session_id: str | None = None,
        phone: str | None = None,
        extra_context: str | None = None,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
        fallback_reply: str = DEFAULT_FALLBACK_REPLY,
    ):
        if session_id is None and phone is None:
            raise ValueError(
                "OpenAIToolOrchestrator requires session_id (or legacy phone)"
            )
        self._redis = redis_client
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._session_id = session_id or phone
        self._extra_context = extra_context
        self._tools: dict[str, OrchestratorTool] = {
            t.name: t for t in (tools or [])
        }
        self._dispatcher = LLMDispatcher(
            client=client,
            model=model,
            max_tool_iterations=max_tool_iterations,
            fallback_reply=fallback_reply,
        )

    # ── memory ─────────────────────────────────────────────────────────
    def _memory_key(self) -> str:
        return memory_key_for(self._session_id)

    def _load_memory(self) -> list[dict[str, Any]]:
        raw = self._redis.lrange(self._memory_key(), -MAX_MEMORY_ITEMS, -1)
        memory: list[dict[str, Any]] = []
        for item in raw or []:
            try:
                memory.append(json.loads(item))
            except Exception:
                continue
        return memory

    def _append_memory(self, direction: str, text: str) -> None:
        append_memory(
            self._redis,
            session_id=self._session_id,
            direction=direction,
            text=text,
        )

    def load_history(self) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for entry in self._load_memory():
            text = entry.get("text")
            if not text:
                continue
            role = (
                "assistant"
                if entry.get("direction") == "outbound"
                else "user"
            )
            items.append({"role": role, "content": text})
        return items

    def reset_history(self) -> None:
        self._redis.delete(self._memory_key())

    @staticmethod
    def _memory_to_messages(
        memory: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in memory:
            text = item.get("text")
            if not text:
                continue
            role = (
                "assistant"
                if item.get("direction") == "outbound"
                else "user"
            )
            messages.append({"role": role, "content": text})
        return messages

    # ── tool dispatch (async intake bridged into the sync dispatcher) ──
    async def _dispatch_tool(
        self, name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": "unknown_tool", "name": name}
        try:
            return await tool.handler(args)
        except Exception as exc:
            logger.exception("Chatbot tool failed: %s", name)
            return {"error": "tool_exception", "message": str(exc)}

    # ── public entry point ─────────────────────────────────────────────
    async def reply(
        self,
        inbound_text: str,
        *,
        append_inbound: bool = True,
        append_outbound: bool = True,
    ) -> str:
        """Run the orchestration loop via the composed
        :class:`LLMDispatcher`.

        The dispatcher is synchronous; the consumer's tool handlers are
        async (validated contract). We run the dispatcher in a worker
        thread and bridge each async tool call back onto the calling
        event loop with ``run_coroutine_threadsafe`` — no rewrite of
        the validated dispatcher loop, async intake preserved.
        """
        memory = self._load_memory()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt}
        ]
        if self._extra_context:
            messages.append(
                {"role": "system", "content": self._extra_context}
            )
        messages.extend(self._memory_to_messages(memory))
        messages.append({"role": "user", "content": inbound_text})

        loop = asyncio.get_running_loop()

        def _sync_tool_handler(call: ToolCall) -> ToolResult:
            future = asyncio.run_coroutine_threadsafe(
                self._dispatch_tool(call.name, call.arguments), loop
            )
            result = future.result()
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(
                    result, ensure_ascii=False, default=str
                ),
            )

        tools_payload = _tools_payload(self._tools) if self._tools else None

        text = await asyncio.to_thread(
            self._dispatcher.reply,
            messages,
            tools_payload,
            _sync_tool_handler if tools_payload else None,
        )
        text = (text or "").strip()

        if append_inbound:
            self._append_memory("inbound", inbound_text)
        if append_outbound:
            self._append_memory("outbound", text)
        return text


class FakeToolOrchestrator:
    """Scripted, network-free :class:`ToolOrchestrator` for tests + dev.

    Pass ``scripted_replies`` (one popped per :meth:`reply` call). Memory
    is an in-memory list so :meth:`load_history` / :meth:`reset_history`
    round-trip exactly like the Real adapter. Tool handlers are NOT
    invoked — the Fake's purpose is to exercise consumers of the
    orchestrator without OpenAI, mirroring the other seed Fakes."""

    def __init__(
        self,
        *,
        session_id: str | None = None,
        phone: str | None = None,
        scripted_replies: list[str] | None = None,
    ):
        if session_id is None and phone is None:
            raise ValueError(
                "FakeToolOrchestrator requires session_id (or legacy phone)"
            )
        self._session_id = session_id or phone
        self._scripted = list(scripted_replies or [])
        self._memory: list[dict[str, Any]] = []

    async def reply(
        self,
        inbound_text: str,
        *,
        append_inbound: bool = True,
        append_outbound: bool = True,
    ) -> str:
        text = (
            self._scripted.pop(0)
            if self._scripted
            else "(fake orchestrator reply)"
        )
        if append_inbound:
            self._memory.append(
                {"direction": "inbound", "text": inbound_text}
            )
        if append_outbound:
            self._memory.append({"direction": "outbound", "text": text})
        return text

    def load_history(self) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for entry in self._memory:
            text = entry.get("text")
            if not text:
                continue
            role = (
                "assistant"
                if entry.get("direction") == "outbound"
                else "user"
            )
            items.append({"role": role, "content": text})
        return items

    def reset_history(self) -> None:
        self._memory.clear()


def make_tool_orchestrator(
    *,
    redis_client: Any | None = None,
    client: Any | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[OrchestratorTool] | None = None,
    session_id: str | None = None,
    phone: str | None = None,
    extra_context: str | None = None,
    scripted_replies: list[str] | None = None,
    use_fake: bool = False,
) -> ToolOrchestrator:
    """Factory — :class:`FakeToolOrchestrator` when ``use_fake`` (or no
    OpenAI client/model/prompt), else :class:`OpenAIToolOrchestrator`.
    Mirrors the `make_<adapter>` convention of the other seed
    integrations."""
    if use_fake or client is None or model is None or system_prompt is None:
        return FakeToolOrchestrator(
            session_id=session_id,
            phone=phone,
            scripted_replies=scripted_replies,
        )
    if redis_client is None:
        raise ValueError("OpenAIToolOrchestrator requires redis_client")
    return OpenAIToolOrchestrator(
        redis_client=redis_client,
        client=client,
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        session_id=session_id,
        phone=phone,
        extra_context=extra_context,
    )


__all__ = [
    "MEMORY_PREFIX",
    "FakeToolOrchestrator",
    "OpenAIToolOrchestrator",
    "OrchestratorTool",
    "ToolOrchestrator",
    "append_memory",
    "make_tool_orchestrator",
    "memory_key_for",
]
