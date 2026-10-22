"""Request-scoped memo -- compute a per-request answer ONCE, never across requests.

The effective-org resolution (memberships / blocks / selection / licence: several sequential
PostgREST round trips) is asked by the base auth dependency, the licence gate AND the organ auth
wrapper for the SAME request. This module gives them one fresh ``dict`` per HTTP request, held in
a ``ContextVar`` set by :class:`RequestMemoMiddleware` (registered by ``create_product_app``).

Safety contract (authz depends on it):

* the dict is created per request and dropped when the request ends -- never shared across
  requests, users or tokens; callers MUST key on everything that changes the answer;
* worker threads see it: Starlette/anyio copy the context, and the dict object is shared;
* OUTSIDE a request (jobs, tests without the middleware) :func:`request_memo` is ``None`` and
  callers behave exactly as without a memo;
* callers memoize SUCCESSFUL results only -- an exception is never stored (fail closed as before).

Pure ASGI, like every seed middleware (``BaseHTTPMiddleware`` would run the app in another task).

KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import contextvars
from typing import Any, Callable, Optional

_MEMO: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("request_memo", default=None)

_MISS = object()


def request_memo() -> Optional[dict]:
    """The current request's memo dict, or ``None`` outside a request."""
    return _MEMO.get()


def memoize_for_request(key: tuple, compute: Callable[[], Any]) -> Any:
    """``compute()`` once per ``key`` within the current request; plain ``compute()`` outside one.

    An exception from ``compute`` propagates and is NOT stored."""
    memo = _MEMO.get()
    if memo is None:
        return compute()
    hit = memo.get(key, _MISS)
    if hit is not _MISS:
        return hit
    value = compute()
    memo[key] = value
    return value


def forget_for_request(kind: str) -> None:
    """Drop every memoized entry whose key starts with ``kind`` -- called by a WRITE that changes
    the answer (e.g. an org-selection set/end), so a later read in the same request recomputes."""
    memo = _MEMO.get()
    if memo is None:
        return
    for key in [k for k in memo if k and k[0] == kind]:
        memo.pop(key, None)


class RequestMemoMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _MEMO.set({})
        try:
            await self.app(scope, receive, send)
        finally:
            _MEMO.reset(token)


__all__ = ["RequestMemoMiddleware", "forget_for_request", "memoize_for_request", "request_memo"]
