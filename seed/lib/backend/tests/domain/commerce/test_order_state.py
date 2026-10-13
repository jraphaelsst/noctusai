"""The order state machine: the contract's transition table, exhaustively."""
from __future__ import annotations

import itertools

import pytest

from noctusai_lib.domain.commerce import InvalidTransition, OrderEvent, OrderStatus, transition
from noctusai_lib.domain.commerce.order_state import TERMINAL_STATES, TRANSITIONS, is_terminal, legal_events, legal_next_states

S, E = OrderStatus, OrderEvent

#: CONTRACT §1, written out independently of the implementation's table.
CONTRACT = {
    S.CREATED: {S.PENDING_PAYMENT, S.FAILED, S.CANCELLED},
    S.PENDING_PAYMENT: {S.PAID, S.EXPIRED, S.FAILED, S.CANCELLED},
    S.EXPIRED: {S.PAID, S.CANCELLED},
    S.FAILED: {S.PENDING_PAYMENT},
    S.PAID: {S.REFUNDED, S.CHARGEBACK},
    S.CANCELLED: set(),
    S.REFUNDED: set(),
    S.CHARGEBACK: set(),
}


def test_every_status_is_covered_by_the_contract_table():
    assert set(CONTRACT) == set(OrderStatus)


@pytest.mark.parametrize("status", list(OrderStatus))
def test_reachable_states_equal_the_contract(status):
    assert set(legal_next_states(status)) == CONTRACT[status]


@pytest.mark.parametrize("status,event", list(itertools.product(OrderStatus, OrderEvent)))
def test_exhaustive_status_by_event(status, event):
    if (status, event) in TRANSITIONS:
        new = transition(status, event)
        assert new in CONTRACT[status]
    else:
        with pytest.raises(InvalidTransition) as exc:
            transition(status, event)
        assert exc.value.current is status and exc.value.event is event


def test_terminal_states_are_exactly_cancelled_refunded_chargeback():
    assert TERMINAL_STATES == {S.CANCELLED, S.REFUNDED, S.CHARGEBACK}
    for s in OrderStatus:
        assert is_terminal(s) == (s in TERMINAL_STATES)
        if is_terminal(s):
            assert legal_events(s) == ()


def test_late_payment_recovers_an_expired_order():
    assert transition(S.EXPIRED, E.PAYMENT_CONFIRMED) is S.PAID


def test_failed_order_can_only_retry_not_pay_directly():
    assert transition(S.FAILED, E.RETRY) is S.PENDING_PAYMENT
    with pytest.raises(InvalidTransition):
        transition(S.FAILED, E.PAYMENT_CONFIRMED)


def test_accepts_wire_strings_and_rejects_unknown_ones():
    assert transition("pending_payment", "payment_confirmed") is S.PAID
    with pytest.raises(ValueError):
        transition("nonsense", "payment_confirmed")


def test_a_repeated_event_is_an_error_not_a_silent_noop():
    with pytest.raises(InvalidTransition):
        transition(S.PAID, E.PAYMENT_CONFIRMED)
