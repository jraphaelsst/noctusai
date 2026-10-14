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
    S.EXPIRED: {S.PAID, S.CANCELLED, S.PENDING_PAYMENT},
    S.FAILED: {S.PENDING_PAYMENT},
    S.PAID: {S.REFUNDED, S.CHARGEBACK, S.PARTIALLY_REFUNDED, S.DISPUTED},
    S.PARTIALLY_REFUNDED: {S.PARTIALLY_REFUNDED, S.REFUNDED, S.CHARGEBACK, S.DISPUTED},
    S.DISPUTED: {S.PAID, S.PARTIALLY_REFUNDED, S.CHARGEBACK},
    S.CANCELLED: set(),
    S.REFUNDED: set(),
    S.CHARGEBACK: set(),
}

#: CONTRACT §2.2 -- the P4 additions, one target per (state, event), written out independently.
P4_EDGES = {
    (S.EXPIRED, E.RETRY): S.PENDING_PAYMENT,
    (S.PAID, E.PARTIAL_REFUND): S.PARTIALLY_REFUNDED,
    (S.PARTIALLY_REFUNDED, E.PARTIAL_REFUND): S.PARTIALLY_REFUNDED,
    (S.PARTIALLY_REFUNDED, E.REFUND): S.REFUNDED,
    (S.PAID, E.DISPUTE_OPENED): S.DISPUTED,
    (S.PARTIALLY_REFUNDED, E.DISPUTE_OPENED): S.DISPUTED,
    (S.DISPUTED, E.DISPUTE_WON): S.PAID,
    (S.DISPUTED, E.DISPUTE_WON_PARTIAL): S.PARTIALLY_REFUNDED,
    (S.DISPUTED, E.DISPUTE_LOST): S.CHARGEBACK,
    (S.PARTIALLY_REFUNDED, E.CHARGEBACK): S.CHARGEBACK,
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


@pytest.mark.parametrize("edge,target", list(P4_EDGES.items()))
def test_p4_edges_are_in_the_table_with_one_target(edge, target):
    assert TRANSITIONS[edge] is target


def test_the_p3_paid_to_chargeback_edge_stays():
    assert transition(S.PAID, E.CHARGEBACK) is S.CHARGEBACK
    assert transition(S.PAID, E.REFUND) is S.REFUNDED


def test_a_dispute_cannot_be_refunded_or_charged_back_directly():
    for event in (E.REFUND, E.PARTIAL_REFUND, E.CHARGEBACK, E.PAYMENT_CONFIRMED):
        with pytest.raises(InvalidTransition):
            transition(S.DISPUTED, event)
