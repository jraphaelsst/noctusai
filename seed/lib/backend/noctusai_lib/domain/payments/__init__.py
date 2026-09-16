"""Payments domain — pure business rules layered on top of gateway data.

Two independent pieces, both zero-IO-in-substance:

* `subscription` — a total, explicit state machine (`SubscriptionState`,
  `transition`). `trialing -> active -> past_due -> grace ->
  canceled|expired`, plus `incomplete` for a first charge that hasn't
  succeeded yet. An unrecognized transition raises — never a silent
  no-op — because a state machine that quietly ignores an illegal move
  is a state machine that lies about what actually happened.
* `event_inbox` — `EventInbox` (Protocol + Fake + RealSupabase +
  factory), proving a duplicate `(gateway, event_id)` webhook delivery
  is a no-op. Gateways retry; this is the seam that makes retrying safe.

Neither module imports `noctusai_lib.integrations.payments` — the
gateway adapters translate vendor status strings INTO
`GatewaySubscriptionStatus`, and a consumer decides how a gateway status
change maps to a `transition()` call. That direction-of-dependency is
deliberate: domain rules must not know which vendor is configured.
"""
from __future__ import annotations

from .event_inbox import EventInbox, FakeEventInbox, RealSupabaseEventInbox, make_event_inbox
from .subscription import (
    TERMINAL_STATES,
    Subscription,
    SubscriptionState,
    is_terminal,
    legal_next_states,
    transition,
)

__all__ = [
    "TERMINAL_STATES",
    "EventInbox",
    "FakeEventInbox",
    "RealSupabaseEventInbox",
    "Subscription",
    "SubscriptionState",
    "is_terminal",
    "legal_next_states",
    "make_event_inbox",
    "transition",
]
