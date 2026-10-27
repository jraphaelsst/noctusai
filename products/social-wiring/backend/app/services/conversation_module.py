"""Conversation framework wiring for the Social Wiring bot.

Adopts the seed `noctusai_lib.domain.chatbot` Redis-backed buffer + worker
so WhatsApp inbounds **accumulate** across short bursts ("broken messages")
before the LLM/intake-state-machine reacts. Solves the longstanding gap
where receiving a property code in one message and the Drive URL in a
second message seconds later would fire two separate (and noisy) LLM
calls instead of one combined intent.

**Lifecycle map** — what the seed owns vs. what this product owns.

Seed-owned (`noctusai_lib.domain.chatbot`):

  - ``ConversationBufferService`` (Redis-backed memory + debounce + idle queue)
  - ``ConversationWorker`` (poll + due-conversation dispatch)

Product-owned (this module):

  - ``ConversationModule`` container held by app lifespan.
  - ``configure_conversation_module(...)`` startup wiring.
  - ``start_worker()`` / ``stop_worker()`` lifespan hooks.
  - ``_build_processor(...)`` — the heart: regex-first extraction over the
    accumulated inbound buffer, LLM fallback when regex misses,
    paragraph-split outbound emission via ``whatsapp_outbound``.

**Threading model.** ``ConversationWorker.run_forever()`` is **synchronous**
(uses ``time.sleep``). We schedule it via ``asyncio.to_thread(...)`` from
lifespan startup so the poll-loop doesn't block the asyncio event loop. The
processor closure, running in the worker thread, dispatches async work
(WAHA send, LLM tool-loop) back to the main loop via
``asyncio.run_coroutine_threadsafe(...)`` and blocks the worker thread on
the resulting future. The worker thread is dedicated to one conversation
at a time, so blocking it is fine for OPERATOR keys; the asyncio loop stays
responsive for other requests in parallel.

**Lead keys never block the worker thread.** A Julia lead turn is a slow HTTP
call to agents, so ``lead:`` keys are handed to ``LeadTurnDispatcher``
(``julia_lead_dispatcher``): bounded concurrency across chats
(``julia_agente_max_concurrent_turns``), one in-flight turn per key.

**Memory key unification.** The seed buffer uses the prefix
``conversation:memory:`` for its memory lists. ``chatbot_service.py``
historically used ``whatsapp:chatbot:``. We unify on the seed prefix so
the worker's processor and the chatbot read/write the same Redis list —
otherwise the chatbot would miss the inbound that the webhook buffered.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol
from uuid import UUID

from noctusai_lib.domain.real_estate import PRODUCT_CODE_SCAN_PATTERN
from noctusai_lib.domain.chatbot import (
    ConversationBufferService,
    ConversationWorker,
)
from noctusai_lib.integrations.redis import (
    make_fake_redis_client,
    make_redis_client,
)
from noctusai_lib.primitives.tasks import schedule_coro

from app.config import settings
from app.services.julia_agente_service import LEAD_PREFIX

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex extractor — fast path that bypasses the LLM when the buffered
# inbound text contains a well-formed product code + Drive URL.
#
# Aligned with the operator-side message template:
#     "ONE7360
#      https://drive.google.com/drive/folders/1uDh..."
#
# Order-agnostic by design (the buffer accumulates messages across N
# inbounds before the worker fires, so either ordering joins to the same
# blob).
# ---------------------------------------------------------------------------
# Canonical scanner — imported, never re-declared. Three hand-synced copies
# of this pattern previously drifted; see the seed module's docstring.
_PRODUCT_CODE_RE = PRODUCT_CODE_SCAN_PATTERN
_DRIVE_URL_RE = re.compile(
    r"https?://(?:drive|docs)\.google\.com/[^\s]+",
    re.IGNORECASE,
)


def _regex_extract(text: str) -> tuple[str | None, str | None]:
    """Return ``(product_code, drive_url)`` extracted from ``text``.

    Both fields are independently optional; the caller decides what to
    do when only one is present (LLM fallback for completion). Product
    code is uppercased to match the canonical ``ONE\\d{3,6}`` form.
    """
    code_match = _PRODUCT_CODE_RE.search(text)
    url_match = _DRIVE_URL_RE.search(text)
    code = code_match.group(0).upper() if code_match else None
    drive_url = url_match.group(0) if url_match else None
    return code, drive_url


def _join_unanswered_inbound(memory: list[dict[str, Any]]) -> str:
    """Join the trailing inbound run since the last outbound.

    The buffer memory is oldest-first. We walk back to the last
    ``direction == "outbound"`` entry and join every inbound after it
    with newlines. This is the text the regex extractor + LLM see — it
    represents *what the user has said since the bot last replied*,
    which is exactly the multi-message intent we want to react to.
    """
    last_outbound_idx = -1
    for idx in range(len(memory) - 1, -1, -1):
        if memory[idx].get("direction") == "outbound":
            last_outbound_idx = idx
            break
    inbound_run = memory[last_outbound_idx + 1 :]
    texts = [str(item.get("text") or "").strip() for item in inbound_run if item.get("direction") == "inbound"]
    return "\n".join(t for t in texts if t)


# ---------------------------------------------------------------------------
# Conversation module — held as a process-wide singleton by app lifespan.
# ---------------------------------------------------------------------------
@dataclass
class ConversationModule:
    """Wired conversation framework. Built once per app start.

    Attributes:
        buffer: Redis-backed buffer service (the seed primitive).
        worker: Polling worker dispatcher.
        main_loop: The asyncio loop captured at startup; the processor
            uses this to dispatch async work from the worker thread.
        worker_task: Background asyncio task wrapping ``worker.run_forever``.
            Lifespan shutdown sets ``worker.should_stop = True`` then
            awaits this task.
        admin_supabase: Admin client used for downstream service builds
            (intake service, MessageStore writes).
        org_id: Default org UUID stamped on uploads triggered via this
            conversation path.
    """

    buffer: ConversationBufferService
    worker: ConversationWorker
    main_loop: asyncio.AbstractEventLoop
    admin_supabase: Any
    org_id: UUID
    worker_task: Optional[asyncio.Task] = field(default=None)
    lead_dispatcher: Optional[Any] = field(default=None)


_module: Optional[ConversationModule] = None
_module_lock = threading.Lock()


def get_conversation_module() -> Optional[ConversationModule]:
    """Return the configured ``ConversationModule`` or ``None`` if the
    lifespan startup short-circuited (e.g. missing admin client).

    Callers MUST tolerate ``None`` — the webhook handles a missing module
    by falling back to the inline-reply path so single-process dev still
    works.
    """
    return _module


def configure_conversation_module(
    *,
    admin_supabase: Any,
    org_id: UUID,
    redis_client: Any = None,
    main_loop: Optional[asyncio.AbstractEventLoop] = None,
    agents_client_factory: Optional[Callable[[UUID], Any]] = None,
    waha_factory: Optional[Callable[..., Any]] = None,
    cfg: Any = None,
) -> ConversationModule:
    """Build + cache the ``ConversationModule``.

    Called once at lifespan startup. The asyncio loop is captured here
    so the worker thread's processor can dispatch async work back to it.

    Args:
        admin_supabase: Supabase admin client (service-role-keyed).
        org_id: Default org UUID for downstream MessageStore writes.
        redis_client: Optional ``RedisBufferClient``. Defaults to the real
            client when ``settings.redis_url`` is set, else the in-memory
            Fake for test/dev paths.
        main_loop: Optional event loop override (tests). Defaults to the
            running loop at startup time.
        agents_client_factory: ``org_id -> AgentsClient | None`` for the Julia lead
            path (contract 10.2 B2). Default = the org's ``api_key:agents`` token
            (``julia_agente_service.resolve_agents_client``). The DI seam tests use
            to script agents' replies.
        waha_factory: ``(base_url=, api_key=, session=) -> WAHA client`` for the lead
            path's sends. Default = the seed ``get_whatsapp_client``.
        cfg: settings object the lead path reads (default: the module singleton).
    """
    global _module
    with _module_lock:
        if _module is not None:
            logger.debug("ConversationModule already configured; reusing existing instance.")
            return _module

        redis = redis_client if redis_client is not None else _build_redis_client()
        loop = main_loop or asyncio.get_event_loop()

        buffer = ConversationBufferService(
            redis_client=redis,
            memory_ttl_seconds=settings.conversation_memory_ttl_seconds,
            debounce_seconds=settings.message_debounce_seconds,
        )

        lead_dispatcher = _build_lead_dispatcher(
            buffer=buffer,
            admin_supabase=admin_supabase,
            agents_client_factory=agents_client_factory,
            waha_factory=waha_factory,
            cfg=cfg,
        )
        worker = ConversationWorker(
            buffer_service=buffer,
            processor=_build_processor(
                buffer=buffer,
                main_loop=loop,
                admin_supabase=admin_supabase,
                org_id=org_id,
                lead_dispatcher=lead_dispatcher,
            ),
            idle_processor=None,
            poll_seconds=2.0,
        )

        _module = ConversationModule(
            buffer=buffer,
            worker=worker,
            main_loop=loop,
            admin_supabase=admin_supabase,
            org_id=org_id,
            lead_dispatcher=lead_dispatcher,
        )

    logger.info(
        "ConversationModule configured: debounce=%ss memory_ttl=%ss org_id=%s",
        settings.message_debounce_seconds,
        settings.conversation_memory_ttl_seconds,
        org_id,
    )
    return _module


def _build_redis_client() -> Any:
    """Return a real Redis client when ``settings.redis_url`` is set, else
    the in-memory Fake. ``KB § PATTERNS/seed-fake-real-adapter.md`` — the
    Fake is a first-class adapter, not "dev-only"."""
    redis_url = getattr(settings, "redis_url", None) or ""
    if redis_url:
        try:
            return make_redis_client(redis_url)
        except Exception:
            logger.exception("Real Redis unavailable; falling back to FakeRedis.")
    logger.info("ConversationBuffer using in-memory FakeRedis (no persistence across restarts).")
    return make_fake_redis_client()


# ---------------------------------------------------------------------------
# Processor — invoked by the worker thread for each due conversation.
#
# Sequence:
#
#   1. Compute the unanswered-inbound run from the buffer memory.
#   2. Skip if empty (e.g. an outbound bumped the timer but no new inbound).
#   3. Regex extractor: if both ONE-code AND Drive URL present → fast path
#      (hand to the WhatsAppIntakeService state machine; saves LLM tokens
#      for the structured-input case the operator's team uses 90% of the
#      time per user direction).
#   4. LLM fallback: instantiate ChatbotService (or its surface-agnostic
#      replacement) and pass the joined unanswered text in. Memory writes
#      are suppressed on the chatbot side; the processor writes the
#      outbound to the buffer afterward so both inbound + outbound live
#      in the same Redis list.
#   5. Outbound emission via ``whatsapp_outbound.send_paragraphs`` —
#      splits on \\n\\n + sends one WAHA message per paragraph with a
#      short inter-message delay (toggleable via
#      ``settings.whatsapp_paragraph_split``).
# ---------------------------------------------------------------------------

PROCESSOR_TIMEOUT_S = 180.0
"""Hard timeout per dispatched conversation. Covers LLM tool-loop
latency + WAHA send roundtrips. Far above expected tail latency; the
exception path logs + moves on so a single stuck conversation doesn't
freeze the worker thread."""


def _build_processor(
    *,
    buffer: ConversationBufferService,
    main_loop: asyncio.AbstractEventLoop,
    admin_supabase: Any,
    org_id: UUID,
    lead_dispatcher: Any,
):
    """Return the ``ConversationProcessor`` closure the worker invokes.

    Args mirror ``ConversationModule`` so the closure has everything it
    needs without re-resolving at dispatch time (the worker thread isn't
    on the asyncio loop and can't easily call back into request-scoped
    factories).
    """

    def _process(conversation_id: str, memory: list[dict[str, Any]]) -> None:
        # Julia (lead agent, contract 10.2 B2): `lead:<connection_id>:<chat_id>`
        # keys resolve their OWN org + connection from the key and carry every
        # provider_message_id -- they never enter the operator path below (no
        # intake, no ChatbotService, no operator tools).
        if conversation_id.startswith(LEAD_PREFIX):
            # Hand over, never block: a lead turn is a slow HTTP call to agents and
            # must not hold this (single) worker thread -- see julia_lead_dispatcher.
            lead_dispatcher.submit_threadsafe(main_loop, conversation_id, memory)
            return

        unanswered = _join_unanswered_inbound(memory)
        if not unanswered.strip():
            logger.debug("conv=%s: no unanswered inbound, skipping dispatch.", conversation_id)
            return

        coro = _dispatch_conversation(
            buffer=buffer,
            admin_supabase=admin_supabase,
            org_id=org_id,
            conversation_id=conversation_id,
            joined_inbound=unanswered,
        )
        future = asyncio.run_coroutine_threadsafe(coro, main_loop)
        try:
            future.result(timeout=PROCESSOR_TIMEOUT_S)
        except Exception:
            logger.exception("conv=%s: dispatch failed", conversation_id)

    return _process


def _build_lead_dispatcher(
    *,
    buffer: ConversationBufferService,
    admin_supabase: Any,
    agents_client_factory: Optional[Callable[[UUID], Any]],
    waha_factory: Optional[Callable[..., Any]],
    cfg: Any = None,
):
    from app.services.julia_lead_dispatcher import LeadTurnDispatcher

    effective = cfg if cfg is not None else settings

    async def _run(key: str, memory: list[dict[str, Any]]) -> None:
        await _dispatch_lead(
            key, memory, buffer=buffer, admin_supabase=admin_supabase,
            agents_client_factory=agents_client_factory, waha_factory=waha_factory, cfg=cfg,
        )

    return LeadTurnDispatcher(
        _run,
        max_concurrent=getattr(effective, "julia_agente_max_concurrent_turns", 4),
        timeout_s=PROCESSOR_TIMEOUT_S,
        reload_memory=buffer.memory_for,
    )


async def _dispatch_lead(
    conversation_id: str,
    memory: list[dict[str, Any]],
    *,
    buffer: ConversationBufferService,
    admin_supabase: Any,
    agents_client_factory: Optional[Callable[[UUID], Any]],
    waha_factory: Optional[Callable[..., Any]],
    cfg: Any = None,
) -> None:
    """Run one Julia batch on the main loop (late import: the lead service pulls in
    the stores + agents client, none of which the operator path needs)."""
    from app.services.julia_lead_turn_service import LeadDeps, process_lead_batch

    deps = LeadDeps(
        buffer=buffer, admin=admin_supabase, cfg=cfg if cfg is not None else settings,
        agents_client_factory=agents_client_factory, waha_factory=waha_factory,
    )
    await process_lead_batch(conversation_id, memory, deps=deps)


class ChatCommands(Protocol):
    """Typed post-upload commands (``ONE10874 privacidade publico`` …) —
    deterministic, no model. ``try_handle`` returns the reply, or None when
    the text is not a command (nor the answer to a pending confirmation)."""

    def has_pending_confirmation(self, session_id: str) -> bool: ...

    async def try_handle(self, session_id: str, text: str) -> Optional[str]: ...


LlmFallback = Callable[[str], Awaitable[None]]


async def route_inbound(
    *,
    intake: Any,
    session_id: str,
    text: str,
    llm_fallback: LlmFallback,
    commands: Optional[ChatCommands] = None,
    attached_file_id: Optional[str] = None,
) -> str:
    """Code-first routing for the YouTube upload chat — ONE order for
    WhatsApp and the platform chat. A model is consulted only when every
    deterministic path declines. Returns the path taken (logs + tests).

      1. ``command-confirm`` — a typed command (e.g. ``apagar``) is waiting
         for its sim/não.
      2. ``state-machine`` — the upload flow is mid-question (sim/não, manual
         title, video choice): ``intake.handle_message`` owns the reply.
         Regex + LLM would both misread a bare ``"1"`` or ``"sim"``.
      3. ``command`` — a typed post-upload command.
      4. ``upload-file`` — platform chat: a video is attached and the text
         carries a property code.
      5. ``upload-drive`` — the text carries a property code + Drive URL.
      6. ``llm`` — everything else (free-form questions, partial requests).

    Replies go out through the intake (WhatsApp send, or memory + the web
    request's collector), so callers never format messages themselves.
    """
    if commands is not None and commands.has_pending_confirmation(session_id):
        reply = await commands.try_handle(session_id, text)
        if reply is not None:
            await intake.send_reply(session_id, reply)
            return "command-confirm"

    pending = None
    try:
        pending = await intake._get_state(session_id)
    except Exception:
        logger.exception("conv=%s: intake state lookup failed", session_id)
    current_state = pending.state if pending else "idle"
    if current_state != "idle":
        logger.info("conv=%s: state-machine path (state=%s)", session_id, current_state)
        await intake.handle_message(session_id, text)
        return "state-machine"

    if commands is not None:
        reply = await commands.try_handle(session_id, text)
        if reply is not None:
            logger.info("conv=%s: typed command path", session_id)
            await intake.send_reply(session_id, reply)
            return "command"

    code, drive_url = _regex_extract(text)
    if attached_file_id and code:
        logger.info("conv=%s: attached-file upload path (code=%s)", session_id, code)
        await intake.start_file_upload(session_id, product_code=code, file_id=attached_file_id)
        return "upload-file"

    if code and drive_url:
        logger.info(
            "conv=%s: regex fast-path matched (code=%s, drive=%s)",
            session_id,
            code,
            drive_url[:60] + ("…" if len(drive_url) > 60 else ""),
        )
        await intake.handle_message(session_id, text)
        return "upload-drive"

    logger.info(
        "conv=%s: deterministic paths declined (code=%s, drive=%s) → LLM fallback",
        session_id,
        code,
        bool(drive_url),
    )
    await llm_fallback(text)
    return "llm"


async def _dispatch_conversation(
    *,
    buffer: ConversationBufferService,
    admin_supabase: Any,
    org_id: UUID,
    conversation_id: str,
    joined_inbound: str,
) -> None:
    """WhatsApp worker entry: build the intake and run :func:`route_inbound`
    over the buffered inbound run. Failures are logged, never raised — the
    worker thread must keep draining other conversations."""
    del buffer  # intake._reply writes outbound to the unified buffer key
    from app.routers.whatsapp_router import build_intake_service_for_processor

    intake = await build_intake_service_for_processor(
        admin_supabase=admin_supabase,
        org_id=org_id,
    )
    if intake is None:
        logger.warning("conv=%s: intake service unavailable", conversation_id)
        return

    async def _llm(text: str) -> None:
        await _llm_fallback_dispatch_inner(
            intake=intake,
            conversation_id=conversation_id,
            joined_inbound=text,
        )

    try:
        await route_inbound(
            intake=intake,
            session_id=conversation_id,
            text=joined_inbound,
            llm_fallback=_llm,
        )
    except Exception:
        logger.exception("conv=%s: route_inbound failed", conversation_id)


async def _llm_fallback_dispatch_inner(
    *,
    intake: Any,
    conversation_id: str,
    joined_inbound: str,
) -> None:
    """LLM fallback: run the tool-calling chatbot (Anthropic) over the buffered
    text and send the reply via the paragraph-splitter.

    Called from ``_dispatch_conversation`` after the state-machine check
    + regex extractor have both declined. ``intake`` is pre-built so we
    don't pay the constructor cost twice.

    Memory writes are suppressed on the chatbot side (``append_inbound=False,
    append_outbound=False``) because the seed buffer already wrote the
    per-message inbounds, and ``send_paragraphs`` writes the outbound via
    ``intake._reply`` which lands on the same unified buffer key.
    """
    from app.services.chatbot_service import ChatbotService
    from app.services.whatsapp_outbound import send_paragraphs

    chatbot = ChatbotService(
        redis_client=intake.redis_client,
        intake_service=intake,
        session_id=conversation_id,
        model=settings.chatbot_llm_model,
    )
    try:
        reply = await chatbot.reply(
            joined_inbound,
            append_inbound=False,
            append_outbound=False,
        )
    except Exception:
        logger.exception("conv=%s LLM-fallback: chatbot.reply failed", conversation_id)
        return

    if not reply:
        logger.info("conv=%s LLM-fallback: empty reply, nothing to send", conversation_id)
        return

    try:
        await send_paragraphs(intake=intake, sender=conversation_id, text=reply)
    except Exception:
        logger.exception("conv=%s LLM-fallback: send_paragraphs failed", conversation_id)


# ---------------------------------------------------------------------------
# Worker lifecycle — start/stop from lifespan.
# ---------------------------------------------------------------------------

async def _run_worker_in_thread(worker: ConversationWorker) -> None:
    """Wrap the synchronous ``worker.run_forever()`` so it can be scheduled
    on the event loop. The worker's ``should_stop`` flag (set by
    ``stop_worker``) lets the poll loop exit cleanly; the wrapping
    coroutine resolves shortly after."""
    await asyncio.to_thread(worker.run_forever)


def start_worker() -> Optional[asyncio.Task]:
    """Start the conversation worker as a background asyncio task.

    Safe to call when the module is unconfigured (returns ``None`` with a
    WARN so the lifespan hook can continue). Idempotent — re-entry with
    an already-running task logs at WARNING and returns the existing
    handle.
    """
    module = _module
    if module is None:
        logger.warning("start_worker: conversation module not configured; skipping.")
        return None
    if module.worker_task is not None and not module.worker_task.done():
        logger.warning("ConversationWorker already running; skipping start.")
        return module.worker_task

    task = schedule_coro(
        _run_worker_in_thread(module.worker),
        logger=logger,
        name="social-wiring-conversation-worker",
    )
    module.worker_task = task
    logger.info(
        "ConversationWorker scheduled (poll_seconds=%.1f, debounce=%ss).",
        module.worker.poll_seconds,
        settings.message_debounce_seconds,
    )
    return task


async def stop_worker(timeout: float = 5.0) -> None:
    """Signal the worker to stop + await its task with a timeout.

    Per ``ConversationWorker.stop()``, setting ``should_stop=True`` causes
    the next poll iteration to exit. The to_thread-wrapped coroutine then
    resolves and the asyncio task completes. If the worker is mid-sleep,
    it can take up to ``poll_seconds`` (2s by default) for the loop to
    notice — the timeout cancels the task hard at that point.
    """
    module = _module
    if module is not None and module.lead_dispatcher is not None:
        await module.lead_dispatcher.shutdown(grace_s=timeout)
    if module is None or module.worker_task is None:
        return
    module.worker.stop()
    try:
        await asyncio.wait_for(module.worker_task, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "ConversationWorker did not stop within %.1fs; cancelling task.",
            timeout,
        )
        module.worker_task.cancel()
    finally:
        module.worker_task = None


def _reset_for_tests() -> None:
    """Test helper — clears the module-level singleton."""
    global _module
    with _module_lock:
        _module = None


__all__ = [
    "ConversationModule",
    "configure_conversation_module",
    "get_conversation_module",
    "start_worker",
    "stop_worker",
]
