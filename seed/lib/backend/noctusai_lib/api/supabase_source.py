"""Pure-ASGI middleware: every Supabase call made while serving a request is source ``http`` (user traffic).

Why explicit: the Supabase request breaker's contextvar default is ``unattributed`` (budgeted + trippable like a
background source), so a lifespan ``create_task`` loop or a bare ``Thread`` outside the Worker/scheduler can be stopped.
``http`` is the one source that is NEVER held (it only alerts), so it must be set deliberately, per request, here.
Threadpool handlers and ``to_thread`` copy the context, so they inherit it.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

from fastapi import FastAPI

from noctusai_lib.primitives.supabase_breaker import HTTP_SOURCE, source_scope


class SupabaseSourceMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        with source_scope(HTTP_SOURCE):
            await self.app(scope, receive, send)


class SeedFastAPI(FastAPI):
    """``FastAPI`` whose ASGI stack is ALWAYS wrapped by :class:`SupabaseSourceMiddleware` at the outermost layer, built
    lazily at the first request — so middleware a product adds AFTER ``create_product_app`` (token audit, rate limits, ...)
    still runs inside the `http` source instead of `unattributed`."""

    def build_middleware_stack(self):
        return SupabaseSourceMiddleware(super().build_middleware_stack())
