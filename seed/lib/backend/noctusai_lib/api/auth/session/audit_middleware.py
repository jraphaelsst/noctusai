"""``ApiTokenAuditMiddleware`` — wires `ApiTokenAuditWriter` (`audit.py`)
into a live request/response cycle.

Contract §B.0: "every resolved product-token call writes
``api_token_audit(api_token_id, org_id, method, path, status)``,
best-effort and logged loudly on failure." The writer itself
(``audit.py``) has shipped since Wave 1/SEED-1 with NO call site — this
is that call site (N=2 consumers per this module's own promotion note:
academia now, the social-wiring bridge next).

Pure ASGI, NOT ``BaseHTTPMiddleware`` — see
``noctusai_lib.api.middleware``'s module docstring for the 2026-08-25
mid-response-disconnect incident that rule exists to prevent. This
middleware never re-frames or delays the response; it only reads the
already-captured status code and fires the audit write AFTER the
downstream ASGI app has fully returned (i.e. after the response is
already on the wire).

**How it learns the caller.** `ApiTokenAuditMiddleware` runs OUTSIDE
FastAPI's dependency graph, so it cannot see the `AuthContext` a route's
own `Depends(get_auth_context)` resolves. `session.dep.make_get_auth_context`
stashes the resolved context on ``request.state.auth_context`` on every
successful resolution (SEED-1 addition, purely additive) — since ASGI
`scope["state"]` is the SAME dict object threaded through the whole
middleware chain, this middleware reads it back after the downstream
call returns. A request that never reaches a `get_auth_context`
dependency (no route matched, or the route has no auth dep at all)
simply has no state to read — silently skipped, never an error.
"""
from __future__ import annotations

import logging

from noctusai_lib.api.auth.session.audit import ApiTokenAuditWriter
from noctusai_lib.api.auth.session.types import AuthContext

logger = logging.getLogger(__name__)


class ApiTokenAuditMiddleware:
    """Fires `audit_writer.record(...)` for every resolved
    `caller_kind == "product"` request. Pure ASGI — see module
    docstring."""

    def __init__(self, app, *, audit_writer: ApiTokenAuditWriter) -> None:
        self.app = app
        self._audit_writer = audit_writer

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_holder: dict[str, int] = {}

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # Downstream (dependency resolution + route handler + response)
        # has fully completed by this point — `scope["state"]` (the same
        # dict object `Request.state` writes through) carries whatever
        # `get_auth_context` stashed, if anything.
        state = scope.get("state") or {}
        ctx: AuthContext | None = state.get("auth_context")
        if ctx is None or ctx.caller_kind != "product" or ctx.api_token_id is None:
            return

        status = status_holder.get("status")
        if status is None:
            # No response was ever started (e.g. the connection dropped
            # before headers went out) — nothing meaningful to audit.
            return

        try:
            await self._audit_writer.record(
                api_token_id=ctx.api_token_id,
                org_id=ctx.org_id,
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                status=status,
            )
        except Exception:
            # Best-effort per contract §B.0 — the writer itself already
            # swallows its own IO failures (see `audit.py`'s
            # `SupabaseApiTokenAuditWriter.record`); this is defence in
            # depth against a writer implementation that doesn't.
            logger.exception(
                "api_token_audit_middleware_failed method=%s path=%s api_token_id=%s",
                scope.get("method", ""),
                scope.get("path", ""),
                ctx.api_token_id,
            )


__all__ = ["ApiTokenAuditMiddleware"]
