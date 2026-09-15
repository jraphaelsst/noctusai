"""Tests for ``app.runtime.transcript_mirror.ConversationTranscriptMirror``
(contract §E.11 "Durable transcripts", slice B2).

Uses ``FakeTranscriptStore`` throughout (no monkeypatching of our own
modules) plus the REAL, installed ``claude_agent_sdk`` for protocol
conformance — the SDK's own ``TranscriptMirrorBatcher`` and
``ClaudeAgentOptions`` construction path, driven directly without a CLI
subprocess (see ``TestSdkProtocolConformance``).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.transcript_mirror_batcher import (
    TranscriptMirrorBatcher,
)

from app.runtime.transcript_mirror import ConversationTranscriptMirror
from app.stores.transcripts import FakeTranscriptStore


def _entry(uuid_value: str = "u1") -> dict:
    return {"type": "assistant", "uuid": uuid_value, "message": {"text": "oi"}}


class TestFrameFiltering:
    @pytest.mark.asyncio
    async def test_a_subpath_frame_is_dropped_and_never_stored(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)

        await mirror.append(
            {"project_key": "-app", "session_id": "sess-1", "subpath": "subagents/agent-1"},
            [_entry()],
        )

        assert mirror.frames_dropped == 1
        assert mirror.pinned_session_id is None
        assert store.load(org_id, conv_id, "sess-1") is None

    @pytest.mark.asyncio
    async def test_a_frame_with_the_wrong_project_key_is_dropped(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)

        await mirror.append(
            {"project_key": "-some-other-cwd", "session_id": "sess-1"}, [_entry()]
        )

        assert mirror.frames_dropped == 1
        assert store.load(org_id, conv_id, "sess-1") is None

    @pytest.mark.asyncio
    async def test_a_frame_for_a_different_session_than_expected_is_dropped(self):
        """Resume case: `expected_session_id` is set at construction, so it
        is never pinned from a frame — a frame for any OTHER session id
        (e.g. from a stale/compromised subprocess writing under a
        different session) is dropped outright."""
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(
            store, org_id, conv_id, expected_session_id="sess-expected"
        )

        await mirror.append(
            {"project_key": "-app", "session_id": "sess-other"}, [_entry()]
        )

        assert mirror.frames_dropped == 1
        assert mirror.pinned_session_id == "sess-expected"
        assert store.load(org_id, conv_id, "sess-other") is None


class TestFreshSessionPinning:
    @pytest.mark.asyncio
    async def test_a_fresh_session_pins_the_first_session_id_seen(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)

        await mirror.append({"project_key": "-app", "session_id": "sess-1"}, [_entry("u1")])

        assert mirror.pinned_session_id == "sess-1"
        assert store.load(org_id, conv_id, "sess-1") == [_entry("u1")]

    @pytest.mark.asyncio
    async def test_frames_after_the_pin_for_a_different_session_are_dropped(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)
        await mirror.append({"project_key": "-app", "session_id": "sess-1"}, [_entry("u1")])

        await mirror.append({"project_key": "-app", "session_id": "sess-2"}, [_entry("u2")])

        assert mirror.frames_dropped == 1
        assert store.load(org_id, conv_id, "sess-2") is None


class TestFinalize:
    def test_a_matching_result_session_id_leaves_the_estado_unchanged(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "ok")
        mirror = ConversationTranscriptMirror(
            store, org_id, conv_id, expected_session_id="sess-1"
        )

        mirror.finalize("sess-1")

        assert store.get_estado(org_id, conv_id) == "ok"

    def test_a_mismatched_result_session_id_marks_invalido(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "ok")
        mirror = ConversationTranscriptMirror(
            store, org_id, conv_id, expected_session_id="sess-1"
        )

        mirror.finalize("sess-DIFFERENT")

        assert store.get_estado(org_id, conv_id) == "invalido"


class TestMirrorError:
    def test_on_mirror_error_marks_incompleto(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "ok")
        mirror = ConversationTranscriptMirror(
            store, org_id, conv_id, expected_session_id="sess-1"
        )

        mirror.on_mirror_error()

        assert store.get_estado(org_id, conv_id) == "incompleto"


class TestTranscriptCap:
    @pytest.mark.asyncio
    async def test_crossing_the_cap_marks_truncado_and_stops_further_writes(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "ok")
        # A tiny cap so one entry crosses it.
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None, cap_bytes=10)

        await mirror.append({"project_key": "-app", "session_id": "sess-1"}, [_entry("u1")])

        assert store.get_estado(org_id, conv_id) == "truncado"
        bytes_after_first = store.total_bytes(org_id, conv_id, "sess-1")

        # A second batch must add nothing further — "no further writes".
        await mirror.append({"project_key": "-app", "session_id": "sess-1"}, [_entry("u2")])

        assert store.total_bytes(org_id, conv_id, "sess-1") == bytes_after_first
        loaded = store.load(org_id, conv_id, "sess-1")
        assert loaded is not None
        assert len(loaded) == 1


class TestLoadReturnsNoneOnPurpose:
    @pytest.mark.asyncio
    async def test_load_always_returns_none_even_when_entries_exist(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)
        await mirror.append({"project_key": "-app", "session_id": "sess-1"}, [_entry("u1")])

        result = await mirror.load({"project_key": "-app", "session_id": "sess-1"})

        assert result is None


class TestLoadForHandoff:
    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_has_been_pinned_yet(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "ok")
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)

        assert mirror.load_for_handoff() is None

    def test_returns_none_when_the_estado_is_not_ok(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "truncado")
        store.append_entries(org_id, conv_id, "sess-1", [_entry("u1")])
        mirror = ConversationTranscriptMirror(
            store, org_id, conv_id, expected_session_id="sess-1"
        )

        assert mirror.load_for_handoff() is None

    def test_returns_the_stored_entries_when_the_estado_is_ok(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id, "ok")
        store.append_entries(org_id, conv_id, "sess-1", [_entry("u1")])
        mirror = ConversationTranscriptMirror(
            store, org_id, conv_id, expected_session_id="sess-1"
        )

        assert mirror.load_for_handoff() == [_entry("u1")]


class TestSdkProtocolConformance:
    def test_constructing_claude_agent_options_with_the_mirror_never_raises(self):
        store = FakeTranscriptStore()
        mirror = ConversationTranscriptMirror(store, uuid4(), uuid4(), None)

        options = ClaudeAgentOptions(session_store=mirror, session_store_flush="batched")

        assert options.session_store is mirror

    @pytest.mark.asyncio
    async def test_a_real_sdk_mirror_frame_flows_through_the_batcher(self):
        """Drives the REAL, installed SDK's ``TranscriptMirrorBatcher`` —
        the exact component the SDK's read loop hands ``transcript_mirror``
        stdout frames to (``_internal/query.py:348-355``) — directly,
        without a CLI subprocess. Proves this mirror's ``append`` really
        satisfies the SDK's calling convention end-to-end: SDK-side file
        path -> ``file_path_to_session_key`` -> ``SessionKey`` -> our
        filtering/pinning/store-write.
        """
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        mirror = ConversationTranscriptMirror(store, org_id, conv_id, None)
        errors: list[tuple] = []

        async def _on_error(key, message):
            errors.append((key, message))

        projects_dir = "/run/julia-0/home/.claude/projects"
        batcher = TranscriptMirrorBatcher(
            store=mirror, projects_dir=projects_dir, on_error=_on_error
        )
        file_path = f"{projects_dir}/-app/sess-real.jsonl"

        batcher.enqueue(file_path, [_entry("u1")])
        await batcher.flush()

        assert errors == []
        assert mirror.pinned_session_id == "sess-real"
        assert store.load(org_id, conv_id, "sess-real") == [_entry("u1")]
