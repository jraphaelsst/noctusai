"""Synchronous exponential-backoff retry helper for product-side IO calls.

**Why this exists** — the absorbed `imobi-scheduling` scheduling domain (social-wiring Wave 2.3)
adds transient-failure retries on the two external write paths the bot
depends on at runtime: Google Calendar (`create_event` / `update_event` /
`delete_event`) and WAHA `send_text`. The seed ships
`noctusai_lib.domain.jobs.retry_policy.RetryPolicy` (exponential-backoff
math + the canonical 3-try/1s/2x/300s policy) but no in-flight retry
*wrapper* — `RetryPolicy` is consumed by the seed's queue-job worker,
which re-enqueues failed jobs after `next_retry_at(...)`. That shape
doesn't help an in-flight blocking call like a Calendar API hit.

This module composes the seed's `RetryPolicy` with a thin synchronous
`retry_call(...)` wrapper that:

  1. Invokes the supplied callable.
  2. On listed transient exceptions, sleeps `next_retry_at(...) - now()`
     (i.e. the seed's backoff formula) + retries up to `max_retries`.
  3. On exhaustion OR a non-listed exception, raises the underlying
     exception unmodified — call sites' error semantics are preserved.

**Why product-side (not seed-side) at v1** — N=1 consumer (this product).
Per `KB § PATTERNS/seed-fake-real-adapter.md` + the recurrence rule, the
seed gains the wrapper when N=2 consumers need the same shape (e.g.
mailing's outbound send / therapy's calendar invites). At that point the
right destination is `noctusai_lib.primitives.retry` (a stateless helper
fits the primitives layer per `KB § PATTERNS/seed-lib-layout.md`). The
follow-up project is filed in PROJECT.md §11.

**Anti-pattern guard** — never wrap retries around code paths that have
their own retry semantics (e.g. OpenAI SDK has built-in retries). Apply
only to outermost call boundaries the consumer owns.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, TypeVar

from noctusai_lib.domain.jobs.retry_policy import (
    DEFAULT_POLICY,
    RetryPolicy,
    next_retry_at,
)

logger = logging.getLogger(__name__)


T = TypeVar("T")


# Canonical policies for this product's transient-failure write paths.
# Tuned against the operational profile in PROJECT.md §6 Phase 10:
#
#   - Calendar: 3 retries, 1s base, 2x, 30s cap. Google Calendar rate
#     limits + transient 503s clear within 5-10 seconds typically; a
#     longer cap rarely helps and lengthens the inbound webhook
#     response time WAHA tolerates (~25s before resend).
#
#   - WAHA: 3 retries, 0.5s base, 2x, 10s cap. WAHA is local-network
#     by deployment convention (Docker fabric), so failures are usually
#     transient TCP hiccups; a shorter cap matches the "either it
#     comes back in seconds or we're in a real outage" profile.
RETRY_POLICY_CALENDAR: RetryPolicy = RetryPolicy(
    max_retries=3,
    backoff_seconds=1.0,
    backoff_multiplier=2.0,
    max_backoff_seconds=30.0,
)
RETRY_POLICY_WAHA: RetryPolicy = RetryPolicy(
    max_retries=3,
    backoff_seconds=0.5,
    backoff_multiplier=2.0,
    max_backoff_seconds=10.0,
)


def retry_call(
    callable_: Callable[[], T],
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    transient_exceptions: Iterable[type[BaseException]] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    label: str = "retry_call",
) -> T:
    """Invoke ``callable_`` with exponential-backoff retries on transients.

    The callable is invoked at least once (`max_retries=0` → no retries,
    one shot). Listed `transient_exceptions` trigger backoff + retry;
    any other exception propagates immediately. The final attempt's
    exception is re-raised on exhaustion.

    Sleep is parameterized so tests can pass a no-op sleep without
    mutating ``time.sleep``. Default is the real ``time.sleep`` — which
    means consumers in async hot paths should call this via
    ``asyncio.to_thread(retry_call, ...)`` to avoid blocking the event
    loop.

    Args:
        callable_: Zero-arg callable. Use ``functools.partial`` or a
            lambda to bind arguments at the call site.
        policy: `RetryPolicy` from the seed. Defaults to
            `noctusai_lib.domain.jobs.retry_policy.DEFAULT_POLICY` (3
            retries, 1s base, 2x, 300s cap).
        transient_exceptions: Tuple of exception classes that trigger
            retry. Anything not in this list propagates on the first
            occurrence. Defaults to broad `Exception` — narrow at call
            site (e.g. `httpx.HTTPError`).
        sleep: Sleep function. Tests pass a no-op. Defaults to
            `time.sleep`.
        label: Human-readable label used in retry-warning logs (e.g.
            ``"calendar.create_event"``). Helps operators correlate
            log lines to which write path is throttling.

    Returns:
        The callable's return value on the first successful attempt.

    Raises:
        The underlying exception when (a) it's not in
        ``transient_exceptions`` (immediate) or (b) ``max_retries`` is
        exhausted (after the final attempt).
    """
    exceptions_tuple = tuple(transient_exceptions)
    last_exc: BaseException | None = None
    attempts = policy.max_retries + 1  # initial try + retries

    for attempt_index in range(attempts):
        try:
            return callable_()
        except exceptions_tuple as exc:
            last_exc = exc
            # Decide whether to sleep + retry. If this was the final
            # attempt, fall through to re-raise.
            if attempt_index >= policy.max_retries:
                break

            # `retry_count` for the BACKOFF formula = retries consumed
            # so far. attempt_index=0 → 0 retries consumed → use base
            # `backoff_seconds`. attempt_index=1 → 1 retry consumed →
            # base * multiplier. Matches the seed's formula at
            # `noctusai_lib.domain.jobs.retry_policy.next_retry_at`.
            now = datetime.now(timezone.utc)
            scheduled_for = next_retry_at(
                retry_count=attempt_index,
                policy=policy,
                now=now,
            )
            delay_seconds = (scheduled_for - now).total_seconds()
            logger.warning(
                "%s transient failure (attempt %d/%d): %s. Retrying in %.1fs.",
                label,
                attempt_index + 1,
                attempts,
                exc,
                delay_seconds,
            )
            if delay_seconds > 0:
                sleep(delay_seconds)

    # Exhausted. Re-raise the last transient.
    assert last_exc is not None  # for type-checkers
    logger.error(
        "%s exhausted %d attempts; surfacing last exception.",
        label,
        attempts,
    )
    raise last_exc


__all__ = [
    "RETRY_POLICY_CALENDAR",
    "RETRY_POLICY_WAHA",
    "retry_call",
]
