"""Metrics-sink seam — placeholder for production hardening (absorbed from imobi-scheduling, Wave 2.3).

**Status: deferred-with-destination** (per PROJECT.md §6 Phase 10).

A full metrics implementation (StatsD / OpenTelemetry / Prometheus
exporter) is a platform-wide concern, not one product's responsibility.
Implementing it here would either (a) duplicate work the platform will
eventually do at the seed layer, or (b) lock in a wire format the
platform later wants to change. Both anti-patterns.

This module ships:

  - `Counter` Protocol — what every metrics sink must satisfy.
  - `NoopCounter` — default in production today; logs are the metric.
  - `record_tool_dispatch` / `record_llm_call` — semantic helpers the
    conversation worker + dispatcher can call without knowing the
    backend. Calls flow through the configured `Counter`; until a real
    backend is wired, they fall through `NoopCounter` (which is just
    debug-level logging — no silent-ok, the line is observable).

When the platform-wide metrics project lands (filed as
`projects/platform-metrics/` follow-up), this module becomes a thin
re-export of `noctusai_lib.observability.counter` and the wire is
flipped at lifespan startup. No call-site churn.

**Why not just skip this for v1?** Because the *call sites* matter —
once `dispatch_tool` + `chat_completion` start emitting metric events,
backfilling them later is a cross-cutting refactor. Wiring the seam
now (with `NoopCounter` as default) lets the future metrics project
ship a one-line lifespan change.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Counter(Protocol):
    """Minimal metrics-counter Protocol.

    Implementations:
      - `NoopCounter` — default; logs at debug level.
      - Future: `StatsDCounter`, `PrometheusCounter`,
        `OpenTelemetryCounter`.

    Tags are a flat dict[str, str] — keep keys low-cardinality
    (`tool_name="propose_appointment"`, NOT `request_id="..."`).
    """

    def increment(
        self,
        metric: str,
        *,
        value: int = 1,
        tags: Optional[dict[str, str]] = None,
    ) -> None:
        ...


class NoopCounter:
    """Default counter — debug-level logging.

    Not silent: every recorded event surfaces in the structured-log
    stream at DEBUG (which our `configure_logging` JSON formatter
    captures + ships to whatever log sink the deployment uses). When a
    real metrics backend lands, swap this out at lifespan startup; no
    call-site change.
    """

    def increment(
        self,
        metric: str,
        *,
        value: int = 1,
        tags: Optional[dict[str, str]] = None,
    ) -> None:
        logger.debug(
            "metric.increment name=%s value=%d tags=%s",
            metric,
            value,
            tags or {},
        )


# Module-level singleton. Lifespan startup MAY swap this out with a real
# implementation when the platform-metrics project lands.
_counter: Counter = NoopCounter()


def configure_counter(counter: Counter) -> None:
    """Replace the module-level counter (idempotent across re-configs).

    Called from lifespan startup once the platform-metrics project
    ships a real backend. The conversation worker + dispatcher read
    via `get_counter()` at call time (not at import) so this swap is
    runtime-visible.
    """
    global _counter
    _counter = counter
    logger.info("Metrics counter configured: %s", type(counter).__name__)


def get_counter() -> Counter:
    """Return the configured counter (defaults to `NoopCounter`)."""
    return _counter


# ---------------------------------------------------------------------------
# Semantic helpers — used by call sites that should NOT know the backend.
# ---------------------------------------------------------------------------


def record_tool_dispatch(tool_name: str, *, success: bool) -> None:
    """Emit a counter event for a tool-dispatch outcome.

    Call from the conversation-worker tool handler after each invocation.
    Tags `success` so a single metric tracks both success + failure
    rates without needing two metric names.
    """
    get_counter().increment(
        "bot.tool_dispatch",
        tags={"tool": tool_name, "success": str(success).lower()},
    )


def record_llm_call(*, model: str, success: bool) -> None:
    """Emit a counter event for an LLM completion call.

    Call after every `dispatcher.reply(...)` round trip. Useful for
    tracking model-level success rates + spend cardinality.
    """
    get_counter().increment(
        "bot.llm_call",
        tags={"model": model, "success": str(success).lower()},
    )


__all__ = [
    "Counter",
    "NoopCounter",
    "configure_counter",
    "get_counter",
    "record_llm_call",
    "record_tool_dispatch",
]
