"""``LlmToolRuntime`` — the provider-neutral :class:`~app.runtime.types.AgentRuntime`
(Lais A1, contract ``julia-agent-contract.md`` §2 + §10.2).

Runs an agent whose ``agents.runtime`` is ``'llm'`` on the seed's single tool
loop (``noctusai_lib.integrations.llm.run_tool_loop`` over ``chat_with_tools``):
OpenAI today, Anthropic later, chosen per agent VERSION (``spec.provider``).
``'llm'`` is NOT ``'external'``: ``external`` means another product runs the
agent (One Chat); ``llm`` means agents runs it on this loop.

Event vocabulary == :class:`~app.runtime.claude_runtime.ClaudeAgentSdkRuntime`'s
(the route's turn loop and the eval runner consume both identically):
``message.new`` · ``tool.started`` · ``tool.finished`` · a final
``session.status{status:"ociosa", sdk_session_id:None, custo_usd, tokens_entrada,
tokens_saida, tokens_cache_leitura}``. There is no SDK session, so
``sdk_session_id`` is ``None`` (the route only upserts the conversation when it
is truthy).

Memory (no SDK session): the compiled prompt (``spec.prompt_append``) as the
system message + the last N stored messages of the conversation + the new
prompt. Lead / user text is ALWAYS the ``user`` role (§10.1 M3) — contact names
and the like never enter the system prompt, which is exactly
``spec.prompt_append`` and nothing else.

B1 — org-only keys, fail closed: the provider key is resolved through the
injected ``key_resolver(provider, org_id)`` (production:
``app.credentials.org_keys.make_org_llm_key_resolver`` — this org's rows only)
and handed to the seed with ``require_explicit_key=True``, so the seed resolves
NOTHING itself (no tier-0 override, platform setting or env). No key ⇒
:class:`~app.runtime.errors.LlmNotConfiguredError` (424 ``llm_not_configured``).

Typed failures (``app.runtime.errors``): not configured → 424, budget
exhausted / limiter full → 429 ``capacidade``, provider failure → 502
``llm_upstream``. A channel caller (A2) calls :meth:`preflight` BEFORE it
persists anything (clean refusal, zero trace) and :meth:`try_reserve` for
capacity, then drives :meth:`run_turn` with a service-principal
``TurnContext.requested_by`` (:func:`service_principal_id`).
"""
from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.integrations.llm import (
    ChatMessage,
    LLMAPIError,
    LLMBudgetExceeded,
    LLMNotConfigured,
    ToolCall,
    ToolCallingNotImplemented,
    ToolResult,
    ToolSpec,
    chat_with_tools,
    enforce_budget,
    run_tool_loop,
)

from app.runtime.errors import (
    LlmCapacityError,
    LlmNotConfiguredError,
    LlmRuntimeError,
    LlmUpstreamError,
)
from app.runtime.types import AgentEvent, AgentSpec, ApprovalBroker, TurnContext

logger = logging.getLogger(__name__)

__all__ = [
    "LlmToolset",
    "LlmTurnLimiter",
    "LlmTurnSlot",
    "LlmToolRuntime",
    "make_budget_guard",
    "service_principal_id",
]

#: What the user reads when the loop hit its cap without a final reply.
FALLBACK_REPLY = "Não consegui concluir esse pedido agora. Pode reformular em poucas palavras?"
_TOOL_FAILED = "Falha ao executar a ferramenta."

KeyResolver = Callable[[str, UUID], "str | None"]
BudgetGuard = Callable[[UUID], Awaitable[None]]


def service_principal_id(agent_id: UUID) -> UUID:
    """The actor id for a turn with no human behind it (a channel
    conversation): the AGENT's own id — the same value an api token minted for
    the agent carries as ``principal_agent_id``. ``TurnContext.requested_by``
    is non-null by contract; a user turn passes the user's id instead."""
    return agent_id


@dataclass(frozen=True)
class LlmToolset:
    """The tools one turn may call. ``handler`` may be sync or async and must
    return a :class:`ToolResult`; an exception it raises becomes an error
    result (logged, the text never shown). The registry is the caller's (A2
    brings ``handoff``); the runtime knows no tool by name."""

    tools: tuple[ToolSpec, ...]
    handler: Callable[[ToolCall], "ToolResult | Awaitable[ToolResult]"]
    #: PT-BR one-liner for ``tool.started.resumo``; default ``Executar <name>.``
    resumo: Callable[[str, dict[str, Any]], str] | None = None


ToolsFactory = Callable[[AgentSpec, TurnContext], "LlmToolset | None"]


class LlmTurnSlot:
    """A leased concurrency permit. ``release()`` is async and idempotent (the
    same contract as :class:`~app.runtime.slots.TurnSlot`, which the route and
    the eval runner call)."""

    def __init__(self, limiter: "LlmTurnLimiter") -> None:
        self._limiter = limiter
        self._released = False

    async def release(self) -> None:
        if not self._released:
            self._released = True
            self._limiter._release()


class LlmTurnLimiter:
    """In-process cap on concurrent LLM turns. There is no subprocess to
    isolate (unlike the Bia CLI :class:`~app.runtime.slots.SlotPool`), so a
    counter is the whole mechanism. ``try_reserve`` is synchronous and
    race-free for the same reason the slot pool's is (single worker, no
    ``await`` between check and take)."""

    def __init__(self, capacity: int) -> None:
        self._capacity = max(1, int(capacity))
        self._busy = 0

    def try_reserve(self) -> LlmTurnSlot | None:
        if self._busy >= self._capacity:
            return None
        self._busy += 1
        return LlmTurnSlot(self)

    def _release(self) -> None:
        self._busy = max(0, self._busy - 1)

    def health(self) -> dict[str, int]:
        return {"total": self._capacity, "busy": self._busy, "free": self._capacity - self._busy}


def make_budget_guard(
    *,
    messages: Any | None = None,
    daily_cap_usd: float = 0.0,
    monthly: Callable[[str | None], Awaitable[None]] = enforce_budget,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> BudgetGuard:
    """The per-org pre-turn budget check (§10.1 M4, agents side).

    Two layers, both the seed's data: the seed's monthly BRL budget
    (``enforce_budget`` → ``org_settings.monthly_llm_budget_brl``) and — when
    ``daily_cap_usd > 0`` — a per-org DAILY cap over the turn costs already
    stamped on ``agents.messages`` (``messages.sum_cost_usd_since``). Either
    exhausted ⇒ :class:`LlmCapacityError` (429 ``capacidade``). The monthly
    layer is fail-open by the seed's design (a flaky budget read must not
    take replies down); the daily one reads agents' own table."""

    async def _guard(org_id: UUID) -> None:
        try:
            await monthly(str(org_id))
        except LLMBudgetExceeded as exc:
            raise LlmCapacityError("Orçamento de IA da organização esgotado.", retry_after_seconds=3600) from exc
        if daily_cap_usd > 0 and messages is not None:
            current = now()
            midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
            spent = await asyncio.to_thread(messages.sum_cost_usd_since, org_id, midnight)
            if spent >= daily_cap_usd:
                retry = max(60, int((midnight + timedelta(days=1) - current).total_seconds()))
                raise LlmCapacityError(
                    "Limite diário de IA da organização atingido.", retry_after_seconds=retry
                )

    return _guard


def _map_error(exc: BaseException, provider: str) -> BaseException:
    """Seed/vendor failures → the typed runtime errors. Anything else (a
    programming error) is returned unchanged so it surfaces as the bug it is."""
    if isinstance(exc, LlmRuntimeError):
        return exc
    if isinstance(exc, LLMNotConfigured):
        return LlmNotConfiguredError(provider)
    if isinstance(exc, LLMBudgetExceeded):
        return LlmCapacityError("Orçamento de IA da organização esgotado.", retry_after_seconds=3600)
    if isinstance(exc, (LLMAPIError, ToolCallingNotImplemented)):
        return LlmUpstreamError(str(exc))
    return exc


class LlmToolRuntime:
    """:class:`~app.runtime.types.AgentRuntime` over the seed tool loop."""

    def __init__(
        self,
        *,
        messages: Any,
        key_resolver: KeyResolver,
        limiter: LlmTurnLimiter,
        budget_guard: BudgetGuard | None = None,
        tools_factory: ToolsFactory | None = None,
        provider_impl: Any | None = None,
        history_messages: int = 20,
        max_iterations: int = 6,
        temperature: float = 1.0,
        max_tokens: int | None = None,
        bound_org_id: UUID | None = None,
    ) -> None:
        self._messages = messages
        self._key_resolver = key_resolver
        self._limiter = limiter
        self._budget_guard = budget_guard
        self._tools_factory = tools_factory
        #: Seed seam: a ready provider-like object (tests pass the seed's
        #: ``FakeProvider``). ``None`` ⇒ the registry's real provider.
        self._provider_impl = provider_impl
        self._history_messages = max(0, int(history_messages))
        self._max_iterations = max(1, int(max_iterations))
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._bound_org_id = bound_org_id

    # ── AgentRuntime ────────────────────────────────────────────────────

    def try_reserve(self) -> LlmTurnSlot | None:
        return self._limiter.try_reserve()

    async def preflight(self, provider: str, org_id: UUID) -> None:
        """Refuse BEFORE anything is persisted: no key for this org ⇒
        :class:`LlmNotConfiguredError`, budget exhausted ⇒
        :class:`LlmCapacityError`. :meth:`run_turn` re-checks (a caller that
        skips this still fails closed)."""
        self._resolve_key(provider, org_id)
        if self._budget_guard is not None:
            await self._budget_guard(org_id)

    async def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
        slot: Any | None = None,
    ) -> AsyncIterator[AgentEvent]:
        if self._bound_org_id is not None and ctx.org_id != self._bound_org_id:
            raise ValueError("this LlmToolRuntime was built for a different org")
        await self.preflight(spec.provider, ctx.org_id)
        api_key = self._resolve_key(spec.provider, ctx.org_id)

        toolset = self._tools_factory(spec, ctx) if self._tools_factory is not None else None
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def _handler(call: ToolCall) -> ToolResult:
            assert toolset is not None
            queue.put_nowait(("event", {
                "event": "tool.started",
                "payload": {
                    "tool_use_id": call.call_id,
                    "tool_name": call.name,
                    "classe": "leitura",
                    "resumo": (toolset.resumo(call.name, call.arguments) if toolset.resumo
                               else f"Executar {call.name}."),
                },
            }))
            try:
                result = toolset.handler(call)
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                logger.exception(
                    "agents.llm.tool_failed org_id=%s conversation_id=%s tool=%s",
                    ctx.org_id, ctx.conversation_id, call.name,
                )
                result = ToolResult(call.call_id, _TOOL_FAILED, is_error=True)
            queue.put_nowait(("event", {
                "event": "tool.finished",
                "payload": {
                    "tool_use_id": call.call_id,
                    "tool_name": call.name,
                    "resultado": "erro" if result.is_error else "ok",
                },
            }))
            return result

        chat = functools.partial(
            chat_with_tools,
            model=spec.model,
            provider=spec.provider,
            org_id=str(ctx.org_id),
            api_key=api_key,
            require_explicit_key=True,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            provider_impl=self._provider_impl,
        )
        history = self._history(ctx, prompt)
        messages: list[ChatMessage] = [ChatMessage.system(spec.prompt_append, cache=True)]
        if ctx.contexto is not None:
            # Dynamic per-turn section AFTER the cacheable compiled prompt (§2.1(b)).
            from app.channels.contexto import render_contexto_system

            messages.append(ChatMessage.system(render_contexto_system(ctx.contexto)))
        messages.extend(history)
        if prompt:
            messages.append(ChatMessage.user(prompt))

        async def _run() -> None:
            try:
                result = await run_tool_loop(
                    messages,
                    list(toolset.tools) if toolset else [],
                    _handler if toolset else None,
                    chat=chat,
                    max_iterations=min(self._max_iterations, max(1, spec.max_turns)),
                    fallback_reply=FALLBACK_REPLY,
                )
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001 — handed to the generator, re-raised there
                queue.put_nowait(("error", exc))
            else:
                queue.put_nowait(("done", result))

        task = asyncio.create_task(_run(), name=f"llm-turn-{ctx.conversation_id}")
        try:
            while True:
                kind, value = await queue.get()
                if kind == "event":
                    yield value
                    continue
                if kind == "error":
                    mapped = _map_error(value, spec.provider)
                    if mapped is value:
                        raise value
                    raise mapped from value
                result = value
                break
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        if result.text and result.text.strip():
            yield {
                "event": "message.new",
                "payload": {"role": "assistant", "texto": result.text, "blocks": []},
            }
        usage = result.usage
        yield {
            "event": "session.status",
            "payload": {
                "status": "ociosa",
                "sdk_session_id": None,
                "custo_usd": usage.cost_usd,
                "tokens_entrada": usage.prompt_tokens,
                "tokens_saida": usage.completion_tokens,
                "tokens_cache_leitura": usage.cache_read_tokens,
            },
        }

    async def structured_extract(
        self,
        *,
        provider: str,
        model: str,
        org_id: UUID,
        system: str,
        user: str,
        tool: ToolSpec,
    ) -> tuple[dict[str, Any], Any]:
        """One structured-output call (Lais F-AG ``/resumo``): the model is
        FORCED to call ``tool`` (the provider-neutral structured-output path of
        the seed's tool calling), the call's arguments are returned with the
        turn's ``LLMUsage``. Same org-only key (B1) + budget guard as a turn;
        provider failures map to the typed runtime errors. No persistence here."""
        await self.preflight(provider, org_id)
        api_key = self._resolve_key(provider, org_id)
        try:
            response = await chat_with_tools(
                [ChatMessage.system(system), ChatMessage.user(user)],
                [tool],
                model=model, provider=provider, org_id=str(org_id), api_key=api_key,
                require_explicit_key=True, temperature=0.0, max_tokens=self._max_tokens,
                tool_choice=tool.name, provider_impl=self._provider_impl,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 — mapped to the typed error or re-raised
            mapped = _map_error(exc, provider)
            if mapped is exc:
                raise
            raise mapped from exc
        for call in response.tool_calls:
            if call.name == tool.name:
                return dict(call.arguments or {}), response.usage
        raise LlmUpstreamError("structured output: the model did not call the extraction tool")

    # ── internals ───────────────────────────────────────────────────────

    def _resolve_key(self, provider: str, org_id: UUID) -> str:
        key = self._key_resolver(provider, org_id)
        if not key:
            raise LlmNotConfiguredError(provider)
        return key

    def _history(self, ctx: TurnContext, prompt: str) -> list[ChatMessage]:
        """The conversation's last N stored messages as chat history.

        The route persists the user message BEFORE the turn runs, so the
        stored tail normally IS ``prompt``: that one trailing user row is
        dropped (the prompt is appended once, by the caller of this method).
        A caller that already stored the whole input and has no separate
        prompt passes ``prompt=""`` — nothing is dropped or appended then.
        An ephemeral context (an eval case) has no conversation rows."""
        if ctx.ephemeral or self._history_messages == 0:
            return []
        records = list(
            self._messages.list(ctx.org_id, ctx.conversation_id, limite=self._history_messages + 1)
        )
        if prompt:
            for i in range(len(records) - 1, -1, -1):
                if records[i].role == "user":
                    if records[i].texto == prompt:
                        del records[i]
                    break
        out: list[ChatMessage] = []
        for r in records[-self._history_messages:]:
            if r.role == "user" and r.texto:
                out.append(ChatMessage.user(r.texto))
            elif r.role == "assistant" and r.texto and r.texto.strip():
                out.append(ChatMessage.assistant(r.texto))
            # `system` rows are route notices ("O turno falhou."), never model input.
        return out
