"""``AuditMiddleware`` — records every mutating request through an
:class:`~noctusai_lib.api.audit.sink.AuditSink`.

Pure ASGI, NOT ``BaseHTTPMiddleware`` — see
``noctusai_lib.api.middleware``'s module docstring for the 2026-08-25
mid-response-disconnect incident that rule exists to prevent. Same
shape as ``noctusai_lib.api.auth.session.audit_middleware
.ApiTokenAuditMiddleware``: read the response status from a
``send_wrapper`` closure, read the resolved caller from
``scope["state"]`` (the SAME dict object threaded through the whole
ASGI chain — a FastAPI dependency's ``request.state.audit_actor = ...``
is visible here after the downstream app returns), never re-frame the
response.

**Mount position matters.** Must be added to ``app.add_middleware(...)``
BEFORE ``CorrelationIdMiddleware`` (i.e. stay NESTED inside it — see
``noctusai_lib.api.app_factory.configure_app``) so ``get_correlation_id()``
still resolves when this middleware's ``send_wrapper`` fires: the
correlation-id ``ContextVar`` is reset in `CorrelationIdMiddleware`'s
own ``finally`` block once ITS ``__call__`` returns, which only happens
AFTER every middleware nested inside it (this one) has already
returned.
"""
from __future__ import annotations

import time
from typing import Optional

from starlette.datastructures import Headers

from noctusai_lib.primitives._correlation import get_correlation_id

from .detect import client_hint_from_ua, detect_actor_kind
from .sink import AuditSink
from .types import AuditActor, AuditEntry

#: The only methods worth recording — a GET/HEAD/OPTIONS never mutates
#: state, so auditing it would be pure noise (and pure cost) at
#: platform scale.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuditMiddleware:
    """Fires ``sink.record(...)`` for every mutating request that
    reached a matched route. Pure ASGI — see module docstring.

    Args:
        app: The downstream ASGI app.
        sink: Where a resolved entry goes.
        product_slug: The product's CATALOG slug (``"social-wiring"``),
            never the display name — becomes
            :attr:`AuditEntry.product_slug`, matching
            ``public.audit_logs.product_slug`` (migration 053)
            verbatim.
        enabled: When ``False`` the middleware is a straight
            passthrough — no header parsing, no clock read, no sink
            call. Wired to ``settings.audit_trail_enabled`` by
            ``noctusai_lib.api.app_factory.configure_app`` so a product
            that hasn't flipped the flag pays zero overhead per
            request, not just "no DB write."
    """

    def __init__(
        self,
        app,
        *,
        sink: AuditSink,
        product_slug: str,
        enabled: bool = True,
    ) -> None:
        self.app = app
        self._sink = sink
        self._product_slug = product_slug
        self._enabled = enabled

    async def __call__(self, scope, receive, send) -> None:
        if not self._enabled or scope["type"] != "http" or scope.get("method") not in _MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # Downstream (routing + dependency resolution + handler) has
        # fully completed — `scope["route"]` (set by Starlette's
        # router) and `scope["state"]["audit_actor"]` (set by a seed
        # auth dependency, if one ran) are both readable now.
        route = scope.get("route")
        if route is None:
            # No route matched (404) — nothing meaningful to attribute
            # the mutation to. Matches ApiTokenAuditMiddleware's same
            # "silently skip, never an error" posture for an
            # unresolvable request.
            return

        status = status_holder.get("status")
        if status is None:
            # Connection dropped before any response was sent.
            return

        headers = Headers(scope=scope)
        user_agent = headers.get("user-agent")
        x_noctus_client = headers.get("x-noctus-client")

        state = scope.get("state") or {}
        actor: Optional[AuditActor] = state.get("audit_actor")

        entry = AuditEntry(
            product_slug=self._product_slug,
            method=scope.get("method", ""),
            route_template=getattr(route, "path", str(route)),
            path_params=dict(scope.get("path_params") or {}),
            status=status,
            actor_kind=detect_actor_kind(x_noctus_client=x_noctus_client, user_agent=user_agent),
            client_hint=client_hint_from_ua(user_agent),
            correlation_id=get_correlation_id(),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            actor=actor if actor is not None else AuditActor(),
        )
        await self._sink.record(entry)


__all__ = ["AuditMiddleware"]
