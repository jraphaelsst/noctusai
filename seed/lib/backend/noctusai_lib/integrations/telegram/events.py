"""Append-only Telegram line events sink (``<schema>.telegram_line_events``), mirroring
``whatsapp/line_event_sink.py``: INSERT-only, service role only, LOUD on failure (raised, never swallowed).
Payloads carry no message content and no bot token: ``detail`` holds ids/counts/reason codes only.

NOC-REMEDIATE[telegram-events-to-transition-log]: when the platform transition-log organ lands, fold this
per-vendor event table into it (one event model, EOA) -- 2026-11-13.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol
from uuid import UUID

from .redact import redact

logger = logging.getLogger(__name__)

LINE_EVENTS_TABLE = "telegram_line_events"

#: Closed event vocabulary (intent-named).
EVENTS = (
    "telegram.line.connected", "telegram.line.token_rotated", "telegram.line.suspended", "telegram.line.resumed",
    "telegram.line.needs_reconnection", "telegram.line.deleted", "telegram.channel.bound",
    "telegram.channel.unbound", "telegram.webhook.set", "telegram.webhook.refused_foreign",
    "telegram.post.sent", "telegram.post.edited", "telegram.post.deleted", "telegram.post.failed",
    "telegram.post.rate_limited",
)


class LineEventPersistenceError(RuntimeError):
    """A line event could not be persisted. Raised, never swallowed."""


@dataclass(frozen=True)
class TelegramLineEvent:
    event: str
    line_id: UUID
    org_id: Optional[UUID] = None
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.event not in EVENTS:
            raise ValueError(f"unknown telegram line event {self.event!r}")


class TelegramLineEventSink(Protocol):
    def record(self, event: TelegramLineEvent) -> None: ...


def event_row(event: TelegramLineEvent) -> dict[str, Any]:
    return {
        "event": event.event, "line_id": str(event.line_id),
        "org_id": str(event.org_id) if event.org_id else None,
        "reason": event.reason, "detail": dict(event.detail), "occurred_at": event.at,
    }


class FakeTelegramLineEventSink:
    persistent = True

    def __init__(self, fail_with: Optional[Exception] = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self.fail_with = fail_with

    def record(self, event: TelegramLineEvent) -> None:
        if self.fail_with is not None:
            raise LineEventPersistenceError(f"telegram event {event.event!r} not persisted") from self.fail_with
        self.rows.append(event_row(event))


class SupabaseTelegramLineEventSink:
    persistent = True

    def __init__(self, client_factory: Callable[[], Any], *, schema: str) -> None:
        self._client_factory = client_factory
        self._schema = schema

    def record(self, event: TelegramLineEvent) -> None:
        try:
            self._client_factory().schema(self._schema).table(LINE_EVENTS_TABLE).insert(event_row(event)).execute()
        except Exception as exc:  # noqa: BLE001 -- re-raised typed below; never swallowed
            logger.critical("telegram event NOT persisted event=%s line=%s err=%s", event.event, event.line_id,
                            redact(type(exc).__name__))
            raise LineEventPersistenceError(f"telegram event {event.event!r} not persisted") from exc


def make_telegram_line_event_sink(
    *, schema: str, client_factory: Optional[Callable[[], Any]] = None, use_fake: bool = False,
) -> TelegramLineEventSink:
    if use_fake:
        return FakeTelegramLineEventSink()
    if client_factory is None:
        raise ValueError("make_telegram_line_event_sink: a Real sink needs client_factory (service-role client)")
    return SupabaseTelegramLineEventSink(client_factory, schema=schema)
