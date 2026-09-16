"""EventInbox — a duplicate `(gateway, event_id)` webhook delivery MUST
be a proven no-op. This is the single most common billing bug per the
brief, so it gets its own explicit, unambiguous test.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.payments.event_inbox import (
    EventInbox,
    FakeEventInbox,
    RealSupabaseEventInbox,
    make_event_inbox,
)


@pytest.fixture
def inbox() -> FakeEventInbox:
    return FakeEventInbox()


def test_satisfies_protocol(inbox: FakeEventInbox) -> None:
    assert isinstance(inbox, EventInbox)


def test_first_delivery_is_claimed(inbox: FakeEventInbox) -> None:
    assert inbox.claim(gateway="stripe", event_id="evt_1") is True


def test_duplicate_delivery_is_a_proven_no_op(inbox: FakeEventInbox) -> None:
    """THE test: gateways retry, and a second delivery of the SAME event
    must be detected as a duplicate, not processed twice."""
    first = inbox.claim(gateway="stripe", event_id="evt_1")
    second = inbox.claim(gateway="stripe", event_id="evt_1")
    third = inbox.claim(gateway="stripe", event_id="evt_1")

    assert first is True
    assert second is False
    assert third is False
    # The duplicate call must not raise — a duplicate is an ordinary,
    # expected outcome, never an error condition.
    assert inbox.claims.count(("stripe", "evt_1")) == 3


def test_duplicate_delivery_does_not_raise(inbox: FakeEventInbox) -> None:
    inbox.claim(gateway="stripe", event_id="evt_dup")
    try:
        result = inbox.claim(gateway="stripe", event_id="evt_dup")
    except Exception as exc:  # noqa: BLE001 - explicitly proving no raise
        pytest.fail(f"duplicate claim raised {exc!r} instead of returning False")
    assert result is False


def test_same_event_id_different_gateway_is_not_a_duplicate(inbox: FakeEventInbox) -> None:
    """`(gateway, event_id)` is the composite key — two vendors could
    plausibly mint overlapping ids and must not collide."""
    assert inbox.claim(gateway="stripe", event_id="evt_1") is True
    assert inbox.claim(gateway="asaas", event_id="evt_1") is True


def test_clear_resets_state(inbox: FakeEventInbox) -> None:
    inbox.claim(gateway="stripe", event_id="evt_1")
    inbox.clear()
    assert inbox.claim(gateway="stripe", event_id="evt_1") is True


class TestFactory:
    def test_use_fake_returns_fake(self) -> None:
        assert isinstance(make_event_inbox(use_fake=True), FakeEventInbox)

    def test_missing_client_without_fake_raises(self) -> None:
        with pytest.raises(RuntimeError):
            make_event_inbox(use_fake=False)

    def test_real_supabase_variant_constructible(self) -> None:
        inbox = make_event_inbox(use_fake=False, supabase_client=object())
        assert isinstance(inbox, RealSupabaseEventInbox)


class _FakeAPIError(Exception):
    """Stand-in for `postgrest.exceptions.APIError` — same `.code` shape,
    no dependency on the real postgrest package for this unit test."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _DuplicateKeyTableBuilder:
    """Minimal Supabase-query-builder double: `insert(...).execute()`
    raises a unique-violation on every call, simulating a real second
    delivery hitting the DB's `(gateway, event_id)` primary key."""

    def insert(self, payload: dict) -> "_DuplicateKeyTableBuilder":
        return self

    def execute(self) -> None:
        raise _FakeAPIError("23505")


class _DuplicateKeyClient:
    def table(self, name: str) -> _DuplicateKeyTableBuilder:
        return _DuplicateKeyTableBuilder()


class _SucceedingTableBuilder:
    def __init__(self, calls: list[dict]) -> None:
        self._calls = calls

    def insert(self, payload: dict) -> "_SucceedingTableBuilder":
        self._calls.append(payload)
        return self

    def execute(self) -> dict:
        return {"data": [dict(self._calls[-1])]}


class _SucceedingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def table(self, name: str) -> _SucceedingTableBuilder:
        return _SucceedingTableBuilder(self.calls)


class TestRealSupabaseEventInboxShape:
    """`RealSupabaseEventInbox` is shape-only (no live Postgres in this
    suite — see the module docstring), but the duplicate-vs-first-seen
    branch is pure Python and IS exercised here with a scripted client
    double, matching `RealSupabaseJobRepository`'s own test discipline.
    """

    def test_first_insert_succeeds(self) -> None:
        client = _SucceedingClient()
        inbox = RealSupabaseEventInbox(client)
        assert inbox.claim(gateway="stripe", event_id="evt_1") is True
        assert client.calls[0]["gateway"] == "stripe"
        assert client.calls[0]["event_id"] == "evt_1"

    def test_unique_violation_is_treated_as_duplicate_not_error(self) -> None:
        inbox = RealSupabaseEventInbox(_DuplicateKeyClient())
        assert inbox.claim(gateway="stripe", event_id="evt_1") is False

    def test_non_unique_violation_reraises(self) -> None:
        class _BrokenTableBuilder:
            def insert(self, payload: dict) -> "_BrokenTableBuilder":
                return self

            def execute(self) -> None:
                raise _FakeAPIError("23503")  # foreign-key violation, NOT duplicate

        class _BrokenClient:
            def table(self, name: str) -> _BrokenTableBuilder:
                return _BrokenTableBuilder()

        inbox = RealSupabaseEventInbox(_BrokenClient())
        with pytest.raises(_FakeAPIError):
            inbox.claim(gateway="stripe", event_id="evt_1")


def test_release_makes_the_next_delivery_claimable_again() -> None:
    inbox = FakeEventInbox()
    assert inbox.claim(gateway="stripe", event_id="evt_9") is True
    inbox.release(gateway="stripe", event_id="evt_9")
    assert inbox.claim(gateway="stripe", event_id="evt_9") is True
    assert inbox.releases == [("stripe", "evt_9")]


def test_release_of_an_unclaimed_pair_is_a_no_op() -> None:
    inbox = FakeEventInbox()
    inbox.release(gateway="asaas", event_id="never")
    assert inbox.claim(gateway="asaas", event_id="never") is True


def test_real_release_deletes_the_claim_row() -> None:
    from noctusai_lib.testing import MockSupabaseClient

    client = MockSupabaseClient(validate_schema=False)
    client.set_table_data(
        "payment_gateway_events",
        [{"gateway": "stripe", "event_id": "evt_1"}, {"gateway": "stripe", "event_id": "evt_2"}],
    )
    inbox = RealSupabaseEventInbox(client)
    inbox.release(gateway="stripe", event_id="evt_1")
    remaining = client.table("payment_gateway_events").select("*").execute().data
    assert [r["event_id"] for r in remaining] == ["evt_2"]
