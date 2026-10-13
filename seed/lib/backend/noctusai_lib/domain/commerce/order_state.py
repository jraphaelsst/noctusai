"""The order state machine — pure, total, explicit (CONTRACT §1).

`transition(current, event)` returns the new `OrderStatus` or raises
`InvalidTransition`. It never mutates and never touches IO; the service layer
(`orders.apply_transition`) persists the result AND appends the
`commerce_order_events` row, so a transition can never exist without its event.

An illegal move raises — never a silent no-op — because a state machine that
quietly ignores an illegal move lies about what happened (same posture as
`domain.payments.subscription`). Idempotency for repeated gateway deliveries is
the webhook layer's job (`EventInbox` + `webhook.handle_event`), not this one's.

Transitions (the whole table):

    created          -> pending_payment | failed | cancelled
    pending_payment  -> paid | expired | failed | cancelled
    expired          -> paid (late payment = recovery) | cancelled
    failed           -> pending_payment (retry)
    paid             -> refunded | chargeback
    terminal: cancelled, refunded, chargeback
"""
from __future__ import annotations

from enum import Enum

from .types import OrderStatus


class OrderEvent(str, Enum):
    """What happened to an order. Each event has exactly one legal source-set."""

    CHARGE_CREATED = "charge_created"        # gateway accepted the charge
    CHARGE_FAILED = "charge_failed"          # gateway refused / errored
    PAYMENT_CONFIRMED = "payment_confirmed"  # money arrived
    EXPIRED = "expired"                      # charge overdue / past expires_at
    CANCEL = "cancel"                        # buyer or staff gave up
    RETRY = "retry"                          # a failed order gets a new charge
    REFUND = "refund"
    CHARGEBACK = "chargeback"


class InvalidTransition(Exception):
    """`event` is not legal from `current`."""

    def __init__(self, current: OrderStatus, event: OrderEvent) -> None:
        self.current = current
        self.event = event
        super().__init__(f"order cannot apply {event.value!r} while {current.value!r}")


S = OrderStatus
E = OrderEvent

#: `(current, event) -> new`. The single source of truth; `legal_events`,
#: `legal_next_states` and the exhaustive test all read it.
TRANSITIONS: dict[tuple[OrderStatus, OrderEvent], OrderStatus] = {
    (S.CREATED, E.CHARGE_CREATED): S.PENDING_PAYMENT,
    (S.CREATED, E.CHARGE_FAILED): S.FAILED,
    (S.CREATED, E.CANCEL): S.CANCELLED,
    (S.PENDING_PAYMENT, E.PAYMENT_CONFIRMED): S.PAID,
    (S.PENDING_PAYMENT, E.EXPIRED): S.EXPIRED,
    (S.PENDING_PAYMENT, E.CHARGE_FAILED): S.FAILED,
    (S.PENDING_PAYMENT, E.CANCEL): S.CANCELLED,
    (S.EXPIRED, E.PAYMENT_CONFIRMED): S.PAID,
    (S.EXPIRED, E.CANCEL): S.CANCELLED,
    (S.FAILED, E.RETRY): S.PENDING_PAYMENT,
    (S.PAID, E.REFUND): S.REFUNDED,
    (S.PAID, E.CHARGEBACK): S.CHARGEBACK,
}

TERMINAL_STATES: frozenset[OrderStatus] = frozenset(
    {S.CANCELLED, S.REFUNDED, S.CHARGEBACK}
)


def transition(current: OrderStatus | str, event: OrderEvent | str) -> OrderStatus:
    """The status after `event` — or `InvalidTransition`."""
    cur = OrderStatus(current)
    ev = OrderEvent(event)
    try:
        return TRANSITIONS[(cur, ev)]
    except KeyError:
        raise InvalidTransition(cur, ev) from None


def legal_events(current: OrderStatus | str) -> tuple[OrderEvent, ...]:
    cur = OrderStatus(current)
    return tuple(ev for (st, ev) in TRANSITIONS if st is cur)


def legal_next_states(current: OrderStatus | str) -> tuple[OrderStatus, ...]:
    cur = OrderStatus(current)
    return tuple(new for (st, _ev), new in TRANSITIONS.items() if st is cur)


def is_terminal(status: OrderStatus | str) -> bool:
    return OrderStatus(status) in TERMINAL_STATES


__all__ = [
    "InvalidTransition",
    "OrderEvent",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "is_terminal",
    "legal_events",
    "legal_next_states",
    "transition",
]
