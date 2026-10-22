"""Request timing — every product measures its own latency by construction.

Owner mandate 2026-10-22: fast responses are mandatory. A budget nobody can
read is decoration, so the seed app factory registers this middleware for
every product. It does two cheap things per HTTP request:

* adds ``Server-Timing: app;dur=<ms>`` (visible in browser devtools);
* emits ONE structured log line, parsed by ``noctus.dev.latency_report``::

      req_timing method=GET route=/api/finance/accounts/{account_id} status=200 dur_ms=41.7

The ROUTE TEMPLATE is logged, never the raw path, so ids / emails / tokens
never reach the logs. A request that matched no route logs ``route=<unmatched>``
(bounded cardinality, no attacker-controlled path text).

Duration is measured to the response START (first byte), the same definition
`RequestLoggingMiddleware` uses. Pure ASGI (see ``middleware.py`` for why
``BaseHTTPMiddleware`` is forbidden here).

KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("noctusai.request_timing")

LOG_PREFIX = "req_timing"
UNMATCHED_ROUTE = "<unmatched>"


def route_template(scope) -> str:
    """The matched route's path template (``/x/{id}``), else ``<unmatched>``.

    Starlette's router writes the matched route into the shared ``scope`` dict,
    which this middleware (wrapping the router) sees after the app has run.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else UNMATCHED_ROUTE


class RequestTimingMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope.get("method", "")

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                dur_ms = (time.perf_counter() - start) * 1000.0
                headers = list(message.get("headers") or [])
                headers.append((b"server-timing", f"app;dur={dur_ms:.1f}".encode("latin-1")))
                message = {**message, "headers": headers}
                logger.info(
                    "%s method=%s route=%s status=%s dur_ms=%.1f",
                    LOG_PREFIX, method, route_template(scope), message.get("status", 0), dur_ms,
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
