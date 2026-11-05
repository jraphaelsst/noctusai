"""Retry policy + exponential-backoff math.

Pure-domain. No clock side effects — all helpers take `now` as input so
tests are deterministic and timezone-explicit.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential-backoff retry configuration.

    Defaults model the canonical "3 tries, 1s base, doubling, capped at
    5 minutes" pattern that fits most product-side handlers. Override
    via `RetryPolicy(...)` when a product needs different timing
    (e.g. AI batch retries with longer caps).

    Fields:
        max_retries: total retry attempts (excluding the first run).
        backoff_seconds: base delay before the first retry.
        backoff_multiplier: per-retry growth factor.
        max_backoff_seconds: cap so very high retry counts don't spiral.
    """

    max_retries: int = 3
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 300.0


# Default-policy singleton used by `Worker` when caller doesn't override.
DEFAULT_POLICY: RetryPolicy = RetryPolicy()


def backoff_ceiling_seconds(retry_count: int, policy: RetryPolicy) -> float:
    """Un-jittered exponential delay for `retry_count`, capped at
    `policy.max_backoff_seconds` (the full-jitter upper bound)."""
    if retry_count < 0:
        raise ValueError(f"retry_count must be >= 0, got {retry_count}")
    try:
        raw = policy.backoff_seconds * (policy.backoff_multiplier ** retry_count)
    except OverflowError:
        return policy.max_backoff_seconds
    return min(raw, policy.max_backoff_seconds)


def next_retry_at(
    retry_count: int,
    policy: RetryPolicy,
    now: datetime,
    *,
    rng: random.Random | None = None,
    jitter: bool = True,
) -> datetime:
    """Compute when the next retry should fire.

    Full jitter ("Exponential Backoff And Jitter", AWS Architecture Blog):

        ceiling = min(backoff_seconds * multiplier**retry_count, max_backoff_seconds)
        delay   = uniform(0, ceiling)

    Without jitter, jobs that failed together retry together and re-hammer
    the same vendor (thundering herd). `rng` is injectable/seedable so tests
    are deterministic (`random.Random(42)`); default is the module RNG.
    `jitter=False` returns the exact ceiling (legacy deterministic shape).

    `retry_count` is the number of retries ALREADY consumed (first retry
    uses `retry_count=0`).

    Returns:
        `now + delay`, in whatever timezone `now` carries.
    """
    ceiling = backoff_ceiling_seconds(retry_count, policy)
    if jitter:
        delay_seconds = (rng or random).uniform(0.0, ceiling)  # noqa: S311 — not a security path
    else:
        delay_seconds = ceiling
    return now + timedelta(seconds=delay_seconds)


__all__ = [
    "DEFAULT_POLICY",
    "RetryPolicy",
    "backoff_ceiling_seconds",
    "next_retry_at",
]
