"""Request timing — every product measures its own latency by construction.

Owner mandate 2026-10-22: fast responses are mandatory. A budget nobody can
read is decoration, so the seed app factory registers this middleware for
every product. It does two cheap things per HTTP request:

* adds ``Server-Timing: app;dur=<ms>`` (visible in browser devtools) plus the CONCURRENCY metrics
  below, so a slow request can be told apart: real work vs waiting behind other requests;
* emits ONE structured log line, parsed by ``noctus.dev.latency_report``::

      req_timing method=GET route=/api/finance/accounts/{account_id} status=200 dur_ms=41.7 inflight=3 inflight_peak=5 ...

Everything after ``dur_ms=`` is optional ``key=value`` (old parsers stop at dur_ms; old lines stay valid).
The ROUTE TEMPLATE is logged, never the raw path, so ids / emails / tokens
never reach the logs. A request that matched no route logs ``route=<unmatched>``
(bounded cardinality, no attacker-controlled path text).

Duration is measured to the response START (first byte), the same definition
`RequestLoggingMiddleware` uses. Pure ASGI (see ``middleware.py`` for why
``BaseHTTPMiddleware`` is forbidden here).

KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
import time
import weakref
from typing import Any, Optional

logger = logging.getLogger("noctusai.request_timing")

LOG_PREFIX = "req_timing"
UNMATCHED_ROUTE = "<unmatched>"
LAG_TICK_S = 0.05  # event-loop lag sampler period; runs ONLY while >=1 request is in flight

# --- process-wide concurrency state (plain ints; mutated under the GIL / _LOCK) ---------------
_LOCK = threading.Lock()
_INFLIGHT = 0
_ACTIVE: set[int] = set()  # ids of active stats dicts, for peak/lag fan-out
_ACTIVE_STATS: dict[int, dict] = {}
_TICKING: "weakref.WeakSet[asyncio.AbstractEventLoop]" = weakref.WeakSet()

_STATS: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("request_timing_stats", default=None)


def current_stats() -> Optional[dict]:
    """The current request's stats dict (shared into worker threads), or ``None`` outside a request."""
    return _STATS.get()


def record_blocking(wait_s: float, run_s: float) -> None:
    """One ``run_blocking`` hop: ``wait_s`` = submit -> fn starts, ``run_s`` = time inside fn."""
    st = _STATS.get()
    if st is None:
        return
    with _LOCK:
        st["blk_n"] += 1
        st["blk_wait_s"] += wait_s
        st["blk_run_s"] += run_s


def record_parallel(wait_s: float) -> None:
    """One ``run_parallel`` thunk: time queued in the fan-out pool before it started."""
    st = _STATS.get()
    if st is None:
        return
    with _LOCK:
        st["par_n"] += 1
        st["par_wait_s"] += wait_s


def route_template(scope) -> str:
    """The matched route's path template (``/x/{id}``), else ``<unmatched>``.

    Starlette's router writes the matched route into the shared ``scope`` dict,
    which this middleware (wrapping the router) sees after the app has run.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else UNMATCHED_ROUTE


def _new_stats(inflight: int) -> dict:
    return {"inflight": inflight, "peak": inflight, "blk_n": 0, "blk_wait_s": 0.0, "blk_run_s": 0.0,
            "par_n": 0, "par_wait_s": 0.0, "lag_ms": None, "tp_busy": None, "tp_wait": None}


def _threadpool_sample(st: dict) -> None:
    """Read (never patch) anyio's default limiter -- the one Starlette uses for plain ``def``
    endpoints/deps and ``run_blocking``: tokens borrowed and tasks queued for a thread."""
    try:
        import anyio.to_thread
        lim = anyio.to_thread.current_default_thread_limiter()
        busy, waiting = lim.borrowed_tokens, lim.statistics().tasks_waiting
    except Exception:  # noqa: BLE001 -- observability must never break a request
        return
    st["tp_busy"] = busy if st["tp_busy"] is None else max(st["tp_busy"], busy)
    st["tp_wait"] = waiting if st["tp_wait"] is None else max(st["tp_wait"], waiting)


def _tick(loop: asyncio.AbstractEventLoop, due: float) -> None:
    lag_ms = max(0.0, (loop.time() - due) * 1000.0)
    for st in list(_ACTIVE_STATS.values()):
        if st["lag_ms"] is None or lag_ms > st["lag_ms"]:
            st["lag_ms"] = lag_ms
    if _ACTIVE_STATS:
        nxt = loop.time() + LAG_TICK_S
        loop.call_at(nxt, _tick, loop, nxt)
    else:
        _TICKING.discard(loop)


def _ensure_sampler() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if loop in _TICKING:
        return
    _TICKING.add(loop)
    due = loop.time() + LAG_TICK_S
    loop.call_at(due, _tick, loop, due)


def server_timing_value(dur_ms: float, st: dict) -> str:
    parts = [f"app;dur={dur_ms:.1f}", f'inflight;desc="{st["inflight"]}"', f'inflight_peak;desc="{st["peak"]}"']
    if st["blk_n"]:
        parts.append(f'blk;dur={st["blk_run_s"] * 1000:.1f};desc="{st["blk_n"]}"')
        parts.append(f'blkq;dur={st["blk_wait_s"] * 1000:.1f}')
    if st["par_n"]:
        parts.append(f'parq;dur={st["par_wait_s"] * 1000:.1f};desc="{st["par_n"]}"')
    if st["lag_ms"] is not None:
        parts.append(f'lag;dur={st["lag_ms"]:.1f}')
    if st["tp_wait"] is not None:
        parts.append(f'tp_busy;desc="{st["tp_busy"]}"')
        parts.append(f'tp_wait;desc="{st["tp_wait"]}"')
    return ", ".join(parts)


def log_suffix(st: dict) -> str:
    """`` key=value`` tail for the req_timing line (appended AFTER ``dur_ms=``)."""
    out = f' inflight={st["inflight"]} inflight_peak={st["peak"]}'
    if st["blk_n"]:
        out += f' blk_n={st["blk_n"]} blk_ms={st["blk_run_s"] * 1000:.1f} blkq_ms={st["blk_wait_s"] * 1000:.1f}'
    if st["par_n"]:
        out += f' par_n={st["par_n"]} parq_ms={st["par_wait_s"] * 1000:.1f}'
    if st["lag_ms"] is not None:
        out += f' lag_ms={st["lag_ms"]:.1f}'
    if st["tp_wait"] is not None:
        out += f' tp_busy={st["tp_busy"]} tp_wait={st["tp_wait"]}'
    return out


class RequestTimingMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        global _INFLIGHT
        start = time.perf_counter()
        method = scope.get("method", "")
        with _LOCK:
            _INFLIGHT += 1
            st = _new_stats(_INFLIGHT)
            for other in _ACTIVE_STATS.values():
                if _INFLIGHT > other["peak"]:
                    other["peak"] = _INFLIGHT
            _ACTIVE_STATS[id(st)] = st
        _threadpool_sample(st)
        _ensure_sampler()
        token = _STATS.set(st)

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                dur_ms = (time.perf_counter() - start) * 1000.0
                _threadpool_sample(st)
                headers = list(message.get("headers") or [])
                headers.append((b"server-timing", server_timing_value(dur_ms, st).encode("latin-1")))
                message = {**message, "headers": headers}
                logger.info(
                    "%s method=%s route=%s status=%s dur_ms=%.1f%s",
                    LOG_PREFIX, method, route_template(scope), message.get("status", 0), dur_ms, log_suffix(st),
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _STATS.reset(token)
            with _LOCK:
                _INFLIGHT -= 1
                _ACTIVE_STATS.pop(id(st), None)
