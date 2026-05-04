"""Conversation worker — drains the seed `ConversationBufferService` due
queue, dispatches to OpenAI via the seed `LLMDispatcher`, sends replies
through the seed `WhatsAppClient`.

Pure assembly — no business logic lives here. Every primitive is from
`noctusai_lib`:

  - `ConversationBufferService` (Redis buffer + debounce + idle queue)
  - `ConversationWorker`        (poll-loop shell)
  - `LLMDispatcher`             (OpenAI tool-loop)
  - `make_audit_writer`         (per-call audit)
  - `get_whatsapp_client`       (WAHA outbound or in-memory fake)
  - `make_redis_client` / `make_fake_redis_client`

**Engineer-D handoff (Phase 4)**: tools land via
`app.services.scheduling_tools.register_scheduling_tools(dispatcher)`. We
import that lazily — graceful degradation when D's worktree merges later.
Without it the dispatcher runs with zero tools (LLM replies in plain text
referencing what it CAN'T do; useful for end-to-end smoke before tools
ship).

Run as a lifespan startup task on the FastAPI app (see
`app.main.worker_lifecycle`) — runs in a background asyncio.to_thread
so the seed `worker.run_forever()` blocking poll-loop doesn't freeze
the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from noctusai_lib.domain.chatbot import (
    ConversationBufferService,
    ConversationWorker,
    LLMDispatcher,
    QueuedConversationMessage,
    ToolCall,
    ToolHandler,
    ToolResult,
    memory_to_chat_messages,
)
from noctusai_lib.domain.ai.tool_audit import AuditRecord, now_utc
from noctusai_lib.integrations.redis import (
    make_fake_redis_client,
    make_redis_client,
)
from noctusai_lib.integrations.whatsapp import (
    chat_id_for_phone,
    get_whatsapp_client,
)

from app.config import settings
from app.services.audit_hook import get_audit_writer

logger = logging.getLogger(__name__)


# Short placeholder system prompt. Real prompt lands when Phase 4's tool
# handlers register; we keep this terse so unconfigured-dev replies are
# obviously stubs. See `KB § PATTERNS/whatsapp-chatbot-seed.md` for the
# full pt-BR prompt the source repo uses.
PLACEHOLDER_SYSTEM_PROMPT = (
    "Você é um assistente de agendamento da NoctusAI para produção de "
    "conteúdo imobiliário. Conversa em pt-BR no tom de WhatsApp: "
    "natural, breve, objetivo. Use as ferramentas disponíveis para "
    "consultar imóveis, propor horários e confirmar agendamentos. "
    "Se faltar informação, faça uma pergunta direta e curta."
)


_worker_thread: Optional[threading.Thread] = None
_worker_instance: Optional[ConversationWorker] = None


# --- Default tool handler (no-op until Phase 4 registers real tools) ----


def _default_tool_handler(call: ToolCall) -> ToolResult:
    """Catch-all when no tools are registered or dispatcher hits an unknown name.

    Returns a structured "not implemented" result so the LLM can recover
    gracefully (model usually pivots to a clarification question)."""
    logger.info("worker: tool '%s' invoked but no handler registered", call.name)
    return ToolResult(
        call_id=call.call_id,
        content='{"error": "tool_not_implemented", "tool": "' + call.name + '"}',
    )


# --- LLMDispatcher tool registry shape -----------------------------------
#
# Phase 4 (Engineer D) ships `register_scheduling_tools(dispatcher)` which
# attaches tools_payload + handler closures. We expose those as attrs on
# the dispatcher instance so the registration call has a place to mutate.

class _ToolRegistry:
    """Mutable registry the worker passes to the dispatcher."""

    def __init__(self):
        self.tools_payload: list[dict[str, Any]] = self._default_tools_payload()
        self.handler: ToolHandler = _default_tool_handler

    @staticmethod
    def _default_tools_payload() -> list[dict[str, Any]]:
        """2-3 lightweight tool descriptions so the dispatcher exercises the
        tool-call path even before Engineer D's registrations land. The
        handler returns `tool_not_implemented` for each — see above."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "lookup_property",
                    "description": "Verify a property code exists. Returns "
                    "condominium info on hit. CALL BEFORE discussing any "
                    "code with the user.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Property code, e.g. 'AB123'"},
                        },
                        "required": ["code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_appointment",
                    "description": "Return candidate time-slots for a "
                    "property + date. NEVER invent slots — always call this.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "property_code": {"type": "string"},
                            "requested_date": {"type": "string", "description": "ISO YYYY-MM-DD"},
                            "time_window": {"type": "string", "description": "morning/afternoon/specific"},
                        },
                        "required": ["property_code", "requested_date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "confirm_appointment",
                    "description": "Persist the chosen slot to Google Calendar "
                    "and notify the crew. Only call after the user explicitly "
                    "confirms ALL details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "property_code": {"type": "string"},
                            "start_at": {"type": "string", "description": "ISO datetime"},
                            "end_at": {"type": "string", "description": "ISO datetime"},
                            "services": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "photos/videos/reels/virtual_tour",
                            },
                            "notes": {"type": "string"},
                        },
                        "required": ["property_code", "start_at", "end_at"],
                    },
                },
            },
        ]


# --- Processor builder ---------------------------------------------------


def _build_processor(
    dispatcher: LLMDispatcher,
    buffer_service: ConversationBufferService,
    whatsapp_client,
    tool_registry: _ToolRegistry,
):
    """Wire one closure that the seed worker calls per due-conversation tick."""

    audit_writer = get_audit_writer()

    def _audit_adapter(call: ToolCall, result: ToolResult) -> None:
        """Bridge the seed dispatcher's `(ToolCall, ToolResult)` shape into
        an `AuditRecord` the seed audit writer accepts. Best-effort —
        dispatcher already wraps this in try/except."""
        try:
            arguments = call.arguments if isinstance(call.arguments, dict) else None
            audit_writer(
                AuditRecord(
                    tool_name=call.name,
                    status="success",  # We don't know failure here without parsing — Phase 4 may refine.
                    duration_ms=0,
                    started_at=now_utc(),
                    arguments=arguments,
                    result=result.content,
                    gpt_call_id=call.call_id,
                    tool_call_id=call.call_id,
                )
            )
        except Exception:
            logger.exception("worker: audit-adapter failed for tool=%s", call.name)

    def processor(conversation_id: str, memory: list[dict[str, Any]]) -> None:
        # Resolve chat_id from the most-recent inbound's metadata; fall
        # back to phone-derived chat_id (`chat_id_for_phone`) for legacy
        # @c.us cases.
        chat_id = _resolve_chat_id_from_memory(memory, conversation_id)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PLACEHOLDER_SYSTEM_PROMPT},
            *memory_to_chat_messages(memory),
        ]

        try:
            reply = dispatcher.reply(
                messages=messages,
                tools=tool_registry.tools_payload,
                tool_handler=tool_registry.handler,
                audit_writer=_audit_adapter,
            )
        except Exception:
            logger.exception(
                "worker: LLM dispatch failed for conversation %s", conversation_id
            )
            return

        if not reply:
            logger.info(
                "worker: empty reply for conversation %s — skipping send",
                conversation_id,
            )
            return

        try:
            whatsapp_client.send_text_sync(chat_id, reply)
        except AttributeError:
            # FakeWahaClient may expose only `send_text` (async) — fall back.
            try:
                send = getattr(whatsapp_client, "send_text", None)
                if send is None:
                    raise
                # The fake's send_text is sync-friendly per its docstring.
                result = send(chat_id, reply)
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
            except Exception:
                logger.exception(
                    "worker: WAHA send failed for conversation %s", conversation_id
                )
                return
        except Exception:
            logger.exception(
                "worker: WAHA send failed for conversation %s", conversation_id
            )
            return

        # Append the bot reply back into memory so subsequent turns have
        # the assistant message in context. Doesn't trigger debounce.
        buffer_service.append_to_memory(
            QueuedConversationMessage(
                conversation_id=conversation_id,
                text=reply,
                direction="outbound",
            )
        )

    return processor


def _resolve_chat_id_from_memory(memory: list[dict[str, Any]], conversation_id: str) -> str:
    """Reach for the most-recent inbound's `metadata.chat_id`; fall back to
    deriving from phone for legacy @c.us-only chats."""
    for item in reversed(memory):
        meta = item.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("chat_id"):
            return str(meta["chat_id"])
    return chat_id_for_phone(conversation_id)


# --- Lifespan entry point -------------------------------------------------


def build_worker() -> Optional[ConversationWorker]:
    """Construct and return a worker, or None when the env can't support one.

    Currently unconditional — even with no Redis we use the in-memory fake
    so the worker can poll a buffer (cross-process inbounds will not be
    visible, but the LLM dispatcher is exercised). When the OpenAI key is
    missing the dispatcher will raise on first call; we let the worker
    surface that via the per-conversation try/except in the processor."""
    if settings.redis_url:
        redis_client = make_redis_client(settings.redis_url)
    else:
        logger.warning(
            "worker: REDIS_URL unset — using in-memory fake redis "
            "(worker will not see webhook-buffered messages cross-process)"
        )
        redis_client = make_fake_redis_client()

    buffer_service = ConversationBufferService(
        redis_client,
        memory_ttl_seconds=settings.conversation_memory_ttl_seconds,
        debounce_seconds=settings.message_debounce_seconds,
        idle_timeout_seconds=settings.conversation_idle_timeout_seconds,
        stream_maxlen=settings.redis_stream_maxlen,
    )

    whatsapp_client = get_whatsapp_client(
        base_url=settings.waha_base_url or None,
        api_key=settings.waha_api_key or None,
        session=settings.waha_session,
    )

    # OpenAI client — sync. The seed dispatcher calls
    # `client.chat.completions.create(...)` directly, so we need the
    # canonical openai SDK shape. Lazy import keeps the dependency
    # optional in environments that don't ship `openai`.
    try:
        from openai import OpenAI

        openai_client = OpenAI()
    except Exception:
        logger.exception(
            "worker: failed to construct OpenAI client; LLM dispatch will fail per conversation"
        )
        # Build a sentinel that raises on use rather than silently no-oping.
        class _BrokenOpenAI:
            def __getattr__(self, name):
                raise RuntimeError(
                    "OpenAI client unavailable — install `openai` and set OPENAI_API_KEY"
                )

        openai_client = _BrokenOpenAI()

    dispatcher = LLMDispatcher(
        client=openai_client,
        model=settings.openai_chat_model,
    )

    tool_registry = _ToolRegistry()

    # Phase 4 handoff — Engineer D's tool registration. Graceful degrade.
    try:
        from app.services.scheduling_tools import register_scheduling_tools

        # Two valid shapes for D's signature:
        #   register_scheduling_tools(dispatcher)
        #   register_scheduling_tools(dispatcher, tool_registry=...)
        # We pass dispatcher; if D needs the registry, add a sentinel.
        register_scheduling_tools(dispatcher)  # type: ignore[arg-type]
        logger.info("worker: scheduling_tools registered")
    except ImportError:
        logger.warning(
            "worker: scheduling_tools module not yet available; "
            "starting with placeholder tool descriptions and no-op handler"
        )
    except Exception:
        logger.exception(
            "worker: scheduling_tools.register_scheduling_tools raised; "
            "continuing with placeholder tools"
        )

    processor = _build_processor(
        dispatcher, buffer_service, whatsapp_client, tool_registry
    )

    return ConversationWorker(
        buffer_service=buffer_service,
        processor=processor,
        idle_processor=None,  # idle-summary belongs to a future phase
        poll_seconds=settings.worker_poll_seconds,
        due_batch_size=settings.worker_due_batch_size,
    )


def worker_lifecycle() -> None:
    """FastAPI `lifespan_startup` hook — kicks off the worker thread.

    The seed worker uses a blocking `time.sleep`-based poll loop; we run
    it on a daemon thread so FastAPI's event loop stays responsive. The
    thread's lifecycle is the process's — when the server stops, the
    daemon goes with it (we don't need to join on shutdown).

    Re-entrant: subsequent calls (e.g. uvicorn `--reload`) leave the
    existing thread alone if it's still alive."""
    global _worker_thread, _worker_instance

    if _worker_thread is not None and _worker_thread.is_alive():
        logger.info("worker_lifecycle: worker thread already running; skipping start")
        return

    worker = build_worker()
    if worker is None:
        logger.warning("worker_lifecycle: build_worker returned None — not starting")
        return

    _worker_instance = worker

    def _run():
        try:
            worker.run_forever()
        except Exception:
            logger.exception("worker_lifecycle: worker thread crashed")

    thread = threading.Thread(target=_run, name="conversation-worker", daemon=True)
    thread.start()
    _worker_thread = thread
    logger.info(
        "worker_lifecycle: conversation worker thread started "
        "(poll_seconds=%s, due_batch_size=%s)",
        settings.worker_poll_seconds,
        settings.worker_due_batch_size,
    )
