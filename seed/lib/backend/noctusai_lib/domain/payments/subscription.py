"""Subscription lifecycle — pure state machine, zero gateway vocabulary.

Mirrors `noctusai_lib.domain.jobs.entity` exactly: a frozen value object
plus a total transition function validated against an explicit legal-set.
No IO, no clock read except an injectable `now`, no `noctusai_lib.
integrations.payments` import — this module has no idea Stripe or Asaas
exist. A gateway's raw status is the CALLER's translation problem (via
`GatewaySubscriptionStatus`); this module only knows OUR states.

Why "grace" exists and neither vendor reports it: Stripe and Asaas both
tell you a charge failed (`past_due`), but "how long do we keep serving
before we actually cut access" is a business decision this platform
makes, not something either gateway has an opinion about. Modeling it
as its own state — instead of a timestamp comparison scattered across
every consumer — is what makes "still eligible for the retry job to try
again" and "past the point of no return" two states you can pattern-match
on, one place.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


class SubscriptionState(str, Enum):
    """Lifecycle states for a subscription.

    INCOMPLETE → ACTIVE | EXPIRED
    TRIALING   → ACTIVE | CANCELED
    ACTIVE     → PAST_DUE | CANCELED
    PAST_DUE   → ACTIVE | GRACE
    GRACE      → ACTIVE | CANCELED | EXPIRED
    CANCELED, EXPIRED — terminal.

    INCOMPLETE — the first charge hasn't succeeded yet (Stripe's
        `payment_behavior=default_incomplete`; an Asaas subscription
        whose first generated payment is still PENDING).
    TRIALING — inside a trial period; no charge attempted yet.
    ACTIVE — in good standing.
    PAST_DUE — the most recent charge failed; automatic retries may
        still be in flight (the gateway's or our own retry job's).
    GRACE — retries exhausted; access is kept alive on a countdown, not
        indefinitely — this is OUR leniency window, not the gateway's.
    CANCELED — voluntarily ended (by the payer or an operator).
    EXPIRED — involuntarily ended (grace ran out unpaid, or the first
        charge never completed).
    """

    INCOMPLETE = "incomplete"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    GRACE = "grace"
    CANCELED = "canceled"
    EXPIRED = "expired"


#: Terminal states have no legal outward transition — a subscription
#: that reaches one of these is done, full stop. A new subscription
#: (not a transition) is the only way to bill that customer again.
TERMINAL_STATES: frozenset[SubscriptionState] = frozenset(
    {SubscriptionState.CANCELED, SubscriptionState.EXPIRED}
)

# Legal transitions. (current, target) → allowed. Anything not in this
# set raises in `transition` — total and explicit, no silent no-op for
# an unrecognized move.
_LEGAL_TRANSITIONS: frozenset[tuple[SubscriptionState, SubscriptionState]] = frozenset(
    {
        (SubscriptionState.INCOMPLETE, SubscriptionState.ACTIVE),
        (SubscriptionState.INCOMPLETE, SubscriptionState.EXPIRED),
        (SubscriptionState.TRIALING, SubscriptionState.ACTIVE),
        (SubscriptionState.TRIALING, SubscriptionState.CANCELED),
        (SubscriptionState.ACTIVE, SubscriptionState.PAST_DUE),
        (SubscriptionState.ACTIVE, SubscriptionState.CANCELED),
        (SubscriptionState.PAST_DUE, SubscriptionState.ACTIVE),
        (SubscriptionState.PAST_DUE, SubscriptionState.GRACE),
        (SubscriptionState.GRACE, SubscriptionState.ACTIVE),
        (SubscriptionState.GRACE, SubscriptionState.CANCELED),
        (SubscriptionState.GRACE, SubscriptionState.EXPIRED),
    }
)


@dataclass(frozen=True)
class Subscription:
    """A subscription's lifecycle snapshot. Frozen: every transition
    produces a new instance via `transition`; nothing mutates in place.
    """

    id: str
    external_reference: str  # our org/customer id — the conciliation key
    gateway: str  # "stripe" | "asaas" | any future gateway name, opaque here
    id_at_gateway: str
    state: SubscriptionState
    created_at: datetime
    updated_at: datetime
    canceled_at: datetime | None = None


def is_terminal(state: SubscriptionState) -> bool:
    """True iff no legal transition leaves `state`."""
    return state in TERMINAL_STATES


def legal_next_states(state: SubscriptionState) -> frozenset[SubscriptionState]:
    """Every state `state` may legally move to. Empty for a terminal state."""
    return frozenset(
        target for (source, target) in _LEGAL_TRANSITIONS if source == state
    )


def transition(
    subscription: Subscription,
    new_state: SubscriptionState,
    *,
    now: datetime | None = None,
) -> Subscription:
    """Return a new `Subscription` with `state = new_state`.

    Total and explicit: `(subscription.state, new_state)` MUST be in
    `_LEGAL_TRANSITIONS` or this raises `ValueError`. There is no
    "unknown transition, ignore and keep going" branch — an illegal
    transition is a caller bug (a webhook handler racing two events, a
    grace-period job firing twice) and MUST surface, not vanish.

    Args:
        subscription: source snapshot (immutable input).
        new_state: target state.
        now: clock injection seam for deterministic tests; defaults to
            `datetime.now(timezone.utc)`.

    Raises:
        ValueError: the transition is not in the legal set.
    """
    if (subscription.state, new_state) not in _LEGAL_TRANSITIONS:
        raise ValueError(
            f"Illegal Subscription transition: {subscription.state.value} -> "
            f"{new_state.value}"
        )

    stamp = now or datetime.now(timezone.utc)
    canceled_at = (
        stamp
        if new_state in (SubscriptionState.CANCELED, SubscriptionState.EXPIRED)
        else subscription.canceled_at
    )
    return replace(
        subscription, state=new_state, updated_at=stamp, canceled_at=canceled_at
    )


__all__ = [
    "TERMINAL_STATES",
    "Subscription",
    "SubscriptionState",
    "is_terminal",
    "legal_next_states",
    "transition",
]
