"""Contract §E.9 "Resume after a restart" — pins the SDK finding against
the INSTALLED ``claude-agent-sdk`` (0.2.152): an unknown ``resume`` id
surfaces as a terminal ``result`` frame (``is_error: true``) followed by
the CLI exiting non-zero, which ``claude_agent_sdk``'s own background
reader (``_internal/query.py::Query._read_messages``) turns into a
``ResultError`` (a ``ProcessError`` subclass) delivered to the
still-in-flight ``initialize`` control request — so it is
``ClaudeSDKClient.connect()`` itself that raises. See
``app/runtime/claude_runtime.py::ClaudeAgentSdkRuntime._connect_or_fresh``'s
docstring for the file:line evidence.

Pinned here with a STUBBED ``Transport`` (the SDK's own public extension
point, ``claude_agent_sdk.Transport`` — never a monkeypatch of our own
runtime module or of the SDK). Tests ``_connect_or_fresh`` directly
(rather than the full ``run_turn``) — it is the one unit that owns the
fallback decision; driving a whole scripted SDK message stream to a
complete turn is G2's ``FakeAgentRuntime``'s job, not this one.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from claude_agent_sdk import ProcessError

from app.runtime.academia_api import FakeAcademiaApi
from app.runtime.claude_runtime import ClaudeAgentSdkRuntime, build_launch_options
from app.runtime.slots import FakeSlotPool
from app.runtime.transcript_mirror import ConversationTranscriptMirror
from app.runtime.types import AgentSpec, TurnContext
from app.stores.approvals import FakeApprovalStore
from app.stores.transcripts import FakeTranscriptStore

pytestmark = pytest.mark.asyncio


class _ResumeRejectedTransport:
    """Reproduces exactly what query.py's own comment names as the
    trigger for its ProcessError -> ResultError replacement: "an
    `initialize` still in flight when the CLI reports an error result
    during startup (e.g. a refused resume)". Verified against
    ``claude_agent_sdk/_internal/query.py`` lines ~360-368 (the `result`
    frame with `is_error=True` sets `_last_error_result`) and ~405-428
    (the subsequent `ProcessError` — from this transport's `read_messages`
    raising below, mirroring a real CLI's non-zero exit — is replaced by
    a `ResultError` and delivered to every pending control response,
    including the in-flight `initialize`)."""

    async def connect(self) -> None:
        return None

    async def write(self, data: str) -> None:
        return None

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        yield {
            "type": "result",
            "subtype": "error_during_execution",
            "is_error": True,
            "duration_ms": 5,
            "duration_api_ms": 0,
            "num_turns": 0,
            "session_id": "unknown-session",
            "errors": ["No conversation found with session ID: unknown-session"],
        }
        # Mirrors SubprocessCLITransport._read_messages_impl: after the
        # stdout stream ends, a non-zero exit code becomes a ProcessError.
        raise ProcessError("Command failed with exit code 1", exit_code=1)

    async def close(self) -> None:
        return None

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        return None


class _InitializeOnlySuccessTransport:
    """Answers exactly the ONE control request ``client.connect()`` sends
    (``initialize``) with a success response, then emits nothing else.
    Sufficient for ``_connect_or_fresh``'s fresh-session ``connect()`` to
    return normally — it never awaits any turn content."""

    def __init__(self) -> None:
        import asyncio

        self._queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue()

    async def connect(self) -> None:
        return None

    async def write(self, data: str) -> None:
        message = json.loads(data)
        if message.get("type") == "control_request" and message.get("request", {}).get(
            "subtype"
        ) == "initialize":
            await self._queue.put(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": message["request_id"],
                        "response": {},
                    },
                }
            )
        # Any other write (e.g. the initial prompt) is accepted silently —
        # `_connect_or_fresh` never awaits beyond `connect()` returning.

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield await self._queue.get()

    async def close(self) -> None:
        return None

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        return None


def _spec() -> AgentSpec:
    return AgentSpec(
        key="julia",
        model="claude-sonnet-5",
        effort="medium",
        prompt_append="be helpful",
        skills=(),
        tools=(),
        max_turns=40,
    )


def _ctx(*, sdk_session_id: str | None) -> TurnContext:
    return TurnContext(
        org_id=uuid4(),
        conversation_id=uuid4(),
        requested_by=uuid4(),
        instance_id="inst-1",
        sdk_session_id=sdk_session_id,
    )


def _slot():
    slot = FakeSlotPool(1).try_reserve()
    assert slot is not None
    return slot


def _runtime(*, transport_factory) -> ClaudeAgentSdkRuntime:
    return ClaudeAgentSdkRuntime(
        academia_api=FakeAcademiaApi(),
        agent_id=uuid4(),
        approval_secret="s3cr3t",
        plugin_path="/app/agents/julia/plugin",
        approvals=FakeApprovalStore(),
        slot_pool=FakeSlotPool(1),
        transcripts=FakeTranscriptStore(),
        transport_factory=transport_factory,
    )


class TestResumeAfterRestart:
    async def test_refused_resume_falls_back_to_a_fresh_session(self):
        transports = [_ResumeRejectedTransport(), _InitializeOnlySuccessTransport()]

        def factory():
            return transports.pop(0)

        runtime = _runtime(transport_factory=factory)
        ctx = _ctx(sdk_session_id="a-session-lost-to-a-restart")
        slot = _slot()
        # `_resolve_resume` decided this transcript IS usable (this test
        # is exercising the SDK-level refusal, a layer BELOW that
        # decision) — so `resume` mirrors `ctx.sdk_session_id` verbatim,
        # same as the real `run_turn` would build it in that case.
        mirror = ConversationTranscriptMirror(
            runtime._transcripts, ctx.org_id, ctx.conversation_id, ctx.sdk_session_id
        )
        options = build_launch_options(
            spec=_spec(),
            ctx=ctx,
            academia_api=runtime._academia_api,
            agent_id=runtime._agent_id,
            approval_secret=runtime._approval_secret,
            can_use_tool=lambda *a, **k: None,
            approvals=runtime._approvals,
            slot=slot,
            mirror=mirror,
            resume=ctx.sdk_session_id,
            plugin_path=runtime._plugin_path,
        )
        assert options.resume == "a-session-lost-to-a-restart"

        client, used_fresh, active_mirror = await runtime._connect_or_fresh(
            options, "oi", ctx, mirror
        )
        try:
            assert used_fresh is True
            # The fallback swaps in a fresh, unpinned mirror — the old one
            # (pinned to the now-abandoned session id) would only drop
            # every frame of the CLI's brand-new session.
            assert active_mirror is not mirror
            assert active_mirror.pinned_session_id is None
        finally:
            await client.disconnect()

    async def test_non_resume_connect_failure_propagates(self):
        """A genuine startup failure when NO resume was attempted
        (``options.resume is None``) must propagate — the fallback is
        scoped to resume failures only, never a blanket retry."""
        transports = [_ResumeRejectedTransport()]

        def factory():
            return transports.pop(0)

        runtime = _runtime(transport_factory=factory)
        ctx = _ctx(sdk_session_id=None)
        slot = _slot()
        mirror = ConversationTranscriptMirror(
            runtime._transcripts, ctx.org_id, ctx.conversation_id, None
        )
        options = build_launch_options(
            spec=_spec(),
            ctx=ctx,
            academia_api=runtime._academia_api,
            agent_id=runtime._agent_id,
            approval_secret=runtime._approval_secret,
            can_use_tool=lambda *a, **k: None,
            approvals=runtime._approvals,
            slot=slot,
            mirror=mirror,
            resume=None,
            plugin_path=runtime._plugin_path,
        )
        assert options.resume is None

        with pytest.raises(ProcessError):
            await runtime._connect_or_fresh(options, "oi", ctx, mirror)
