"""Anomaly detection — security hardening (absorbed from imobi-scheduling, Wave 2.3).

**Scope.** Baseline counter-based threshold for tool-dispatch volume
per conversation. The brief explicitly says "basic threshold first;
ML later." We ship the threshold. ML lives in a future
`projects/platform-anomaly-detection/` follow-up.

**What it watches.** Tool-call rate per `chat_id` (the conversation
identity). A misbehaving LLM (looped tool calls / jailbreak that
extracts data via repeated lookups / runaway dispatch under prompt
injection) shows up as N dispatches in M seconds against the same
conversation. Threshold defaults: **20 dispatches per 60s** per
conversation — order-of-magnitude above normal (a polite booking
conversation runs ~3-5 dispatches end-to-end).

**Detection shape.** Sliding window via Redis ZSET — each dispatch
appends a timestamp; window slide drops old entries. Cheaper than
exact rate-limit math; we only need "approximately above threshold."

**Action on detection.** WARN log (structured, with conversation_id +
count + window). The log is the line of defense; ops dashboards
filter on it. No automatic kill-switch — false-positives blocking
real conversations is worse than the threat (the per-conversation
rate limiter at `conversation_rate_limit.py` is the hard guard).

**Seam shape**: a `wrap_handler(handler)` factory that mirrors
`sanitization.wrap_handler` — composes onto the tool handler so every
dispatch is observed. ContextVar-threading of conversation_id lives
in the consumer (`conversation.py::_build_processor`) so this module
stays a clean Redis-only adapter.

**Seed lift destination**: pure-logic surface (timestamp arithmetic +
Redis IO via the seed factory). **N=2 destination**:
`noctusai_lib.domain.anomaly.threshold_detector` when therapy / mailing
need the same shape. N=1 today.

**Why not just check inside `RedisConversationRateLimiter`?** Different
axis: rate-limiter blocks at message-rate (inbound throttle); anomaly
detector observes tool-dispatch-rate (LLM-loop behaviour). A user
sending 1 message that triggers a 30-call tool loop bypasses the
inbound limiter entirely but trips the anomaly detector. Separation
is by signal axis (inbound vs LLM-driven), not by storage shape.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnomalyObservation:
    """Outcome of `record_dispatch(...)`.

    Attributes:
        triggered: True if the window count exceeds threshold.
        count: Dispatches observed in the current window (post-record).
        threshold: Configured threshold.
        window_seconds: Configured window size.
    """

    triggered: bool
    count: int
    threshold: int
    window_seconds: int


class ToolDispatchAnomalyDetector:
    """Counter-based anomaly detector for tool dispatch rate.

    Uses Redis ZSET as a sliding-window store. Each dispatch's
    timestamp is added; `zremrangebyscore` slides the window forward;
    `zcard` reads the current count.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        threshold: int = 20,
        window_seconds: int = 60,
        prefix: str = "anomaly:tool_dispatch",
    ) -> None:
        """Construct the detector.

        Args:
            redis_client: Any `RedisBufferClient`-shaped client.
            threshold: Dispatches within `window_seconds` that trigger
                the WARN log. Default 20 — order-of-magnitude above
                normal booking conversation rates (~3-5 dispatches).
            window_seconds: Sliding window. Default 60s.
            prefix: Redis key prefix.
        """
        if threshold <= 0:
            raise ValueError(f"threshold must be positive, got {threshold}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")
        self._redis = redis_client
        self._threshold = threshold
        self._window_seconds = window_seconds
        self._prefix = prefix

    def record_dispatch(
        self,
        conversation_id: str,
        *,
        tool_name: Optional[str] = None,
    ) -> AnomalyObservation:
        """Record a tool dispatch + return whether it triggers the threshold.

        Returns:
            An `AnomalyObservation`. Caller MAY log/branch on
            `triggered` but the method already emits the WARN log so
            the caller can ignore the return value and the signal
            still surfaces.
        """
        if not conversation_id:
            logger.warning(
                "Anomaly detector received empty conversation_id; skipping"
            )
            return AnomalyObservation(
                triggered=False,
                count=0,
                threshold=self._threshold,
                window_seconds=self._window_seconds,
            )

        now = time.time()
        window_start = now - self._window_seconds
        key = f"{self._prefix}:{conversation_id}"
        member = f"{now}:{tool_name or 'unknown'}"

        try:
            self._redis.zadd(key, {member: now})
            self._redis.zremrangebyscore(key, "-inf", window_start)
            count = int(self._redis.zcard(key))
            self._redis.expire(key, self._window_seconds * 2)
        except Exception as exc:  # noqa: BLE001 — fail-open on Redis outage.
            logger.warning(
                "Anomaly detector Redis op failed for conversation_id=%s; failing OPEN: %s",
                conversation_id,
                exc,
            )
            return AnomalyObservation(
                triggered=False,
                count=0,
                threshold=self._threshold,
                window_seconds=self._window_seconds,
            )

        triggered = count > self._threshold
        if triggered:
            logger.warning(
                "Tool-dispatch anomaly: conversation_id=%s count=%d threshold=%d window_s=%d tool=%s",
                conversation_id,
                count,
                self._threshold,
                self._window_seconds,
                tool_name or "<unknown>",
            )
        return AnomalyObservation(
            triggered=triggered,
            count=count,
            threshold=self._threshold,
            window_seconds=self._window_seconds,
        )


# Module-level singleton — same pattern as metrics + rate_limiter.
_detector: Optional[ToolDispatchAnomalyDetector] = None


def configure_anomaly_detector(detector: ToolDispatchAnomalyDetector) -> None:
    """Install the module-level detector."""
    global _detector
    _detector = detector
    logger.info(
        "Tool-dispatch anomaly detector configured: threshold=%d window_s=%d",
        detector._threshold,  # noqa: SLF001 — config-time introspection.
        detector._window_seconds,  # noqa: SLF001
    )


def get_anomaly_detector() -> Optional[ToolDispatchAnomalyDetector]:
    """Return the configured detector, or None if not yet wired."""
    return _detector


def record_dispatch_observed(
    conversation_id: str,
    *,
    tool_name: Optional[str] = None,
) -> Optional[AnomalyObservation]:
    """Module-level convenience — record via the configured detector.

    Returns None if no detector is configured (default in tests that
    don't exercise the anomaly path). Callers don't need to branch on
    None — it means "detection disabled."
    """
    det = _detector
    if det is None:
        return None
    return det.record_dispatch(conversation_id, tool_name=tool_name)


def _reset_for_tests() -> None:
    """Test helper — clears the module-level singleton."""
    global _detector
    _detector = None


__all__ = [
    "AnomalyObservation",
    "ToolDispatchAnomalyDetector",
    "configure_anomaly_detector",
    "get_anomaly_detector",
    "record_dispatch_observed",
]
