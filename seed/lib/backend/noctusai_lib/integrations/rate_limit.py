"""Outbound rate limiting for every external integration — the shared
client-side pacing + backoff primitive.

**Why this exists.** Bursting requests at an external API gets us
throttled or banned. It bit the Meta Marketing API (the 12-month ads
backfill tripped Meta's user-level limit mid-run, 2026-07-23) and the
Cloudflare MCP before it. Each integration used to fire ``httpx`` calls
as fast as the code looped, with no pacing and no principled backoff.

**Two independent protections, both needed:**

1. **Pacing (token bucket).** ``acquire(bucket)`` blocks the caller just
   long enough to hold the sustained request rate for that provider
   below a safe ceiling, while allowing a small burst. This is what
   keeps us from *hitting* the limit in the first place. Keyed by a
   ``bucket`` name (one per provider/host) so a slow provider doesn't
   throttle a fast one.

2. **Backoff-on-signal (`retry_with_backoff`).** When the provider still
   says "slow down" (HTTP 429, or a provider-specific rate-limit error),
   honor its ``Retry-After`` if given, else exponential backoff with
   jitter, bounded by a max attempt count. This is what makes us recover
   *gracefully* instead of hammering a throttled endpoint (which extends
   the ban).

**This is NOT the inbound limiter.** ``noctusai_lib.api.rate_limit_policies``
protects OUR endpoints (slowapi, requests coming IN). This module paces
requests going OUT to third parties. Different direction, different
concern.

**Config.** Per-bucket rate/burst default to conservative values and are
overridable via env (``NOC_RL_<BUCKET>_RPS`` / ``_BURST``) so a provider
can be tuned without a code change. Unknown buckets get the global
default. All clocks/sleeps are injectable for deterministic tests.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ─── Config ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BucketConfig:
    """Per-provider pacing + backoff policy.

    ``rate_per_sec`` — sustained requests/second the bucket refills at.
    ``burst`` — bucket capacity (max tokens = max back-to-back calls
    before pacing kicks in). ``max_retries`` / ``base_backoff`` /
    ``max_backoff`` govern ``retry_with_backoff``."""

    rate_per_sec: float
    burst: float
    max_retries: int = 5
    base_backoff: float = 2.0
    max_backoff: float = 60.0


# Conservative defaults. Meta's Marketing API is the sensitive one (the
# backfill that motivated this): pace to a few requests/second with a
# small burst. Providers not listed fall back to _DEFAULT.
_DEFAULT = BucketConfig(rate_per_sec=5.0, burst=10.0)
_DEFAULTS: dict[str, BucketConfig] = {
    "meta": BucketConfig(rate_per_sec=3.0, burst=5.0, max_retries=6),
    "google": BucketConfig(rate_per_sec=8.0, burst=16.0),
    "youtube": BucketConfig(rate_per_sec=3.0, burst=6.0),
    "whatsapp": BucketConfig(rate_per_sec=5.0, burst=10.0),
    "mailchimp": BucketConfig(rate_per_sec=8.0, burst=10.0),
    "vista": BucketConfig(rate_per_sec=5.0, burst=10.0),
    "llm": BucketConfig(rate_per_sec=8.0, burst=16.0),
}


def _config_for(bucket: str) -> BucketConfig:
    """Resolve a bucket's config: env override → built-in default →
    global default. Env vars: ``NOC_RL_<BUCKET>_RPS`` (float) and
    ``NOC_RL_<BUCKET>_BURST`` (float)."""
    base = _DEFAULTS.get(bucket, _DEFAULT)
    key = bucket.upper()
    rps = os.getenv(f"NOC_RL_{key}_RPS")
    burst = os.getenv(f"NOC_RL_{key}_BURST")
    if rps is None and burst is None:
        return base
    try:
        return BucketConfig(
            rate_per_sec=float(rps) if rps else base.rate_per_sec,
            burst=float(burst) if burst else base.burst,
            max_retries=base.max_retries,
            base_backoff=base.base_backoff,
            max_backoff=base.max_backoff,
        )
    except ValueError:
        logger.warning(
            "rate_limit: bad env override for bucket %r (rps=%r burst=%r) — using default",
            bucket, rps, burst,
        )
        return base


# ─── Clock seam (injectable for tests) ──────────────────────────────────────


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class _RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class VirtualClock:
    """A clock whose ``sleep`` advances virtual time instead of the wall
    clock — so pacing/backoff LOGIC runs for real (tokens refill, retries
    count) but a test never actually waits. Set it as the default in a
    test fixture via ``set_default_clock`` + ``limiter._reset()``."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def monotonic(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self._t += seconds


# Process-wide default clock. Lazily resolved (read at call time, not
# def/bind time) so a test can swap it via `set_default_clock`. Prod uses
# the real clock; tests install a VirtualClock so pacing never wall-waits.
_default_clock: Clock = _RealClock()


def _resolve_clock(clock: Clock | None) -> Clock:
    return clock if clock is not None else _default_clock


def set_default_clock(clock: Clock) -> None:
    """Swap the process-wide default clock (tests only). Call
    ``limiter._reset()`` afterwards so already-built buckets pick it up."""
    global _default_clock
    _default_clock = clock


def reset_default_clock() -> None:
    """Restore the real clock (test teardown)."""
    global _default_clock
    _default_clock = _RealClock()


# ─── Token bucket ────────────────────────────────────────────────────────────


class TokenBucket:
    """Thread-safe token bucket. ``acquire`` removes one token, blocking
    (sleeping) until one is available — so N concurrent threads calling
    the same provider are paced together, not each independently."""

    def __init__(self, config: BucketConfig, clock: Clock | None = None) -> None:
        self._rate = config.rate_per_sec
        self._capacity = config.burst
        self._clock = _resolve_clock(clock)
        self._tokens = config.burst
        self._last = self._clock.monotonic()
        self._lock = threading.Lock()

    def _refill_locked(self) -> None:
        now = self._clock.monotonic()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now

    def acquire(self, tokens: float = 1.0) -> float:
        """Block until ``tokens`` are available, then consume them.
        Returns the seconds waited (0.0 if immediate) — useful for
        telemetry/tests."""
        waited = 0.0
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return waited
                deficit = tokens - self._tokens
                sleep_for = deficit / self._rate if self._rate > 0 else 0.05
            # Sleep OUTSIDE the lock so other threads can refill/observe.
            self._clock.sleep(sleep_for)
            waited += sleep_for


# ─── Registry ────────────────────────────────────────────────────────────────


class RateLimiter:
    """Registry of named token buckets. One process-wide instance
    (``limiter``) is shared by every integration."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def bucket(self, name: str) -> TokenBucket:
        with self._lock:
            b = self._buckets.get(name)
            if b is None:
                b = TokenBucket(_config_for(name), clock=self._clock)
                self._buckets[name] = b
            return b

    def acquire(self, name: str, tokens: float = 1.0) -> float:
        return self.bucket(name).acquire(tokens)

    def config(self, name: str) -> BucketConfig:
        return _config_for(name)

    # Test seam: reset buckets (e.g. after patching config).
    def _reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = RateLimiter()


def acquire(bucket: str, tokens: float = 1.0) -> float:
    """Pace one outbound request against ``bucket`` — blocks until a
    token is free. Call this immediately before every external HTTP
    request for that provider. SYNC — do NOT call from an async coroutine
    (it would block the event loop); use ``acquire_async`` there."""
    return limiter.acquire(bucket, tokens)


# ─── Async pacing (for httpx.AsyncClient / async integrations) ──────────────


class _AsyncBucketState:
    """The token-bucket math for the async path. Reuses the same config +
    virtual/real clock as the sync bucket; the only difference is the wait
    is an ``await asyncio.sleep`` (never a thread block), so it cannot
    stall the event loop mailchimp/vista/etc run on."""

    def __init__(self, config: BucketConfig, clock: Clock | None = None) -> None:
        import asyncio

        self._rate = config.rate_per_sec
        self._capacity = config.burst
        self._clock = _resolve_clock(clock)
        self._tokens = config.burst
        self._last = self._clock.monotonic()
        self._lock = asyncio.Lock()

    def _refill_locked(self) -> None:
        now = self._clock.monotonic()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now

    async def acquire(self, tokens: float = 1.0) -> float:
        import asyncio

        waited = 0.0
        while True:
            async with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return waited
                deficit = tokens - self._tokens
                sleep_for = deficit / self._rate if self._rate > 0 else 0.05
            # A VirtualClock advances time on .sleep so tests never really
            # wait; the real clock uses asyncio.sleep so the loop keeps
            # serving other tasks.
            if isinstance(self._clock, VirtualClock):
                self._clock.sleep(sleep_for)
            else:
                await asyncio.sleep(sleep_for)
            waited += sleep_for


class _AsyncRegistry:
    def __init__(self) -> None:
        self._buckets: dict[str, _AsyncBucketState] = {}

    def bucket(self, name: str) -> _AsyncBucketState:
        b = self._buckets.get(name)
        if b is None:
            b = _AsyncBucketState(_config_for(name))
            self._buckets[name] = b
        return b

    def _reset(self) -> None:
        self._buckets.clear()


_async_registry = _AsyncRegistry()


async def acquire_async(bucket: str, tokens: float = 1.0) -> float:
    """Async twin of ``acquire`` — pace one outbound request without
    blocking the event loop. Call before every request in an async client
    (``await acquire_async("mailchimp")``)."""
    return await _async_registry.bucket(bucket).acquire(tokens)


async def retry_with_backoff_async(
    fn: Callable[[], Any],
    *,
    bucket: str = "default",
    is_retryable: Callable[[BaseException], bool],
    retry_after: Callable[[BaseException], float | None] | None = None,
    clock: Clock | None = None,
) -> Any:
    """Async twin of ``retry_with_backoff``. ``fn`` is an async callable
    (returns an awaitable). Same backoff policy; waits with
    ``await asyncio.sleep`` (or virtual time under a VirtualClock)."""
    import asyncio

    cfg = _config_for(bucket)
    clk = _resolve_clock(clock)
    attempt = 0
    while True:
        try:
            return await fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised if not retryable
            if not is_retryable(exc):
                raise
            attempt += 1
            if attempt > cfg.max_retries:
                logger.warning(
                    "rate_limit[%s] async: retryable error persisted after %d "
                    "retries — giving up: %s", bucket, cfg.max_retries, exc,
                )
                raise
            hinted = retry_after(exc) if retry_after else None
            delay = hinted if (hinted is not None and hinted >= 0) else _backoff_delay(
                attempt, cfg, clk
            )
            delay = min(delay, cfg.max_backoff)
            logger.info(
                "rate_limit[%s] async: retryable (attempt %d/%d) — backing off %.1fs: %s",
                bucket, attempt, cfg.max_retries, delay, exc,
            )
            if isinstance(clk, VirtualClock):
                clk.sleep(delay)
            else:
                await asyncio.sleep(delay)


# ─── Backoff-on-signal ───────────────────────────────────────────────────────


class RateLimitedError(Protocol):
    """Structural type for a provider error that carries retry info."""

    ...


def _backoff_delay(attempt: int, cfg: BucketConfig, clock: Clock) -> float:
    """Exponential backoff with full jitter, capped at ``max_backoff``.
    ``attempt`` is 1-based."""
    ceiling = min(cfg.max_backoff, cfg.base_backoff * (2 ** (attempt - 1)))
    # Full jitter (AWS recipe): uniform in [0, ceiling] — avoids
    # thundering-herd retries. random is fine here (not a security path).
    return random.uniform(0, ceiling)  # noqa: S311


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    bucket: str = "default",
    is_retryable: Callable[[BaseException], bool],
    retry_after: Callable[[BaseException], float | None] | None = None,
    clock: Clock | None = None,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> T:
    """Call ``fn``; on a *retryable* exception (per ``is_retryable`` —
    typically "is this a rate-limit / 429?"), wait and retry, up to the
    bucket's ``max_retries``.

    Wait time = the provider's ``Retry-After`` (via ``retry_after`` if it
    can extract one) when present, else exponential backoff with jitter.
    A non-retryable exception propagates immediately (no swallowing — the
    no-silent-errors contract). After the last attempt the final
    retryable exception is re-raised, never hidden."""
    cfg = _config_for(bucket)
    clk = _resolve_clock(clock)
    attempt = 0
    while True:
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised below if not retryable
            if not is_retryable(exc):
                raise
            attempt += 1
            if attempt > cfg.max_retries:
                logger.warning(
                    "rate_limit[%s]: retryable error persisted after %d retries — giving up: %s",
                    bucket, cfg.max_retries, exc,
                )
                raise
            hinted = retry_after(exc) if retry_after else None
            delay = hinted if (hinted is not None and hinted >= 0) else _backoff_delay(
                attempt, cfg, clk
            )
            delay = min(delay, cfg.max_backoff)
            logger.info(
                "rate_limit[%s]: retryable error (attempt %d/%d) — backing off %.1fs: %s",
                bucket, attempt, cfg.max_retries, delay, exc,
            )
            if on_retry:
                on_retry(attempt, delay, exc)
            clk.sleep(delay)


# ─── Convenience: paced + retried in one call ───────────────────────────────


def paced_call(
    fn: Callable[[], T],
    *,
    bucket: str,
    is_retryable: Callable[[BaseException], bool],
    retry_after: Callable[[BaseException], float | None] | None = None,
    clock: Clock | None = None,
) -> T:
    """The full protection for one logical operation: acquire a pacing
    token before EACH attempt (so a retry is itself paced), and back off
    on a rate-limit signal. This is the one-liner most integrations want
    around their request helper."""

    def _attempt() -> T:
        acquire(bucket)
        return fn()

    return retry_with_backoff(
        _attempt,
        bucket=bucket,
        is_retryable=is_retryable,
        retry_after=retry_after,
        clock=clock,
    )


# ─── httpx Retry-After parsing helper ───────────────────────────────────────


def parse_retry_after(value: Any) -> float | None:
    """Parse an HTTP ``Retry-After`` header value → seconds. Supports the
    delta-seconds form (``"120"``); the HTTP-date form is rare for rate
    limits and returns ``None`` (falls back to exponential backoff)."""
    if value is None:
        return None
    try:
        secs = float(str(value).strip())
        return secs if secs >= 0 else None
    except (TypeError, ValueError):
        return None


def _reset_all_buckets() -> None:
    """Test seam — clear both sync + async bucket registries so they
    rebuild on a freshly-set default clock."""
    limiter._reset()
    _async_registry._reset()


__all__ = [
    "BucketConfig",
    "RateLimiter",
    "TokenBucket",
    "VirtualClock",
    "acquire",
    "acquire_async",
    "limiter",
    "paced_call",
    "parse_retry_after",
    "reset_default_clock",
    "retry_with_backoff",
    "retry_with_backoff_async",
    "set_default_clock",
]
