"""``ClaudeAgentSdkRuntime.run_turn`` — contract §E.11 per-conversation
isolation wired end to end: the loud slot refusal, the handoff files
written before spawn, the transcript-usability (resume) decision, and the
mirror-error/finalize hooks.

Drives a full turn with a STUBBED ``Transport`` (never a monkeypatch of
our own runtime module or the SDK — same convention
``test_resume_after_restart.py`` already uses) so the real
``ClaudeSDKClient``/``Query`` machinery does the parsing; only the wire
bytes are faked.
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest

from app.runtime.academia_api import FakeAcademiaApi
from app.runtime.broker import StoreApprovalBroker
from app.runtime.claude_runtime import (
    RESUME_LOST_CONTEXT_TEXT,
    RESUME_TRUNCATED_TEXT,
    ClaudeAgentSdkRuntime,
    _HANDOFF_APPEND_FILENAME,
    _write_handoff_file,
    _write_turn_handoff,
)
from app.runtime.slots import FakeSlotPool
from app.runtime.types import AgentSpec, TurnContext
from app.stores.approvals import FakeApprovalStore
from app.stores.transcripts import FakeTranscriptStore

# Applied per-class (below) rather than module-wide — `TestHandoffFiles`
# exercises `_write_turn_handoff` directly and has no async tests.
_asyncio_mark = pytest.mark.asyncio


def _spec(**overrides) -> AgentSpec:
    defaults = dict(
        key="julia",
        model="claude-sonnet-5",
        effort="medium",
        prompt_append="PERSONA-TEXT-JULIA.md",
        skills=(),
        tools=(),
        max_turns=40,
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


def _ctx(**overrides) -> TurnContext:
    defaults = dict(
        org_id=uuid4(),
        conversation_id=uuid4(),
        requested_by=uuid4(),
        instance_id="inst-1",
        sdk_session_id=None,
    )
    defaults.update(overrides)
    return TurnContext(**defaults)


def _slot(tmp_path):
    """A real, leased :class:`~app.runtime.slots.TurnSlot`, redirected at
    ``tmp_path`` and this test process's OWN gid so
    ``os.chown``/``os.chmod`` succeed without root (the real deploy's
    ``gid == 2000+K``; only the numeric VALUE differs here, never the
    mechanism)."""
    slot = FakeSlotPool(1).try_reserve()
    assert slot is not None
    slot.handoff_dir = str(tmp_path / "handoff")
    slot.config_dir = str(tmp_path / "config")
    slot.uid = os.getgid()
    return slot


def _broker() -> StoreApprovalBroker:
    return StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=5, instance_id="inst-1")


class _CountingTranscriptStore(FakeTranscriptStore):
    """A real :class:`FakeTranscriptStore` (never a monkeypatch — a proper
    test double via subclassing) that additionally records every
    ``delete_session`` call, so a test can assert exactly which session
    was targeted (or that none was)."""

    def __init__(self) -> None:
        super().__init__()
        self.delete_calls: list[tuple] = []

    def delete_session(self, org_id, conversation_id, sdk_session_id) -> int:
        self.delete_calls.append((org_id, conversation_id, sdk_session_id))
        return super().delete_session(org_id, conversation_id, sdk_session_id)


class _DeleteAlwaysFailsStore(FakeTranscriptStore):
    """A real :class:`FakeTranscriptStore` whose ``delete_session`` always
    raises — scripts "the abandoned-session cleanup's delete call fails"
    without touching any production code."""

    def delete_session(self, org_id, conversation_id, sdk_session_id) -> int:
        raise RuntimeError("boom-delete")


def _runtime(*, transport_factory, transcripts=None, slot_pool=None) -> ClaudeAgentSdkRuntime:
    return ClaudeAgentSdkRuntime(
        academia_api=FakeAcademiaApi(),
        agent_id=uuid4(),
        approval_secret="s3cr3t",
        plugin_path="/app/agents/julia/plugin",
        approvals=FakeApprovalStore(),
        slot_pool=slot_pool or FakeSlotPool(1),
        transcripts=transcripts if transcripts is not None else FakeTranscriptStore(),
        transport_factory=transport_factory,
    )


class _ScriptedTransport:
    """Answers the SDK's ``initialize`` control request, then feeds a
    fixed script of raw wire message dicts — enough to drive a full
    ``run_turn()`` turn (assistant text plus a terminal ``result``, and
    optionally a synthesized ``mirror_error`` system message in between)
    without a real CLI subprocess. Never exercises tool-use/approval (no
    scripted message ever carries a ``tool_use`` block) — that path is
    ``FakeAgentRuntime``'s escrita drive, a G2 concern, not this one."""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = list(script)
        import asyncio

        self._queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue()

    async def connect(self) -> None:
        return None

    async def write(self, data: str) -> None:
        message = json.loads(data)
        if message.get("type") == "control_request" and message.get(
            "request", {}
        ).get("subtype") == "initialize":
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
            for item in self._script:
                await self._queue.put(item)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield await self._queue.get()

    async def close(self) -> None:
        return None

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        return None


def _assistant(text: str, *, session_id: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "session_id": session_id,
        "parent_tool_use_id": None,
        "message": {
            "model": "claude-sonnet-5",
            "id": "msg-1",
            "content": [{"type": "text", "text": text}],
        },
    }


def _result(*, session_id: str) -> dict[str, Any]:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 5,
        "duration_api_ms": 3,
        "num_turns": 1,
        "session_id": session_id,
    }


def _mirror_error(*, error: str = "boom") -> dict[str, Any]:
    return {"type": "system", "subtype": "mirror_error", "key": None, "error": error}


async def _drain(agen) -> list[dict[str, Any]]:
    return [event async for event in agen]


class TestSlotRequiredForRealRuntime:
    pytestmark = _asyncio_mark

    async def test_slot_none_refuses_loudly_without_spawning(self, tmp_path):
        spawned: list[Any] = []

        def factory():
            spawned.append(True)
            return _ScriptedTransport([])

        runtime = _runtime(transport_factory=factory)
        agen = runtime.run_turn(_spec(), _ctx(), "oi", _broker(), slot=None)

        with pytest.raises(RuntimeError):
            await agen.__anext__()
        assert spawned == []


class TestHandoffFiles:
    def test_append_md_carries_the_persona_text_mode_0640_and_slot_group(self, tmp_path):
        slot = _slot(tmp_path)
        _write_turn_handoff(
            slot,
            persona_text="PERSONA-TEXT",
            handoff_entries=None,
            resume_session_id=None,
        )
        append_path = os.path.join(slot.handoff_dir, _HANDOFF_APPEND_FILENAME)
        assert open(append_path, encoding="utf-8").read() == "PERSONA-TEXT"
        st = os.stat(append_path)
        assert (st.st_mode & 0o777) == 0o640
        assert st.st_gid == slot.uid

    def test_transcript_jsonl_is_one_entry_per_line_in_seq_order(self, tmp_path):
        slot = _slot(tmp_path)
        entries = [{"type": "assistant", "uuid": "u1"}, {"type": "assistant", "uuid": "u2"}]
        _write_turn_handoff(
            slot,
            persona_text="p",
            handoff_entries=entries,
            resume_session_id="sess-abc",
        )
        transcript_path = os.path.join(slot.handoff_dir, "sess-abc.jsonl")
        lines = open(transcript_path, encoding="utf-8").read().splitlines()
        assert [json.loads(line) for line in lines] == entries
        st = os.stat(transcript_path)
        assert (st.st_mode & 0o777) == 0o640
        assert st.st_gid == slot.uid

    def test_existing_append_md_refuses_the_turn(self, tmp_path):
        slot = _slot(tmp_path)
        os.makedirs(slot.handoff_dir, exist_ok=True)
        _write_handoff_file(
            os.path.join(slot.handoff_dir, _HANDOFF_APPEND_FILENAME),
            b"stale-leftover",
            gid=slot.uid,
        )
        with pytest.raises(RuntimeError):
            _write_turn_handoff(
                slot, persona_text="p", handoff_entries=None, resume_session_id=None
            )


class TestFreshTurnHappyPath:
    pytestmark = _asyncio_mark

    async def test_fresh_turn_writes_append_md_and_finalizes_cleanly(self, tmp_path):
        transcripts = FakeTranscriptStore()
        ctx = _ctx()
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [_assistant("oi", session_id="fresh-1"), _result(session_id="fresh-1")]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(
            runtime.run_turn(_spec(prompt_append="PERSONA-X"), ctx, "oi", _broker(), slot=slot)
        )

        append_path = os.path.join(slot.handoff_dir, _HANDOFF_APPEND_FILENAME)
        assert open(append_path, encoding="utf-8").read() == "PERSONA-X"

        assert events[-1] == {
            "event": "session.status",
            "payload": {
                "status": "ociosa",
                "sdk_session_id": "fresh-1",
                "custo_usd": None,
                "tokens_entrada": None,
                "tokens_saida": None,
                "tokens_cache_leitura": None,
            },
        }
        # No resume was attempted — no resume_fallback event on this path.
        assert not any(e["event"] == "session.resume_fallback" for e in events)
        # NOTE: a fresh mirror only pins `pinned_session_id` from a real
        # `append()` call (the SDK's own local-disk-to-mirror batcher,
        # watching the CLI subprocess's actual transcript writes) — this
        # fake `Transport` has no real subprocess for that batcher to
        # observe, so `finalize()` legitimately sees an unpinned mirror
        # here and marks `invalido`. Asserting `estado == "ok"` on a
        # FRESH turn would misrepresent what this harness can prove; the
        # resume-path tests below exercise `finalize` against a mirror
        # that IS pinned (from construction, per `_resolve_resume`),
        # which is where that guarantee is actually testable.


class TestUsableResume:
    pytestmark = _asyncio_mark

    async def test_usable_transcript_is_handed_off_and_resumed(self, tmp_path):
        transcripts = FakeTranscriptStore()
        ctx = _ctx(sdk_session_id="old-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")
        transcripts.append_entries(
            ctx.org_id,
            ctx.conversation_id,
            "old-sess",
            [{"type": "assistant", "uuid": "u1"}, {"type": "assistant", "uuid": "u2"}],
        )
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [_assistant("oi", session_id="old-sess"), _result(session_id="old-sess")]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        transcript_path = os.path.join(slot.handoff_dir, "old-sess.jsonl")
        lines = open(transcript_path, encoding="utf-8").read().splitlines()
        assert [json.loads(line)["uuid"] for line in lines] == ["u1", "u2"]

        assert not any(e["event"] == "session.resume_fallback" for e in events)
        assert events[-1]["payload"]["sdk_session_id"] == "old-sess"
        assert transcripts.get_estado(ctx.org_id, ctx.conversation_id) == "ok"

    async def test_finalize_marks_invalido_on_a_session_id_mismatch(self, tmp_path):
        transcripts = FakeTranscriptStore()
        ctx = _ctx(sdk_session_id="old-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")
        transcripts.append_entries(
            ctx.org_id, ctx.conversation_id, "old-sess", [{"type": "assistant", "uuid": "u1"}]
        )
        slot = _slot(tmp_path)

        def factory():
            # The CLI's own result reports a DIFFERENT session id than the
            # one this turn was told to resume — contract §E.11: "the
            # pinned id must equal ResultMessage.session_id; otherwise
            # the transcript is marked invalido".
            return _ScriptedTransport(
                [_assistant("oi", session_id="old-sess"), _result(session_id="surprise-sess")]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        assert transcripts.get_estado(ctx.org_id, ctx.conversation_id) == "invalido"


class TestResumeFallback:
    pytestmark = _asyncio_mark

    async def test_truncado_starts_fresh_with_its_own_text(self, tmp_path):
        transcripts = FakeTranscriptStore()
        ctx = _ctx(sdk_session_id="capped-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "truncado")
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [_assistant("oi", session_id="fresh-2"), _result(session_id="fresh-2")]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        assert events[0] == {
            "event": "session.resume_fallback",
            "payload": {"texto": RESUME_TRUNCATED_TEXT},
        }
        # No stale handoff transcript file for the abandoned session.
        assert not os.path.exists(os.path.join(slot.handoff_dir, "capped-sess.jsonl"))

    async def test_invalido_starts_fresh_with_the_generic_text(self, tmp_path):
        transcripts = FakeTranscriptStore()
        ctx = _ctx(sdk_session_id="bad-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "invalido")
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [_assistant("oi", session_id="fresh-3"), _result(session_id="fresh-3")]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        assert events[0] == {
            "event": "session.resume_fallback",
            "payload": {"texto": RESUME_LOST_CONTEXT_TEXT},
        }

    async def test_missing_transcript_despite_ok_estado_starts_fresh(self, tmp_path):
        """`estado == "ok"` but nothing was ever stored under this session
        id — distinct from truncado/invalido, gets the generic text."""
        transcripts = FakeTranscriptStore()
        ctx = _ctx(sdk_session_id="never-stored-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [_assistant("oi", session_id="fresh-4"), _result(session_id="fresh-4")]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        assert events[0] == {
            "event": "session.resume_fallback",
            "payload": {"texto": RESUME_LOST_CONTEXT_TEXT},
        }


class TestMirrorError:
    pytestmark = _asyncio_mark

    async def test_a_mirror_error_message_marks_the_transcript_incompleto(self, tmp_path):
        # A RESUMED turn: the mirror is pinned from construction (per
        # `_resolve_resume`), so `finalize()` sees a clean match and never
        # clobbers the `incompleto` finding with `invalido` — isolating
        # exactly the behaviour under test. See the note in
        # `TestFreshTurnHappyPath` for why a fresh (unpinned) mirror is
        # not a fair vehicle for this assertion under a fake `Transport`.
        transcripts = FakeTranscriptStore()
        ctx = _ctx(sdk_session_id="sess-me")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")
        transcripts.append_entries(
            ctx.org_id, ctx.conversation_id, "sess-me", [{"type": "assistant", "uuid": "u1"}]
        )
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [
                    _assistant("oi", session_id="sess-me"),
                    _mirror_error(),
                    _result(session_id="sess-me"),
                ]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        assert transcripts.get_estado(ctx.org_id, ctx.conversation_id) == "incompleto"
        # The mirror_error frame itself never becomes a published AgentEvent.
        assert all(e["event"] != "mirror_error" for e in events)


class TestAbandonedSessionCleanup:
    """Contract §E.11 / ``LGPD-WARNINGS.md`` (2026-09-15): an abandoned
    (``truncado``/``incompleto``/``invalido``) session's rows are deleted
    and its conversation's ``transcript_estado`` reset to ``"ok"`` before
    the fresh session starts — never for a merely MISSING transcript
    (nothing to delete), never for a brand-new conversation, and never in
    a way that can kill the turn.

    The deletion/reset assertions call ``_resolve_resume`` directly
    (sync, no transport involved) rather than draining a full
    ``run_turn()``: a full turn's OWN ``finalize()`` unconditionally
    marks a never-pinned mirror ``invalido`` at turn end under this fake
    ``Transport`` (nothing here drives the SDK's real local-disk-to-
    mirror batching that would otherwise pin it) — a HARNESS artifact,
    not a claim about this cleanup, that would otherwise clobber the
    very ``"ok"`` reset under test. See the note in
    ``TestFreshTurnHappyPath`` for the same caveat."""

    @pytest.mark.parametrize("estado", ["truncado", "incompleto", "invalido"])
    def test_abandoned_estado_deletes_exactly_that_session_and_resets_estado(
        self, estado
    ):
        transcripts = _CountingTranscriptStore()
        ctx = _ctx(sdk_session_id="old-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, estado)
        transcripts.append_entries(
            ctx.org_id, ctx.conversation_id, "old-sess", [{"type": "assistant", "uuid": "u1"}]
        )

        # A second, unrelated conversation (same org) — must stay untouched.
        other_conv_id = uuid4()
        transcripts.register_conversation(ctx.org_id, other_conv_id, "ok")
        transcripts.append_entries(
            ctx.org_id, other_conv_id, "other-sess", [{"type": "assistant", "uuid": "z1"}]
        )

        runtime = _runtime(transport_factory=lambda: _ScriptedTransport([]), transcripts=transcripts)
        mirror, entries, fallback_text = runtime._resolve_resume(ctx)

        assert entries is None
        assert fallback_text is not None
        assert transcripts.delete_calls == [(ctx.org_id, ctx.conversation_id, "old-sess")]
        assert transcripts.load(ctx.org_id, ctx.conversation_id, "old-sess") is None
        assert transcripts.get_estado(ctx.org_id, ctx.conversation_id) == "ok"

        # The unrelated conversation's own session and estado are intact.
        assert transcripts.load(ctx.org_id, other_conv_id, "other-sess") == [
            {"type": "assistant", "uuid": "z1"}
        ]
        assert transcripts.get_estado(ctx.org_id, other_conv_id) == "ok"

    def test_a_missing_transcript_deletes_nothing(self):
        transcripts = _CountingTranscriptStore()
        ctx = _ctx(sdk_session_id="never-stored-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")

        runtime = _runtime(transport_factory=lambda: _ScriptedTransport([]), transcripts=transcripts)
        _mirror, entries, fallback_text = runtime._resolve_resume(ctx)

        assert entries is None
        assert fallback_text == RESUME_LOST_CONTEXT_TEXT
        assert transcripts.delete_calls == []
        # estado was already "ok" — untouched, not reset (nothing to reset).
        assert transcripts.get_estado(ctx.org_id, ctx.conversation_id) == "ok"

    def test_a_fresh_conversation_never_attempts_a_delete(self):
        transcripts = _CountingTranscriptStore()
        ctx = _ctx(sdk_session_id=None)
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")

        runtime = _runtime(transport_factory=lambda: _ScriptedTransport([]), transcripts=transcripts)
        _mirror, entries, fallback_text = runtime._resolve_resume(ctx)

        assert entries is None
        assert fallback_text is None
        assert transcripts.delete_calls == []

    def test_a_usable_transcript_never_attempts_a_delete(self):
        """The happy path — a usable resume must never touch delete or
        estado at all."""
        transcripts = _CountingTranscriptStore()
        ctx = _ctx(sdk_session_id="good-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "ok")
        transcripts.append_entries(
            ctx.org_id, ctx.conversation_id, "good-sess", [{"type": "assistant", "uuid": "u1"}]
        )

        runtime = _runtime(transport_factory=lambda: _ScriptedTransport([]), transcripts=transcripts)
        _mirror, entries, fallback_text = runtime._resolve_resume(ctx)

        assert entries == [{"type": "assistant", "uuid": "u1"}]
        assert fallback_text is None
        assert transcripts.delete_calls == []
        assert transcripts.get_estado(ctx.org_id, ctx.conversation_id) == "ok"

class TestFullTurnSurvivesADeleteFailure:
    pytestmark = _asyncio_mark

    async def test_a_delete_failure_still_yields_a_working_fresh_turn(self, tmp_path):
        transcripts = _DeleteAlwaysFailsStore()
        ctx = _ctx(sdk_session_id="capped-sess")
        transcripts.register_conversation(ctx.org_id, ctx.conversation_id, "truncado")
        slot = _slot(tmp_path)

        def factory():
            return _ScriptedTransport(
                [
                    _assistant("oi", session_id="fresh-despite-failure"),
                    _result(session_id="fresh-despite-failure"),
                ]
            )

        runtime = _runtime(transport_factory=factory, transcripts=transcripts)
        events = await _drain(runtime.run_turn(_spec(), ctx, "oi", _broker(), slot=slot))

        # The delete raised RuntimeError (logged, never a silent pass —
        # see `_abandon_old_session`), yet the turn still completed: the
        # fallback event fired and the fresh session's result landed.
        assert events[0] == {
            "event": "session.resume_fallback",
            "payload": {"texto": RESUME_TRUNCATED_TEXT},
        }
        assert events[-1] == {
            "event": "session.status",
            "payload": {
                "status": "ociosa",
                "sdk_session_id": "fresh-despite-failure",
                "custo_usd": None,
                "tokens_entrada": None,
                "tokens_saida": None,
                "tokens_cache_leitura": None,
            },
        }
