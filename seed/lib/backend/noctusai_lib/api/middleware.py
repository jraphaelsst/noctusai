"""
Middleware for request tracking, logging, and monitoring.

Provides:
- CorrelationIdMiddleware: generates/extracts correlation IDs for request tracing
- RequestLoggingMiddleware: logs request/response details with timing
- MaxBodySizeMiddleware: rejects oversized request bodies before handlers run
- get_correlation_id(): accessor for the current request's correlation ID

🔴 ALL THREE ARE PURE ASGI, NOT `BaseHTTPMiddleware`. THAT IS THE POINT.
------------------------------------------------------------------------
`BaseHTTPMiddleware` runs the downstream app inside an anyio task group and
re-emits the response through a memory stream. When a client goes away
mid-response, that machinery can emit a final empty body chunk for a
response whose `Content-Length` was already on the wire, and uvicorn kills
the connection with:

    RuntimeError: Response content shorter than Content-Length

The client sees a reset, and anything in front of it (CloudFlare) turns
that into a **502**. Nothing is logged as an error by the app itself — the
response looked fine right up to the point where the body did not arrive.

Found in production 2026-08-25: `erp.noctusai.com` was serving Bad Gateway
to a browser while every health check passed and the container reported
healthy. 260 occurrences in six hours. It hit erp and no other product
because erp is the only one shipping a service worker — its prefetch and
abort traffic is what produces the mid-response disconnects. Every other
product had the same latent bug and simply no traffic shaped to trigger it.

Pure ASGI middleware wraps `send`/`receive` and never re-frames the
response, so the whole class of bug is gone rather than made rarer. The
cost is that these classes cannot *replace* a response after the app has
started sending one — which is not a real loss, since headers already on
the wire cannot be recalled anyway. `MaxBodySizeMiddleware` tracks that
explicitly (`started`) instead of pretending otherwise.

Keep them pure ASGI. Reaching for `BaseHTTPMiddleware` because `dispatch`
is more convenient re-opens a 502 nobody will connect back to this file.
"""
from __future__ import annotations

import time
import uuid
import logging
from typing import Mapping, Optional

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders

DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB

# `correlation_id_var` and `get_correlation_id` live in the dep-free
# `primitives._correlation` module so logging_config can use them without
# pulling in fastapi/starlette. Re-exported here for backward compatibility.
from noctusai_lib.primitives._correlation import correlation_id_var, get_correlation_id

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware:
    """
    Middleware that generates or extracts correlation IDs for request tracking.

    - Checks for X-Correlation-ID or X-Request-ID header
    - Generates a new UUID if not present
    - Adds correlation ID to response headers
    - Stores in context variable for use throughout request lifecycle

    Pure ASGI — see the module docstring for why that is not optional.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        correlation_id = (
            headers.get("x-correlation-id")
            or headers.get("x-request-id")
            or str(uuid.uuid4())
        )

        token = correlation_id_var.set(correlation_id)

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Correlation-ID"] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Reset in `finally`, not after the await, so a handler that
            # raises cannot leak this request's id into the next one served
            # on the same task.
            correlation_id_var.reset(token)


class RequestLoggingMiddleware:
    """
    Middleware that logs request/response details with timing.

    Logs:
    - Request: method, path, client IP, query params
    - Response: status code, duration
    - Slow requests (> 1s) are logged at WARNING level

    Timing is measured to the response START (first byte), which is what
    the previous `BaseHTTPMiddleware` implementation measured too — its
    `call_next` returned once the response began, not once the body
    finished. Streaming a large file therefore reports the time to begin
    streaming, not the transfer time, and always did.

    Pure ASGI — see the module docstring for why that is not optional.
    """

    SLOW_REQUEST_THRESHOLD_MS = 1000  # 1 second

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        correlation_id = get_correlation_id()

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        method = scope.get("method", "")
        path = scope.get("path", "")
        query_params = scope.get("query_string", b"").decode("latin-1")

        logger.info(
            "Request started",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "query_params": query_params,
            }
        )

        logged = False

        async def send_wrapper(message) -> None:
            nonlocal logged
            if message["type"] == "http.response.start" and not logged:
                logged = True
                duration_ms = (time.perf_counter() - start_time) * 1000
                status_code = message["status"]

                # Determine log level based on response status and duration
                log_level = logging.INFO
                if status_code >= 500:
                    log_level = logging.ERROR
                elif status_code >= 400:
                    log_level = logging.WARNING
                elif duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
                    log_level = logging.WARNING

                logger.log(
                    log_level,
                    "Request completed",
                    extra={
                        "correlation_id": correlation_id,
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": round(duration_ms, 2),
                        "slow_request": duration_ms > self.SLOW_REQUEST_THRESHOLD_MS,
                    }
                )

                # Add timing header
                MutableHeaders(scope=message)["X-Response-Time-Ms"] = str(
                    round(duration_ms, 2)
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Request failed with exception",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                }
            )
            raise


def _split_path_segments(path: str) -> tuple[str, ...]:
    """Split a URL path into its non-empty segments.

    `"/api/clientes/*/documentos"` -> `("api", "clientes", "*", "documentos")`.
    Leading/trailing slashes and any accidental double-slash collapse to
    nothing, matching how `request.url.path` and a hand-written override
    key are both naturally written with a leading `/`.
    """
    return tuple(s for s in path.split("/") if s)


def _pattern_matches(pattern_segments: tuple[str, ...], path_segments: tuple[str, ...]) -> bool:
    """Exact-shape match: same segment COUNT, every non-`*` segment
    equal literally, `*` matches any single segment (never zero, never
    more than one — so a pattern never accidentally swallows a deeper or
    shallower route)."""
    if len(pattern_segments) != len(path_segments):
        return False
    return all(p == "*" or p == s for p, s in zip(pattern_segments, path_segments))


class MaxBodySizeMiddleware:
    """Reject requests whose body exceeds a per-route cap with 413 before
    any handler runs.

    Two checks, cheapest-first:

    1. **`Content-Length` header.** If the client declared more than the
       cap, reject immediately — no body buffering, no handler invocation.
    2. **Streaming counter.** For chunked / unset-Content-Length requests,
       count bytes as they arrive and reject as soon as the cap trips.
       Stops the attack lane where an unbounded stream forces full
       buffering before HMAC verification fires.

    The middleware does NOT rewrite the request body; it just bounds
    incoming bytes. Handlers / dependencies that read `request.body()`
    behave normally below the cap.

    **Per-path overrides.** `max_bytes` is the app-wide default (right for
    webhooks — the flat cap exists to stop an unbounded stream forcing
    full buffering before HMAC verification). A route that legitimately
    receives larger payloads (file/photo uploads) needs a bigger cap
    *without* weakening the default everywhere else. Pass
    `path_overrides={"<key>": <max-bytes>, ...}` with two key shapes:

    - **Plain prefix** (no `*`) — e.g. `"/api/videos/upload"`. The
      LONGEST matching prefix of `request.url.path` wins among all plain
      entries.
    - **Single-segment-wildcard pattern** — e.g.
      `"/api/clientes/*/documentos"`, where each `*` matches exactly ONE
      path segment (never a partial segment, never zero-or-more). Needed
      when the route you're overriding has a path parameter (a UUID
      resource id, etc.) BEFORE the segment you actually care about — a
      plain prefix can't express that without either stopping short (too
      broad — e.g. `"/api/clientes"` would also raise the cap on every
      JSON clientes route) or being unwritable (the id is dynamic, you
      can't enumerate it). A pattern match requires an EXACT segment
      count AND exact literal match on every non-`*` segment, so it
      can't accidentally widen to unrelated routes the way a truncated
      prefix would.

    Pattern entries are checked FIRST (an exact-shape match is, by
    construction, always at least as specific as any prefix); if none
    match, the longest-matching plain prefix is used; if neither
    matches, the path falls back to `max_bytes`. All three lookup paths
    (pattern / prefix / default) feed the SAME resolved limit into both
    checks below — an override that only patched one of them would
    depend on whether the client happened to send a Content-Length,
    which is worse than no override at all.

    Override the cap per product via `settings.max_body_bytes` /
    `settings.max_body_path_overrides` (see `configure_app` /
    `create_product_app`), or pass `max_bytes` / `path_overrides` directly
    when wiring.
    """

    def __init__(
        self,
        app,
        *,
        max_bytes: int = DEFAULT_MAX_BODY_BYTES,
        path_overrides: Optional[Mapping[str, int]] = None,
    ):
        self.app = app
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes
        # Plain-prefix overrides (unchanged, backward-compatible shape).
        self.path_overrides: dict[str, int] = {}
        # Single-segment-wildcard pattern overrides — parsed once at
        # construction into (segments, limit, original_key) tuples so
        # `_limit_for` never re-splits on every request.
        self._path_patterns: list[tuple[tuple[str, ...], int, str]] = []
        for key, limit in (path_overrides or {}).items():
            if limit <= 0:
                raise ValueError(
                    f"path_overrides[{key!r}] must be positive, got {limit}"
                )
            if "*" in key:
                self._path_patterns.append((_split_path_segments(key), limit, key))
            else:
                self.path_overrides[key] = limit

    def _limit_for(self, path: str) -> int:
        """Resolve the effective cap for `path`: exact wildcard-pattern
        match first (most specific by construction), else the
        longest-matching plain prefix, else the app-wide default."""
        if self._path_patterns:
            segments = _split_path_segments(path)
            for pattern_segments, limit, _key in self._path_patterns:
                if _pattern_matches(pattern_segments, segments):
                    return limit

        best_len = -1
        best_limit = self.max_bytes
        for prefix, limit in self.path_overrides.items():
            if len(prefix) > best_len and path.startswith(prefix):
                best_len = len(prefix)
                best_limit = limit
        return best_limit

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope.get("path", ""))
        headers = Headers(scope=scope)

        cl = headers.get("content-length")
        if cl is not None:
            try:
                declared = int(cl)
            except ValueError:
                await JSONResponse(
                    status_code=400,
                    content={"detail": "invalid Content-Length header"},
                )(scope, receive, send)
                return
            if declared > limit:
                await _payload_too_large_response(limit, declared)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        # Streaming counter — only matters for chunked / unset-Content-Length.
        counter = {"n": 0}

        async def counting_receive():
            msg = await receive()
            if msg["type"] == "http.request":
                counter["n"] += len(msg.get("body", b"") or b"")
                if counter["n"] > limit:
                    return {"type": "http.disconnect"}
            return msg

        # Once `http.response.start` has gone downstream the status line is
        # on the wire and no 413 can replace it. The previous
        # `BaseHTTPMiddleware` version could swap a fully-buffered response
        # object; pure ASGI cannot, and pretending otherwise would emit a
        # second response for one request. In practice the cap trips while
        # the handler is still awaiting `request.body()`, so nothing has
        # been sent and the 413 lands normally.
        started = False

        async def send_wrapper(message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, send_wrapper)
        except Exception:
            # A tripped counter disconnects the ASGI receive channel, which
            # Starlette surfaces deep inside body parsing as
            # `ClientDisconnect` — deliberately NOT routed through any
            # registered exception handler (Starlette's own policy: no
            # point sending a response to a client that already hung up).
            # We're still attached from out here though, so turn a
            # genuinely-tripped cap into a clean 413 instead of letting it
            # surface as an opaque, unhandled 500. Anything that raised
            # WITHOUT tripping the cap is an unrelated downstream error
            # and must propagate untouched.
            if counter["n"] > limit and not started:
                await _payload_too_large_response(limit, counter["n"])(
                    scope, receive, send
                )
                return
            raise

        # Cap tripped but the handler never read the body (so nothing
        # downstream ever saw the disconnect) — still trips.
        if counter["n"] > limit and not started:
            await _payload_too_large_response(limit, counter["n"])(scope, receive, send)


def _payload_too_large_response(limit: int, observed: Optional[int] = None) -> JSONResponse:
    detail = {
        "error": "request body too large",
        "limit_bytes": limit,
    }
    if observed is not None:
        detail["observed_bytes"] = observed
    return JSONResponse(status_code=413, content=detail)
