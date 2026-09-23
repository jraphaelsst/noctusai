"""``noctusai_lib.api.audit`` — the seed's request-history audit trail.

Owner directive 2026-09-23: "record history of actions for everything."
This package is the S2 (seed) slice: an :class:`AuditMiddleware` that
records every mutating (``POST``/``PUT``/``PATCH``/``DELETE``) request
through an :class:`AuditSink`, gated behind
``settings.audit_trail_enabled`` (default ``False`` — see
``noctusai_seed.config.ProductSettings``).

Wiring (``noctusai_seed.app.create_product_app`` +
``noctusai_lib.api.app_factory.configure_app``):

1. ``create_product_app`` builds a sink via :func:`make_audit_sink`
   (Real when ``audit_trail_enabled`` and a DB is wired, Fake
   otherwise) and passes it to ``configure_app``.
2. ``configure_app`` mounts :class:`AuditMiddleware` next to
   ``RequestLoggingMiddleware`` — see that function's docstring for
   why the mount position (nested inside ``CorrelationIdMiddleware``)
   is load-bearing.
3. The seed auth dependencies (``noctusai_lib.api.auth
   .make_get_current_user_org`` and
   ``noctusai_seed.dependencies.ProductDependencies.get_current_user``)
   stash the resolved identity on ``request.state.audit_actor`` — the
   ONLY channel this middleware (which runs outside FastAPI's
   dependency graph) has to learn who the caller was.
4. ``create_product_app``'s ``lifespan`` calls ``sink.drain()`` on
   shutdown so no buffered entry is lost on a clean stop.

Consumers needing an entry's shape import :class:`AuditEntry` /
:class:`AuditActor` from ``.types``; a store that wants to plug into
the sink infrastructure directly (rather than going through the
middleware) imports :func:`make_audit_sink` here.
"""
from __future__ import annotations

from .detect import client_hint_from_ua, detect_actor_kind
from .middleware import AuditMiddleware
from .sink import (
    AuditSink,
    FakeAuditSink,
    RealAuditSink,
    log_overflow_or_failure,
    make_audit_sink,
    overflow_or_failure_count,
)
from .types import ActorKind, AuditActor, AuditEntry

__all__ = [
    "ActorKind",
    "AuditActor",
    "AuditEntry",
    "AuditMiddleware",
    "AuditSink",
    "FakeAuditSink",
    "RealAuditSink",
    "client_hint_from_ua",
    "detect_actor_kind",
    "log_overflow_or_failure",
    "make_audit_sink",
    "overflow_or_failure_count",
]
