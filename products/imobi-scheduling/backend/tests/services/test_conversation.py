"""Tests for `app.services.conversation` — the Phase 6 wiring module.

Verifies the wiring without hitting a real LLM:
  - `build_system_prompt()` reads the pt-BR prompt file + strips the
    markdown header.
  - `configure_conversation_module(...)` instantiates buffer / dispatcher
    / worker / audit_writer and caches the module-level singleton.
  - `start_worker()` schedules the worker via `schedule_coro`.
  - The processor closure composes messages + invokes the dispatcher
    with our tool registry + the audit writer.

Per the rule "No monkey-patching of our own code in tests" — patches
are at the OpenAI SDK boundary (`app.services.conversation.OpenAI`) +
`schedule_coro` (a seed primitive treated as the external scheduler
boundary). Our dispatcher / buffer / worker code is exercised as-is.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from noctusai_lib.domain.chatbot import (
    ConversationBufferService,
    ConversationWorker,
    LLMDispatcher,
)


@pytest.fixture(autouse=True)
def reset_conversation_module():
    """Reset the singleton between tests."""
    from app.services import conversation

    conversation._reset_for_tests()
    yield
    conversation._reset_for_tests()


@pytest.fixture
def admin_client():
    """Mock Supabase admin client (schema().table() chain inspectable)."""
    return MagicMock(name="admin_client")


@pytest.fixture
def mock_openai_class():
    """A mock OpenAI class. The conversation module uses
    `client.chat.completions.create(...)` — surface only that."""
    cls = MagicMock(name="OpenAIClass")
    instance = MagicMock(name="OpenAIInstance")
    cls.return_value = instance
    # Default completion stub (single text reply, no tool calls).
    instance.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Olá!", tool_calls=None))]
    )
    return cls


class TestBuildSystemPrompt:
    """The pt-BR prompt loader."""

    def test_loads_prompt_body_strips_markdown_header(self):
        from app.services.conversation import build_system_prompt

        prompt = build_system_prompt()
        # Header lines (`#`, `>`) stripped — body starts at "Você é".
        assert prompt.startswith("Você é um assistente de agendamento")
        # Key sections present.
        assert "FERRAMENTAS DISPONÍVEIS" in prompt
        assert "lookup_property" in prompt
        assert "propose_appointment" in prompt
        assert "confirm_appointment" in prompt
        assert "REGRAS" in prompt
        # Header artifacts NOT present in the body.
        assert "Imobi Scheduling Bot — System Prompt" not in prompt
        assert "**Lifecycle.**" not in prompt


class TestConfigureConversationModule:
    """The wiring factory."""

    def test_builds_buffer_dispatcher_worker_and_audit(
        self, admin_client, mock_openai_class,
    ):
        from app.services import conversation as conv

        with patch.object(conv, "OpenAI", mock_openai_class):
            module = conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )

        assert isinstance(module.buffer, ConversationBufferService)
        assert isinstance(module.dispatcher, LLMDispatcher)
        assert isinstance(module.worker, ConversationWorker)
        assert callable(module.audit_writer)
        # Singleton is set.
        assert conv.get_conversation_module() is module

    def test_uses_settings_for_buffer_ttl_and_debounce(
        self, admin_client, mock_openai_class,
    ):
        from app.config import settings
        from app.services import conversation as conv

        with patch.object(conv, "OpenAI", mock_openai_class):
            module = conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )

        assert module.buffer.memory_ttl_seconds == settings.conversation_memory_ttl_seconds
        assert module.buffer.debounce_seconds == settings.message_debounce_seconds

    def test_uses_settings_for_openai_model(
        self, admin_client, mock_openai_class,
    ):
        from app.config import settings
        from app.services import conversation as conv

        with patch.object(conv, "OpenAI", mock_openai_class):
            module = conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )

        assert module.dispatcher.model == settings.openai_model

    def test_uses_in_memory_redis_when_url_unset(
        self, admin_client, mock_openai_class, monkeypatch,
    ):
        """No `REDIS_URL` configured → FakeRedis. Per
        `KB § PATTERNS/seed-fake-real-adapter.md`."""
        from app.config import settings
        from app.services import conversation as conv

        # Belt+suspenders — settings may already lack redis_url, but
        # explicitly null it to lock the test contract.
        monkeypatch.setattr(settings, "redis_url", "", raising=False)

        with patch.object(conv, "OpenAI", mock_openai_class):
            module = conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )

        # The fakeredis-backed client exposes the same Protocol surface.
        # Cheapest probe — zadd/zrange round-trips.
        module.buffer.redis.zadd("test", {"x": 1.0})
        assert module.buffer.redis.zrangebyscore("test", "-inf", 999.0) == ["x"]

    def test_get_module_raises_when_not_configured(self):
        from app.services import conversation as conv

        with pytest.raises(RuntimeError, match="not configured"):
            conv.get_conversation_module()


class TestProcessorClosure:
    """The per-conversation processor the worker invokes."""

    def test_processor_calls_dispatcher_with_system_prompt_and_tools(
        self, admin_client, mock_openai_class,
    ):
        from app.services import conversation as conv

        with patch.object(conv, "OpenAI", mock_openai_class):
            module = conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )

        # The dispatcher's `reply()` is the seam we observe. Drive the
        # processor with a memory shape matching `buffer.memory_for(...)`.
        memory = [
            {"text": "Oi, preciso agendar fotos pro AP-2034", "direction": "inbound"},
        ]
        # The worker normally invokes `module.worker.processor` — call
        # it directly here.
        module.worker.processor("conv-1", memory)

        # OpenAI client.chat.completions.create was called once
        # (mock_openai_class returned a single-text-reply default).
        mock_instance = mock_openai_class.return_value
        mock_instance.chat.completions.create.assert_called()
        call_kwargs = mock_instance.chat.completions.create.call_args.kwargs
        # System prompt + user message land in the messages list.
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "Você é um assistente de agendamento" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Oi, preciso agendar fotos pro AP-2034"
        # Tools threaded through.
        assert call_kwargs["tools"] is not None
        tool_names = {t["function"]["name"] for t in call_kwargs["tools"]}
        assert tool_names == {"lookup_property", "propose_appointment", "confirm_appointment"}

    def test_processor_tool_call_loop_audits_via_supabase(
        self, admin_client, mock_openai_class,
    ):
        """When OpenAI returns a tool call, the dispatcher dispatches
        the stub handler AND the Supabase audit writer is invoked."""
        from app.services import conversation as conv

        # Configure OpenAI mock to return one tool call then a text reply.
        tool_call = MagicMock()
        tool_call.id = "call_abc"
        tool_call.function.name = "lookup_property"
        tool_call.function.arguments = json.dumps({"code": "AP-2034"})

        first_response = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=None, tool_calls=[tool_call],
            ))]
        )
        second_response = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="O imóvel AP-2034 existe!", tool_calls=None,
            ))]
        )
        mock_openai_class.return_value.chat.completions.create.side_effect = [
            first_response, second_response,
        ]

        with patch.object(conv, "OpenAI", mock_openai_class):
            module = conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )

        module.worker.processor(
            "conv-2",
            [{"text": "AP-2034 existe?", "direction": "inbound"}],
        )

        # Two OpenAI completions invoked (one for tool call, one for
        # the final reply).
        assert mock_openai_class.return_value.chat.completions.create.call_count == 2

        # Audit row was inserted via Supabase admin client.
        admin_client.schema.assert_called_with("imobi_scheduling")
        table_handle = admin_client.schema.return_value.table.return_value
        table_handle.insert.assert_called_once()
        inserted = table_handle.insert.call_args[0][0]
        assert inserted["tool_name"] == "lookup_property"
        # Status is "success" (the stub returned `not_implemented` which
        # maps to success at the audit layer).
        assert inserted["status"] == "success"


class TestWorkerStartStop:
    """Worker lifecycle hooks — `start_worker` schedules via
    `schedule_coro`; `stop_worker` flips `should_stop` and awaits."""

    def test_start_worker_calls_schedule_coro_with_to_thread_wrapper(
        self, admin_client, mock_openai_class,
    ):
        from app.services import conversation as conv

        captured_coro = {}

        def _capture(coro, **_kwargs):
            captured_coro["repr"] = repr(coro)
            coro.close()
            return MagicMock(done=lambda: False)

        with patch.object(conv, "OpenAI", mock_openai_class), \
             patch.object(conv, "schedule_coro", side_effect=_capture) as mock_schedule:
            conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )
            task = conv.start_worker()

        mock_schedule.assert_called_once()
        kwargs = mock_schedule.call_args.kwargs
        assert kwargs["name"] == "imobi-scheduling-conversation-worker"
        # The first positional arg is a coroutine — confirm it's our
        # to_thread wrapper (named `_run_worker_in_thread`).
        assert "_run_worker_in_thread" in captured_coro["repr"]
        assert task is not None

    def test_start_worker_short_circuits_when_already_running(
        self, admin_client, mock_openai_class,
    ):
        """Idempotent re-start — second call returns the existing task."""
        from app.services import conversation as conv

        existing_task = MagicMock()
        existing_task.done.return_value = False

        def _schedule(coro, **_kwargs):
            coro.close()
            return existing_task

        with patch.object(conv, "OpenAI", mock_openai_class), \
             patch.object(conv, "schedule_coro", side_effect=_schedule) as mock_schedule:
            conv.configure_conversation_module(
                admin_client=admin_client, org_id=uuid4(),
            )
            t1 = conv.start_worker()
            t2 = conv.start_worker()

        assert t1 is t2
        # schedule_coro called only once.
        assert mock_schedule.call_count == 1

    def test_stop_worker_signals_should_stop(
        self, admin_client, mock_openai_class,
    ):
        """`stop_worker` sets `worker.should_stop = True` so the
        run_forever loop exits at the next poll iteration.

        We exercise the **flag-flip** semantics + the **already-completed-
        task** safe path. The real worker.run_forever() lives on the
        thread executor; what stop_worker contributes that matters is
        (a) `worker.stop()` (sets the flag) and (b) `wait_for` on the
        scheduled task. We satisfy both by hand-feeding a
        pre-completed Future as the "task" so the await is a no-op."""
        import asyncio

        from app.services import conversation as conv

        async def _drive():
            def _schedule(coro, **_kwargs):
                # Close the coroutine so Python doesn't emit a
                # "coroutine was never awaited" RuntimeWarning, then
                # return a pre-completed Future as the "task".
                coro.close()
                done: asyncio.Future = asyncio.Future()
                done.set_result(None)
                return done

            with patch.object(conv, "OpenAI", mock_openai_class), \
                 patch.object(conv, "schedule_coro", side_effect=_schedule):
                conv.configure_conversation_module(
                    admin_client=admin_client, org_id=uuid4(),
                )
                conv.start_worker()
                worker_ref = conv.get_conversation_module().worker

                await conv.stop_worker(timeout=0.5)

                return worker_ref

        worker = asyncio.run(_drive())
        assert worker.should_stop is True
