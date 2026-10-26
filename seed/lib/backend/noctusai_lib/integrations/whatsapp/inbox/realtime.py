"""Inbox <-> realtime bus wiring: the event vocabulary, the per-connection
scope key, a never-breaks-ingest publisher, and a fake-or-refuse factory.

The seed's :mod:`noctusai_lib.realtime` is provider-neutral (opaque scopes);
this module is the single place that maps the WhatsApp inbox onto it, so the
webhook (write side) and the SSE route (stream side) never re-derive the
scope key or re-spell an event name. The frontend reducer switches on these
exact strings — a typo on either side fails silently, so they are constants.

In-process vs Redis: the default bus is the in-process ``FakeRealtimeBus``
(full semantic parity, but events do NOT cross process boundaries — with >1
uvicorn worker a publish in worker A is invisible to a subscriber in worker
B). A production process therefore has to choose explicitly:
``redis_client`` / ``redis_url`` for the Redis stream bus, or
``allow_in_process=True`` as a declared single-worker decision. Neither ->
:class:`InboxRealtimeNotConfigured` (never a silent Fake).
"""
from __future__ import annotations

import logging
from typing import Any, Final, Optional
from uuid import UUID

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from noctusai_lib.realtime import FakeRealtimeBus, RealtimeBus, get_realtime_bus

logger = logging.getLogger(__name__)

EVENT_MESSAGE_NEW: Final = "message.new"
EVENT_MESSAGE_ACK: Final = "message.ack"
EVENT_CHAT_UPSERT: Final = "chat.upsert"
EVENT_CHAT_READ: Final = "chat.read"
EVENT_SESSION_STATUS: Final = "session.status"

INBOX_EVENTS: Final = frozenset(
    {EVENT_MESSAGE_NEW, EVENT_MESSAGE_ACK, EVENT_CHAT_UPSERT, EVENT_CHAT_READ, EVENT_SESSION_STATUS}
)


class InboxRealtimeNotConfigured(RuntimeError, IntegrationNotConfigured):
    """Neither Redis nor an explicit single-process opt-in was supplied."""


def inbox_scope(connection_id: UUID | str) -> str:
    """Bus scope of one WhatsApp line (the smallest unit a viewer subscribes
    to and the authorization boundary every other op already uses)."""
    return f"wa:conn:{connection_id}"


class InboxRealtime:
    """Thin publisher over a :class:`RealtimeBus`."""

    def __init__(self, bus: RealtimeBus, *, in_process: bool) -> None:
        self.bus = bus
        self.in_process = in_process

    async def publish(self, connection_id: UUID | str, event: str, payload: dict[str, Any]) -> Optional[str]:
        """Publish one event; a bus failure NEVER fails the (already durable)
        write — it is logged with the event name and returns ``None`` so the
        caller can tell "published" from "degraded"."""
        if event not in INBOX_EVENTS:
            raise ValueError(f"unknown inbox event {event!r}; expected one of {sorted(INBOX_EVENTS)}")
        try:
            return await self.bus.publish(inbox_scope(connection_id), event, payload)
        except Exception:  # noqa: BLE001 - degrade realtime, never fail the write
            logger.exception(
                "inbox realtime publish failed (connection=%s event=%s) - the DB write "
                "already succeeded; clients recover on reconnect/refetch",
                connection_id, event,
            )
            return None


def build_inbox_realtime(
    *,
    redis_client: Any = None,
    redis_url: Optional[str] = None,
    allow_in_process: bool = False,
) -> InboxRealtime:
    """Redis bus when a client/url is supplied; the in-process bus only under
    an explicit ``allow_in_process=True``; otherwise refuse."""
    def _refuse() -> InboxRealtime:
        raise InboxRealtimeNotConfigured(
            "WhatsApp inbox realtime has no Redis (redis_client/redis_url) and "
            "allow_in_process=False; pass allow_in_process=True ONLY for a single-worker deployment"
        )

    def _real() -> InboxRealtime:
        return InboxRealtime(get_realtime_bus(redis_url, redis_client=redis_client), in_process=False)

    if allow_in_process and redis_client is None and not redis_url:
        logger.warning(
            "WhatsApp inbox realtime running IN-PROCESS: events do not cross workers; "
            "with >1 worker SSE subscribers miss messages published by another worker"
        )
    return resolve_fake_or_refuse(
        configured=bool(redis_client is not None or redis_url),
        build_real=_real,
        build_fake=lambda: InboxRealtime(FakeRealtimeBus(), in_process=True),
        allow_fake=allow_in_process,
        unconfigured=_refuse,
    )
