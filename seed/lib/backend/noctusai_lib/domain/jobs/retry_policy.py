"""Retry policy + exponential-backoff math.

Pure-domain. No clock side effects — all helpers take `now` as input so
tests are deterministic and timezone-explicit.
"""

from __future__ import annotations

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


def next_retry_at(retry_count: int, policy: RetryPolicy, now: datetime) -> datetime:
    """Compute when the next retry should fire.

    Pure: deterministic given `(retry_count, policy, now)`.

    Backoff formula:
        delay = min(
            policy.backoff_seconds * (policy.backoff_multiplier ** retry_count),
            policy.max_backoff_seconds,
        )

    `retry_count` is the number of retries ALREADY consumed (so the
    first retry uses `retry_count=0` → `backoff_seconds`).

    Args:
        retry_count: retries consumed so far (>= 0).
        policy: RetryPolicy for this job type.
        now: current clock; the returned datetime is `now + delay`.

    Returns:
        UTC datetime (or whatever timezone `now` carries) of the next retry.
    """
    if retry_count < 0:
        raise ValueError(f"retry_count must be >= 0, got {retry_count}")

    delay_seconds = policy.backoff_seconds * (policy.backoff_multiplier ** retry_count)
    if delay_seconds > policy.max_backoff_seconds:
        delay_seconds = policy.max_backoff_seconds
    return now + timedelta(seconds=delay_seconds)


__all__ = [
    "DEFAULT_POLICY",
    "RetryPolicy",
    "next_retry_at",
]
