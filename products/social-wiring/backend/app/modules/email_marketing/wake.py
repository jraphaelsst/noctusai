"""Idle gates of the mailing loops + the wake calls of their producers (in-process).

The send loop used to ask `send_logs` "anything queued?" every 30 s, forever, with `select=*` + a contacts join
(~2.6k calls / 22 h on an empty queue, 2026-11-09 Supabase egress incident, `KB § PATTERNS/backend/polling-request-budget.md`).
Now an empty tick backs the loop off to `SEND_FALLBACK_S`, and whoever QUEUES a send (a campaign starting, an
automation step) wakes it at once, so nothing a user is waiting for is delayed. The fallback only covers a producer
outside this process (none today).
"""
from __future__ import annotations

from noctusai_lib.primitives.ttl_cache import IdleGate

#: Longest the send loop sleeps when idle (a producer in this process wakes it sooner).
SEND_FALLBACK_S = 300.0
#: Longest the scheduled-campaigns check sleeps (it sleeps only until the next `scheduled_at` when one is known).
CAMPAIGNS_FALLBACK_S = 600.0

SEND_GATE = IdleGate(SEND_FALLBACK_S)
CAMPAIGNS_GATE = IdleGate(CAMPAIGNS_FALLBACK_S)


def wake_send_loop() -> None:
    """A `send_logs` row was queued in this process: the next tick sends."""
    SEND_GATE.wake()


def wake_campaigns_check() -> None:
    """A campaign was (re)scheduled in this process: the next tick re-reads `scheduled_at`."""
    CAMPAIGNS_GATE.wake()


__all__ = [
    "CAMPAIGNS_FALLBACK_S",
    "CAMPAIGNS_GATE",
    "SEND_FALLBACK_S",
    "SEND_GATE",
    "wake_campaigns_check",
    "wake_send_loop",
]
