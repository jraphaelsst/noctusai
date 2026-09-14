"""Realtime bus wiring for the Agentes SSE stream (contract §E.3,
``projects/julia-agents-academia-CONTRACT.md``).

One process-wide :class:`~noctusai_lib.realtime.RealtimeBus` (Redis-backed
in prod, in-memory ``FakeRealtimeBus`` under dev/test — the seed's
``get_realtime_bus`` factory), scoped per-conversation as
``agents:julia:conv:<conversation_id>`` (contract §E.3 "Scope"). This
module owns:

  - ``get_bus()`` — the singleton accessor.
  - ``conversation_scope(conversation_id)`` — the scope-string builder,
    the single point of truth so the SSE router's ``scope_resolver`` and
    the turn-loop's publish calls can never drift apart on the format.
  - ``publish_event(...)`` — a thin wrapper naming exactly the E.3 event
    set (``EVENTS``), so a typo'd event name fails loudly at call time
    instead of silently publishing an event no ``events=[...]`` allowlist
    on the frontend's ``useRealtimeStream`` will ever render.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from noctusai_lib.realtime import RealtimeBus, get_realtime_bus

from app.config import settings

logger = logging.getLogger(__name__)

#: Contract §E.3 — the exhaustive event-name set. `message.ack` and
#: `chat.upsert` are explicitly deprecated (WhatsApp-only / renamed) and
#: therefore NOT in this set — publishing either is a bug, not an omission.
EVENTS = frozenset(
    {
        "message.new",
        "message.delta",
        "tool.started",
        "tool.finished",
        "approval.requested",
        "approval.resolved",
        "session.status",
        "conversation.upsert",
    }
)

_bus: RealtimeBus | None = None


def get_bus() -> RealtimeBus:
    """Process-wide singleton — mirrors the seed's own docstring recipe
    (`bus = get_realtime_bus(settings.redis_url)` at module scope), built
    lazily so importing this module never requires a live Redis URL."""
    global _bus
    if _bus is None:
        _bus = get_realtime_bus(getattr(settings, "redis_url", None))
    return _bus


def conversation_scope(conversation_id: UUID | str) -> str:
    """Contract §E.3 "Scope": ``agents:julia:conv:<conversation_id>``."""
    return f"agents:julia:conv:{conversation_id}"


async def publish_event(
    conversation_id: UUID | str, event: str, payload: dict[str, Any]
) -> str | None:
    """Publish one E.3 event onto the conversation's scope. Raises
    ``ValueError`` for any event name outside :data:`EVENTS` — a typo here
    is a silent-drop-from-the-frontend bug, never a warning.

    The bus write itself is **best-effort** — the persisted DB row is the
    source of truth (contract §E.9: the runtime never writes the DB;
    persistence happens BEFORE the publish call at every call site in
    ``conversations_router.py``), and SSE is a supplementary live-update
    channel, not load-bearing for correctness. A transient bus outage
    (Redis unreachable) must never fail the HTTP response or abort the
    turn loop — same "best-effort, logged loudly" posture as
    ``noctusai_lib.api.auth.session.audit.SupabaseApiTokenAuditWriter`` and
    the token resolver's ``last_used_at`` bump. Returns ``None`` on
    failure instead of the assigned event id.
    """
    if event not in EVENTS:
        raise ValueError(f"publish_event: unknown contract §E.3 event {event!r}")
    try:
        return await get_bus().publish(conversation_scope(conversation_id), event, payload)
    except Exception:
        logger.warning(
            "agents.realtime.publish_failed conversation_id=%s event=%s",
            conversation_id,
            event,
            exc_info=True,
        )
        return None


__all__ = ["EVENTS", "conversation_scope", "get_bus", "publish_event"]
