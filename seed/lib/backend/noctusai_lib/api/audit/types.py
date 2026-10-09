"""Shared value types for the audit-trail seed module.

Kept dependency-free (no ``fastapi``/``starlette`` imports) so
``noctusai_lib.domain.action_log`` and other non-ASGI callers can build
an :class:`AuditEntry` without pulling in the web-framework layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Optional

#: Who/what issued the request. Detected by
#: :func:`noctusai_lib.api.audit.detect.detect_actor_kind` from the
#: ``X-Noctus-Client`` header + User-Agent — independent of whether an
#: *identity* (user/org) resolved at all, so a headless-browser hitting
#: an unauthenticated route still records as ``"agent"``, not ``"user"``.
ActorKind = Literal["user", "agent", "service"]


@dataclass(frozen=True)
class AuditActor:
    """The identity resolved by the seed's auth dependencies, stashed on
    ``request.state.audit_actor``. All fields are optional because the
    two call sites that populate it resolve different amounts of
    identity (``ProductDependencies.get_current_user`` only ever knows
    ``user_id``; ``make_get_current_user_org`` additionally resolves
    ``org_id``). A request that never reaches an auth dependency (a
    public route) has no actor at all — :class:`AuditMiddleware` reads
    ``None`` in that case, never a synthesized placeholder.
    """

    user_id: Optional[str] = None
    org_id: Optional[str] = None
    role: Optional[str] = None
    #: Org picker (platform staff acting in a customer org): ``org_id`` is the TARGET org
    #: (the client sees the DATA CHANGES staff make in their org), ``acting_org_id`` the
    #: staff member's HOME org and ``act_as_session_id`` the ``platform_org_selections.id``.
    #: Both ``None`` for every ordinary request. Selection start/end/swap and reads are
    #: logged with ``org_id=None`` (platform-only) -- the client never sees staff browse.
    acting_org_id: Optional[str] = None
    act_as_session_id: Optional[str] = None


@dataclass(frozen=True)
class AuditEntry:
    """One recorded mutating request — the payload
    :class:`~noctusai_lib.api.audit.sink.AuditSink` implementations
    persist.

    ``product_slug`` is the catalog slug (``"social-wiring"``), NEVER
    the human-readable display name (``"Social Wiring"``,
    ``create_product_app(name=...)``) — matches
    ``public.audit_logs.product_slug`` (migration 053) verbatim, so a
    query never has to normalize both shapes.
    """

    product_slug: str
    method: str
    route_template: str
    path_params: Mapping[str, Any]
    status: int
    actor_kind: ActorKind
    client_hint: str
    correlation_id: Optional[str] = None
    duration_ms: Optional[float] = None
    actor: AuditActor = field(default_factory=AuditActor)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["ActorKind", "AuditActor", "AuditEntry"]
