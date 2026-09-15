"""Tests for ``app.stores.transcripts`` (contract §E.11 "Durable
transcripts", slice B2).

``FakeTranscriptStore`` covers idempotency, seq ordering and estado
transitions. ``SupabaseTranscriptStore.delete_session`` is covered against
``MockSupabaseClient`` — same style as
``tests/stores/test_approvals_store.py::TestSupabaseApprovalStoreConsumeQueryShape``
— because that method's guarantee (only THIS session's rows are removed) is
a query-SHAPE guarantee, not something the Fake's dict-keyed storage can
get wrong by construction.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.stores.errors import NotFound
from app.stores.transcripts import (
    TRANSCRIPT_ESTADOS,
    FakeTranscriptStore,
    SupabaseTranscriptStore,
)


def _entry(uuid_value: str | None, extra: str = "x") -> dict:
    entry: dict = {"type": "assistant", "extra": extra}
    if uuid_value is not None:
        entry["uuid"] = uuid_value
    return entry


class TestIdempotentAppend:
    def test_reappending_the_same_entry_uuid_adds_zero_bytes(self):
        store = FakeTranscriptStore()
        org_id, conv_id, sid = uuid4(), uuid4(), "sess-1"
        entries = [_entry("uuid-a"), _entry("uuid-b")]

        first = store.append_entries(org_id, conv_id, sid, entries)
        second = store.append_entries(org_id, conv_id, sid, entries)

        assert first > 0
        assert second == 0
        # No duplicate rows landed either — total_bytes reflects only the
        # first call's writes.
        assert store.total_bytes(org_id, conv_id, sid) == first

    def test_a_partially_overlapping_batch_only_adds_the_new_entries(self):
        store = FakeTranscriptStore()
        org_id, conv_id, sid = uuid4(), uuid4(), "sess-1"
        store.append_entries(org_id, conv_id, sid, [_entry("uuid-a")])

        added = store.append_entries(
            org_id, conv_id, sid, [_entry("uuid-a"), _entry("uuid-c")]
        )

        assert added == len(json.dumps(_entry("uuid-c")).encode("utf-8"))
        loaded = store.load(org_id, conv_id, sid)
        assert loaded is not None
        assert len(loaded) == 2

    def test_entries_without_an_sdk_uuid_are_never_deduped(self):
        """Contract: SDK entries with no ``uuid`` (titles, tags, mode
        markers) 'should be appended without dedup' — appending the SAME
        uuid-less entry twice must land as TWO rows, never collapse."""
        store = FakeTranscriptStore()
        org_id, conv_id, sid = uuid4(), uuid4(), "sess-1"
        entry = _entry(None)

        store.append_entries(org_id, conv_id, sid, [entry])
        store.append_entries(org_id, conv_id, sid, [entry])

        loaded = store.load(org_id, conv_id, sid)
        assert loaded is not None
        assert len(loaded) == 2


class TestSeqOrderIsPreserved:
    def test_load_returns_entries_in_append_order(self):
        store = FakeTranscriptStore()
        org_id, conv_id, sid = uuid4(), uuid4(), "sess-1"
        store.append_entries(org_id, conv_id, sid, [_entry("u1", "first")])
        store.append_entries(org_id, conv_id, sid, [_entry("u2", "second")])
        store.append_entries(org_id, conv_id, sid, [_entry("u3", "third")])

        loaded = store.load(org_id, conv_id, sid)

        assert loaded == [
            {"type": "assistant", "extra": "first", "uuid": "u1"},
            {"type": "assistant", "extra": "second", "uuid": "u2"},
            {"type": "assistant", "extra": "third", "uuid": "u3"},
        ]

    def test_seq_keeps_incrementing_across_calls_never_resets(self):
        store = FakeTranscriptStore()
        org_id, conv_id, sid = uuid4(), uuid4(), "sess-1"
        store.append_entries(org_id, conv_id, sid, [_entry("u1"), _entry("u2")])
        store.append_entries(org_id, conv_id, sid, [_entry("u3")])

        rows = store._sessions[(org_id, conv_id, sid)]
        assert [r["seq"] for r in rows] == [1, 2, 3]


class TestOrgScoping:
    def test_total_bytes_never_crosses_org_boundaries(self):
        store = FakeTranscriptStore()
        conv_id, sid = uuid4(), "sess-1"
        org_a, org_b = uuid4(), uuid4()
        store.append_entries(org_a, conv_id, sid, [_entry("u1")])

        assert store.total_bytes(org_a, conv_id, sid) > 0
        assert store.total_bytes(org_b, conv_id, sid) == 0

    def test_load_never_crosses_org_boundaries(self):
        store = FakeTranscriptStore()
        conv_id, sid = uuid4(), "sess-1"
        org_a, org_b = uuid4(), uuid4()
        store.append_entries(org_a, conv_id, sid, [_entry("u1")])

        assert store.load(org_b, conv_id, sid) is None

    def test_get_estado_raises_not_found_for_another_org(self):
        store = FakeTranscriptStore()
        conv_id = uuid4()
        org_a, org_b = uuid4(), uuid4()
        store.register_conversation(org_a, conv_id)

        with pytest.raises(NotFound):
            store.get_estado(org_b, conv_id)


class TestEstadoTransitions:
    def test_a_registered_conversation_defaults_to_ok(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id)

        assert store.get_estado(org_id, conv_id) == "ok"

    @pytest.mark.parametrize("estado", TRANSCRIPT_ESTADOS)
    def test_every_contract_estado_round_trips(self, estado):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id)

        store.set_estado(org_id, conv_id, estado)

        assert store.get_estado(org_id, conv_id) == estado

    def test_an_unknown_estado_value_is_rejected(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.register_conversation(org_id, conv_id)

        with pytest.raises(ValueError):
            store.set_estado(org_id, conv_id, "bogus")

    def test_get_estado_raises_not_found_for_an_unregistered_conversation(self):
        store = FakeTranscriptStore()
        with pytest.raises(NotFound):
            store.get_estado(uuid4(), uuid4())

    def test_set_estado_raises_not_found_for_an_unregistered_conversation(self):
        store = FakeTranscriptStore()
        with pytest.raises(NotFound):
            store.set_estado(uuid4(), uuid4(), "truncado")


class TestDeleteSession:
    def test_delete_session_removes_the_whole_session_and_nothing_else(self):
        store = FakeTranscriptStore()
        org_id, conv_id = uuid4(), uuid4()
        store.append_entries(org_id, conv_id, "sess-old", [_entry("u1"), _entry("u2")])
        store.append_entries(org_id, conv_id, "sess-new", [_entry("u3")])

        removed = store.delete_session(org_id, conv_id, "sess-old")

        assert removed == 2
        assert store.load(org_id, conv_id, "sess-old") is None
        assert store.load(org_id, conv_id, "sess-new") is not None

    def test_deleting_an_unknown_session_removes_nothing_and_never_raises(self):
        store = FakeTranscriptStore()
        assert store.delete_session(uuid4(), uuid4(), "never-existed") == 0


def _supabase_row(*, org_id, conversation_id, sdk_session_id, entry_uuid, seq=1) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "conversation_id": str(conversation_id),
        "sdk_session_id": sdk_session_id,
        "seq": seq,
        "entry": {"type": "assistant", "uuid": entry_uuid},
        "entry_uuid": entry_uuid,
        "byte_size": 42,
        "created_at": "2026-09-15T12:00:00+00:00",
    }


class TestSupabaseTranscriptStoreDeleteSessionQueryShape:
    """§E.11: 'a fresh session replaces a truncated one' — the old session's
    rows must be fully removed, and ONLY that session's rows, proven
    against the real ``.eq(...)`` predicate chain via ``MockSupabaseClient``
    (mirrors ``TestSupabaseApprovalStoreConsumeQueryShape``: a single call,
    inspected via its own return value — ``MockSupabaseClient.schema(...)``
    rebinds to a fresh isolated copy on every call, so a SEPARATE follow-up
    query against the same client can never observe this call's mutation;
    that isolation is exactly why ``delete_session`` returns the removed
    count instead of ``None``)."""

    def test_delete_session_removes_only_the_matching_rows(self):
        org_id, other_org = uuid4(), uuid4()
        conv_id, other_conv = uuid4(), uuid4()
        rows = [
            _supabase_row(
                org_id=org_id,
                conversation_id=conv_id,
                sdk_session_id="sess-old",
                entry_uuid="u1",
            ),
            # Same conversation, DIFFERENT session — must survive.
            _supabase_row(
                org_id=org_id,
                conversation_id=conv_id,
                sdk_session_id="sess-new",
                entry_uuid="u2",
            ),
            # Same session id, DIFFERENT conversation — must survive.
            _supabase_row(
                org_id=org_id,
                conversation_id=other_conv,
                sdk_session_id="sess-old",
                entry_uuid="u3",
            ),
            # Same everything else, DIFFERENT org — must survive.
            _supabase_row(
                org_id=other_org,
                conversation_id=conv_id,
                sdk_session_id="sess-old",
                entry_uuid="u4",
            ),
        ]
        client = MockSupabaseClient(rows, validate_schema=False)
        store = SupabaseTranscriptStore(client)

        removed = store.delete_session(org_id, conv_id, "sess-old")

        assert removed == 1

    def test_deleting_a_session_with_no_rows_removes_nothing(self):
        client = MockSupabaseClient([], validate_schema=False)
        store = SupabaseTranscriptStore(client)

        assert store.delete_session(uuid4(), uuid4(), "never-existed") == 0
