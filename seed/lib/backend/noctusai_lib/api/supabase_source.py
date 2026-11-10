"""Pure-ASGI middleware: every Supabase call made while serving a request is source ``http`` (user traffic).

Why explicit: the Supabase request breaker's contextvar default is ``unattributed`` (budgeted + trippable like a
background source), so a lifespan ``create_task`` loop or a bare ``Thread`` outside the Worker/scheduler can be stopped.
``http`` is the one source that is NEVER held (it only alerts), so it must be set deliberately, per request, here.
Threadpool handlers and ``to_thread`` copy the context, so they inherit it.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

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
