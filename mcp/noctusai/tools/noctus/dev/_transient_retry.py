"""Shared transient-failure retry for toolkit HTTP calls (2026-10-21).

ONE chokepoint wrapper (used by ``migrate_product.SupabaseMgmtExecutor``, which
every Supabase-Management-API toolkit tool reuses via ``make_sql_executor``):
retries ONLY transport-level failures, paced ~1s/3s/9s with jitter, then
re-raises the ORIGINAL error. Backoff math is the seed's own
``noctusai_lib.domain.jobs.retry_policy`` (no second formula).

Never retried: any HTTP 4xx other than 429, and any SQL error. A ``NOC_PROBE``
refusal is a 400 and is a PASS for ``verify_db_guards`` -- retrying it would
be wrong by construction.

Two classes:
  * safe      -- the request provably never reached the server (DNS failure,
                 connection refused/unreachable, HTTP 429). Always retried.
  * ambiguous -- the request may have executed (read timeout, connection reset,
                 HTTP 502/503/504). Retried unless ``retry_ambiguous=False``
                 (callers that run non-idempotent writes opt out).
"""

from __future__ import annotations

import http.client
import random
import socket
import ssl
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from noctusai_lib.domain.jobs.retry_policy import RetryPolicy, next_retry_at

T = TypeVar("T")

#: 3 retries, 1s base, x3 growth => 1s / 3s / 9s.
DEFAULT_POLICY = RetryPolicy(max_retries=3, backoff_seconds=1.0, backoff_multiplier=3.0, max_backoff_seconds=30.0)
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_MAX_RETRY_AFTER_S = 30.0
_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def classify(exc: BaseException) -> str | None:
    """``'safe'`` | ``'ambiguous'`` | ``None`` (not transient -- never retry)."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return "safe"
        return "ambiguous" if exc.code in _RETRYABLE_STATUS else None
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (socket.gaierror, ConnectionRefusedError)):
            return "safe"
        if isinstance(reason, BaseException):
            return classify(reason) or ("ambiguous" if isinstance(reason, OSError) else None)
        return "safe" if "nodename nor servname" in str(reason) else "ambiguous"
    if isinstance(exc, (socket.gaierror, ConnectionRefusedError)):
        return "safe"
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionError, http.client.HTTPException, ssl.SSLError)):
        return "ambiguous"
    return None


def is_transient(exc: BaseException) -> bool:
    return classify(exc) is not None


def _delay(attempt: int, policy: RetryPolicy, exc: BaseException, rng: Callable[[], float]) -> float:
    base = (next_retry_at(attempt, policy, _EPOCH) - _EPOCH).total_seconds()
    if isinstance(exc, urllib.error.HTTPError):
        ra = exc.headers.get("Retry-After") if exc.headers else None
        try:
            if ra is not None:
                return min(max(float(ra), 0.0), _MAX_RETRY_AFTER_S)
        except ValueError:
            pass
    return base * (1.0 + 0.25 * rng())  # up to +25% jitter


def call_with_transient_retry(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    retry_ambiguous: bool = True,
    sleep: Callable[[float], Any] = time.sleep,
    rng: Callable[[], float] = random.random,
    on_retry: Callable[[int, BaseException], Any] | None = None,
) -> T:
    """Call ``fn``; on a transient failure sleep + retry up to
    ``policy.max_retries`` times, then raise the last (original) error."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 -- classified; non-transient re-raised untouched
            kind = classify(exc)
            if kind is None or (kind == "ambiguous" and not retry_ambiguous) or attempt >= policy.max_retries:
                try:
                    exc.noc_retry_attempts = attempt  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001 -- slotted exception types: attribute is best-effort metadata
                    pass
                raise
            if on_retry:
                on_retry(attempt + 1, exc)
            sleep(_delay(attempt, policy, exc, rng))
            attempt += 1


__all__ = ["DEFAULT_POLICY", "call_with_transient_retry", "classify", "is_transient"]
