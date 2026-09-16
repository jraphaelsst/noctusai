"""`InMemoryPointsLedger` + `make_points_ledger` factory. The idempotent-
insert contract mirrors `payments.event_inbox`'s own test discipline: a
duplicate `(member_id, idempotency_key)` must be a proven no-op."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.engagement import (
    InMemoryPointsLedger,
    PointAward,
    PointsLedger,
    make_points_ledger,
)


def _award(
    *, member_id: str = "m1", points: int = 10, idempotency_key: str = "k1"
) -> PointAward:
    return PointAward(
        member_id=member_id,
        source="platform",
        action="post",
        points=points,
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key=idempotency_key,
    )


@pytest.fixture
def ledger() -> InMemoryPointsLedger:
    return InMemoryPointsLedger()


def test_satisfies_protocol(ledger: InMemoryPointsLedger) -> None:
    assert isinstance(ledger, PointsLedger)


def test_first_record_is_accepted(ledger: InMemoryPointsLedger) -> None:
    assert ledger.record(_award()) is True


def test_duplicate_record_is_a_proven_no_op(ledger: InMemoryPointsLedger) -> None:
    first = ledger.record(_award(idempotency_key="dup"))
    second = ledger.record(_award(idempotency_key="dup"))
    assert first is True
    assert second is False
    # not double-counted
    assert ledger.totals()["m1"] == 10


def test_duplicate_record_does_not_raise(ledger: InMemoryPointsLedger) -> None:
    ledger.record(_award(idempotency_key="dup2"))
    try:
        result = ledger.record(_award(idempotency_key="dup2"))
    except Exception as exc:  # noqa: BLE001 - explicitly proving no raise
        pytest.fail(f"duplicate record raised {exc!r} instead of returning False")
    assert result is False


def test_same_idempotency_key_different_member_is_not_a_duplicate(
    ledger: InMemoryPointsLedger,
) -> None:
    assert ledger.record(_award(member_id="m1", idempotency_key="shared")) is True
    assert ledger.record(_award(member_id="m2", idempotency_key="shared")) is True


def test_history_filters_by_member_source_action(ledger: InMemoryPointsLedger) -> None:
    ledger.record(_award(member_id="m1", idempotency_key="k1"))
    ledger.record(
        PointAward(
            member_id="m1",
            source="whatsapp",
            action="reply",
            points=5,
            occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            idempotency_key="k2",
        )
    )
    result = ledger.history("m1", source="platform", action="post")
    assert len(result) == 1
    assert result[0].idempotency_key == "k1"


def test_totals_sums_points_per_member(ledger: InMemoryPointsLedger) -> None:
    ledger.record(_award(member_id="m1", points=10, idempotency_key="k1"))
    ledger.record(_award(member_id="m1", points=5, idempotency_key="k2"))
    ledger.record(_award(member_id="m2", points=7, idempotency_key="k3"))
    assert ledger.totals() == {"m1": 15, "m2": 7}


def test_totals_can_be_scoped_to_a_member_subset(ledger: InMemoryPointsLedger) -> None:
    ledger.record(_award(member_id="m1", points=10, idempotency_key="k1"))
    ledger.record(_award(member_id="m2", points=7, idempotency_key="k2"))
    assert ledger.totals(member_ids=["m1"]) == {"m1": 10}


def test_clear_resets_state(ledger: InMemoryPointsLedger) -> None:
    ledger.record(_award())
    ledger.clear()
    assert ledger.totals() == {}
    assert ledger.record(_award()) is True  # not treated as a duplicate anymore


# --- factory ---------------------------------------------------------------


def test_factory_returns_fake_when_use_fake_true() -> None:
    ledger = make_points_ledger(use_fake=True)
    assert isinstance(ledger, InMemoryPointsLedger)


def test_factory_raises_without_client_when_not_fake() -> None:
    with pytest.raises(RuntimeError):
        make_points_ledger(use_fake=False)


def test_factory_raises_without_schema_or_table_when_not_fake() -> None:
    with pytest.raises(RuntimeError):
        make_points_ledger(use_fake=False, supabase_client=object())
    with pytest.raises(RuntimeError):
        make_points_ledger(
            use_fake=False, supabase_client=object(), schema_name="community"
        )
    with pytest.raises(RuntimeError):
        make_points_ledger(
            use_fake=False, supabase_client=object(), table_name="engagement_points"
        )
