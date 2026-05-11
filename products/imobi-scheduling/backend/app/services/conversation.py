"""Conversation framework wiring for the Imobi Scheduling bot.

**Lifecycle map** — what this module owns vs. what the seed owns.

Seed-owned (`noctusai_lib.domain.chatbot`):

  - ``ConversationBufferService`` (Redis-backed memory + debounce + idle queue)
  - ``LLMDispatcher`` (OpenAI tool-loop, audit-writer seam)
  - ``ConversationWorker`` (poll + due-conversation dispatch + idle sweep)
  - ``memory_to_chat_messages`` (buffer payload → OpenAI message shape)

Product-owned (this module):

  - System prompt loading (`build_system_prompt()` reads
    ``app/prompts/scheduling_bot.md`` once at module import).
  - OpenAI client construction (uses the ``OPENAI_API_KEY`` env var by
    default; the test path patches ``app.services.conversation.OpenAI``).
  - Per-conversation ``processor`` closure that the seed worker invokes
    for every due conversation — composes system + memory → dispatcher
    reply → outbound persist.
  - Audit-writer adapter (`app.services.tool_audit.make_supabase_audit_writer`)
    threaded through into the dispatcher.

**Lifespan startup contract.**

  - `configure_conversation_module(...)` (the closest seam shape the
    seed exposes — see `KB § PATTERNS/whatsapp-chatbot-seed.md`) does
    NOT exist as a single seed factory. The seed wires by constructor —
    instantiate `ConversationBufferService`, `LLMDispatcher`,
    `ConversationWorker`, pass them around. This module is that
    wiring step. Verified 2026-05-11 via direct seed read.
  - `default_audit_writer(db)` does NOT exist either; the seed ships
    `make_audit_writer(db, table_class)` for the SQLAlchemy-backed
    consumer shape only. The Supabase-backed shape is supplied by
    `app.services.tool_audit.make_supabase_audit_writer(...)`.

Both gaps are tracked in PROJECT.md §6 Phase 6 ``**Improvements:**``.

**Worker dispatch via `schedule_coro`.** `ConversationWorker.run_forever()`
is **synchronous** (uses `time.sleep`). To start it as an asyncio
background task per the brief, wrap via `asyncio.to_thread(...)`. The
resulting coroutine is then passed to `schedule_coro(...)` from
`noctusai_lib.primitives.tasks`. Lifespan shutdown sets
`worker.should_stop = True`; the next poll-iteration exits the loop and
the to_thread coroutine resolves.

**Tool-loop dispatch** — every authorized inbound flows:

  1. `app.routers.whatsapp_router.handle_inbound_whatsapp` resolves auth.
  2. Phase 7+ will queue the inbound into the buffer via
     `buffer_inbound(...)` here.
  3. Worker drains the due queue, calls `dispatch_conversation(...)`.
  4. Dispatcher invokes tool handlers (`app.services.tool_registry`);
     audit writer persists rows.
  5. Outbound reply lands back in WhatsApp via the WAHA send-text
     adapter (Phase 5 wiring; Phase 6 returns the reply but does NOT
     emit it — emission lands at Phase 7 when the buffer+worker actually
     drain inbound messages from authorized users).
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.chatbot import (
    ConversationBufferService,
    ConversationWorker,
    LLMDispatcher,
    memory_to_chat_messages,
)
from noctusai_lib.integrations.redis import (
    make_fake_redis_client,
    make_redis_client,
)
from noctusai_lib.primitives.tasks import schedule_coro

from app.config import settings
from app.services.calendar import create_calendar_event, get_calendar_module
from app.services.maps import get_maps_module
from app.services.scheduling import SchedulingService, build_rules
from app.services.tool_audit import make_supabase_audit_writer
from app.services.tool_registry import TOOL_DESCRIPTORS, build_tool_handler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt — read once at import time per project §6 Phase 6.
# ---------------------------------------------------------------------------
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "scheduling_bot.md"


def build_system_prompt() -> str:
    """Return the pt-BR system prompt prose (file body only — markdown
    header is stripped to keep the LLM-facing payload clean).

    Reads `app/prompts/scheduling_bot.md` on every call. Cheap (file is
    <2KB) and avoids stale-cache surprises in long-lived processes.
    Tests calling this function should not patch the file at runtime —
    use module-level monkeypatching of ``build_system_prompt`` itself
    if a different prompt is needed.
    """
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    # Strip the leading H1 + blockquote prelude (lines starting with
    # ``# `` or ``> `` at file top) — the actual instructions begin at
    # the first ``Você`` paragraph. Keep all body content otherwise.
    lines = raw.splitlines()
    body_start = 0
    for idx, line in enumerate(lines):
        if line.strip().startswith("Você"):
            body_start = idx
            break
    return "\n".join(lines[body_start:]).strip()


# OpenAI is imported lazily inside the factory to keep import-time cheap
# (matches the seed's `make_redis_client` pattern) AND to give tests a
# single patch point (`patch.object(app.services.conversation, "OpenAI", ...)`).
def _import_openai() -> Any:
    """Import + return the OpenAI client class. Indirection lets tests
    patch via ``patch.object(app.services.conversation, '_import_openai', ...)``
    or replace the global ``OpenAI`` attribute below."""
    from openai import OpenAI

    return OpenAI


# Re-bind under a module-level name so tests can patch via
# ``patch.object(app.services.conversation, 'OpenAI', MockOpenAIClass)``
# matching the no-monkey-patching-of-our-own-code rule (the seam IS the
# external OpenAI SDK, which is allowed to be patched).
OpenAI: Any = None


def _resolve_openai_class() -> Any:
    """Return the OpenAI client class — either the module-level
    ``OpenAI`` (set by tests) or freshly imported from the SDK."""
    return OpenAI if OpenAI is not None else _import_openai()


# ---------------------------------------------------------------------------
# Conversation module — top-level wiring object held by app lifespan.
#
# Acts as a "configure_conversation_module" container — the seed doesn't
# ship one but the project §6 Phase 6 brief speaks in those terms, so we
# adopt the shape here. The container holds every wire (buffer / dispatcher
# / worker / audit) and exposes them as attributes so app code (and tests)
# can reach in without re-constructing.
# ---------------------------------------------------------------------------
@dataclass
class ConversationModule:
    """Wired conversation framework. Built once per app start; held by
    the FastAPI lifespan.

    Attributes:
        buffer: Redis-backed buffer service.
        dispatcher: OpenAI tool-loop dispatcher.
        worker: Polling worker. Started via `schedule_coro` in lifespan.
        audit_writer: Adapter that persists tool-call audit rows.
        worker_task: The asyncio Task wrapping `worker.run_forever()`.
            Set by `start_worker()`; None until startup. Lifespan shutdown
            sets `worker.should_stop = True` then awaits this task.
    """

    buffer: ConversationBufferService
    dispatcher: LLMDispatcher
    worker: ConversationWorker
    audit_writer: Any  # Callable[[ToolCall, ToolResult], None]
    scheduling_service: SchedulingService
    worker_task: Optional[asyncio.Task] = field(default=None)


# Module-level singleton populated by `configure_conversation_module(...)`.
_module: Optional[ConversationModule] = None


def get_conversation_module() -> ConversationModule:
    """Return the configured `ConversationModule` (raises if not yet wired).

    Test fixtures can monkeypatch the module-level `_module` to inject a
    stub container.
    """
    if _module is None:
        raise RuntimeError(
            "Conversation module is not configured. "
            "Call `configure_conversation_module(...)` from lifespan startup."
        )
    return _module


def configure_conversation_module(
    *,
    admin_client: Any,
    org_id: UUID,
    redis_client: Any = None,
    openai_api_key: Optional[str] = None,
) -> ConversationModule:
    """Build + cache the `ConversationModule`.

    Called once at lifespan startup (or in tests). The shape mirrors
    the brief's `configure_conversation_module(audit_writer=...)` —
    audit_writer is built INTERNALLY from `admin_client` + `org_id`
    (no consumer has a reason to construct it standalone).

    Args:
        admin_client: Supabase admin client (service-role-keyed). Required
            for the audit-writer to scope rows to `imobi_scheduling.tool_call_audits`.
        org_id: Single-agency v1 org UUID stamped on every audit row.
        redis_client: Optional `RedisBufferClient`. Defaults to
            `make_redis_client(settings.redis_url)` if `settings.redis_url`
            is set, else `make_fake_redis_client()` for test/dev paths.
        openai_api_key: Optional override; defaults to env `OPENAI_API_KEY`.

    Returns:
        The configured module (also cached at module-level so
        `get_conversation_module()` works without re-passing arguments).
    """
    global _module

    redis = redis_client if redis_client is not None else _build_redis_client()

    buffer = ConversationBufferService(
        redis_client=redis,
        memory_ttl_seconds=settings.conversation_memory_ttl_seconds,
        debounce_seconds=settings.message_debounce_seconds,
    )

    openai_cls = _resolve_openai_class()
    key = openai_api_key or os.environ.get("OPENAI_API_KEY")
    openai_client = openai_cls(api_key=key) if key else openai_cls()
    dispatcher = LLMDispatcher(client=openai_client, model=settings.openai_model)

    audit_writer = make_supabase_audit_writer(
        admin_client=admin_client,
        org_id=org_id,
    )

    # Phase 7 — scheduling-engine wiring. SchedulingService owns the
    # SchedulingEngine instance + DB orchestration; the tool handler
    # routes `lookup_property` / `propose_appointment` /
    # `confirm_appointment` through it when wired.
    #
    # Phase 8 — Calendar + Maps composition. The Maps `travel_lookup` is
    # consumed by the scheduling engine's `Scorer` + `Conflict` rules; the
    # Calendar `create_calendar_event` is consumed by `confirm_appointment`
    # BEFORE the DB insert (compensation rule: failed Calendar create
    # aborts the booking). Both modules are configured by lifespan
    # startup and read via their respective `get_*_module()` getters.
    # When their lifespan-startup wasn't run (test paths that skip the
    # full lifespan), the getters raise — we tolerate by reaching for
    # the module's getter with a try/except that drops to Phase-7 defaults.
    travel_lookup = None
    try:
        travel_lookup = get_maps_module().travel_lookup
    except RuntimeError:
        logger.info(
            "Maps module not configured; SchedulingService falling back to "
            "ZeroTravelLookup (Phase 7 default)."
        )

    calendar_factory = None
    try:
        get_calendar_module()
        calendar_factory = create_calendar_event
    except RuntimeError:
        logger.info(
            "Calendar module not configured; SchedulingService.confirm_appointment "
            "will skip Calendar event creation (Phase 7 DB-only path)."
        )

    scheduling_service = SchedulingService(
        admin_client=admin_client,
        org_id=org_id,
        rules=build_rules(settings),
        travel_lookup=travel_lookup,
        calendar_event_factory=calendar_factory,
    )

    worker = ConversationWorker(
        buffer_service=buffer,
        processor=_build_processor(
            buffer, dispatcher, audit_writer, scheduling_service,
        ),
        idle_processor=None,  # Phase 6 wires only the due-conversation path.
    )

    _module = ConversationModule(
        buffer=buffer,
        dispatcher=dispatcher,
        worker=worker,
        audit_writer=audit_writer,
        scheduling_service=scheduling_service,
    )

    logger.info(
        "Conversation module configured: model=%s schema=imobi_scheduling org_id=%s",
        settings.openai_model,
        org_id,
    )
    return _module


def _build_redis_client() -> Any:
    """Return a real Redis client when configured, else the in-memory
    Fake. Settings expose `redis_url` via `BaseAppSettings`; empty
    string / None → Fake. Per `KB § PATTERNS/seed-fake-real-adapter.md`,
    the Fake is a first-class adapter (not "dev-only")."""
    redis_url = getattr(settings, "redis_url", None) or ""
    if redis_url:
        return make_redis_client(redis_url)
    logger.info(
        "REDIS_URL unset — conversation buffer using in-memory FakeRedis. "
        "Set REDIS_URL=redis://... for persistence."
    )
    return make_fake_redis_client()


def _build_processor(
    buffer: ConversationBufferService,
    dispatcher: LLMDispatcher,
    audit_writer: Any,
    scheduling_service: SchedulingService,
):
    """Build the per-conversation processor the worker invokes.

    Closure captures the buffer / dispatcher / audit_writer /
    scheduling_service. The worker invokes
    `processor(conversation_id, memory)` for each due conversation. The
    processor:

      1. Composes the messages list (system prompt + memory turns).
      2. Calls `dispatcher.reply(messages=..., tools=..., tool_handler=...,
         audit_writer=...)` — the dispatcher loops through tool calls,
         persisting audit rows per call.
      3. Logs the reply text (Phase 7 stops here — outbound emission to
         WAHA is wired in a follow-up phase together with full inbound
         draining).

    Returns:
        `Callable[[str, list[dict]], None]` matching
        `noctusai_lib.domain.chatbot.ConversationProcessor`.
    """
    handler = build_tool_handler(scheduling_service=scheduling_service)
    system_prompt = build_system_prompt()

    def _process(conversation_id: str, memory: list[dict[str, Any]]) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *memory_to_chat_messages(memory),
        ]
        try:
            reply = dispatcher.reply(
                messages=messages,
                tools=TOOL_DESCRIPTORS,
                tool_handler=handler,
                audit_writer=audit_writer,
            )
        except Exception:
            logger.exception(
                "Conversation dispatch failed: conversation_id=%s",
                conversation_id,
            )
            return
        # Phase 6 stops at logging the reply. Phase 7 wires outbound
        # emission to WAHA via the WhatsApp client + persists the
        # outbound turn to the buffer via `buffer.append_to_memory(...)`.
        logger.info(
            "Conversation reply generated: conversation_id=%s reply=%s",
            conversation_id,
            reply[:120] + ("…" if len(reply) > 120 else ""),
        )

    return _process


# ---------------------------------------------------------------------------
# Worker start/stop — invoked from lifespan via `schedule_coro`.
# ---------------------------------------------------------------------------

async def _run_worker_in_thread(worker: ConversationWorker) -> None:
    """Wrap the **synchronous** `worker.run_forever()` so it can be
    scheduled on the event loop as an asyncio task.

    `ConversationWorker.run_forever()` uses `time.sleep(...)` between
    poll iterations — running it on the event loop directly would block
    the FastAPI request handlers. `asyncio.to_thread(...)` runs it in
    the default executor; the worker's own `should_stop` flag (set by
    `stop_worker()`) lets the loop exit cleanly.
    """
    await asyncio.to_thread(worker.run_forever)


def start_worker() -> asyncio.Task:
    """Start the conversation worker as a background asyncio task.

    Called from FastAPI lifespan startup. Returns the task so lifespan
    shutdown can `await` it after `should_stop=True`.

    Raises:
        RuntimeError: If the conversation module is not configured.
    """
    module = get_conversation_module()
    if module.worker_task is not None and not module.worker_task.done():
        logger.warning("ConversationWorker already running; skipping start.")
        return module.worker_task

    task = schedule_coro(
        _run_worker_in_thread(module.worker),
        logger=logger,
        name="imobi-scheduling-conversation-worker",
    )
    module.worker_task = task
    logger.info("ConversationWorker scheduled (poll_seconds=%.1f).", module.worker.poll_seconds)
    return task


async def stop_worker(timeout: float = 5.0) -> None:
    """Signal the worker to stop + await the task with a timeout.

    Per `ConversationWorker.stop()`, setting `should_stop=True` causes
    the next poll iteration to exit. The to_thread-wrapped coroutine
    then resolves and the asyncio task completes.
    """
    module = _module  # tolerate not-yet-configured (test fixtures)
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
    """Test helper — clears the module-level singleton.

    Called from test fixtures so a fresh `configure_conversation_module`
    can be wired per-test without state leaking across cases.
    """
    global _module
    _module = None


__all__ = [
    "ConversationModule",
    "build_system_prompt",
    "configure_conversation_module",
    "get_conversation_module",
    "start_worker",
    "stop_worker",
]
