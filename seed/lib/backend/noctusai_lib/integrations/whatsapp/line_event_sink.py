"""Persistent :class:`LineEventSink` -- the append-only ``<schema>.whatsapp_line_events`` table (EOA).

``line_policy`` declares the seam (``LineEventSink`` + ``set_default_line_event_sink``) and refuses to register a
``send: disabled`` line while the sink is in-memory (a refusal nobody can audit later must not be what protects a personal
number). This module is the persistent half: ``make_line_event_sink(...)`` returns the Real sink (one INSERT per event
through the product's service-role client) or the Fake (tests); the product calls
``set_default_line_event_sink(sink)`` BEFORE ``register_line_policy``.

* INSERT-ONLY: the table has no UPDATE/DELETE grant and a trigger refuses both (``whatsapp_line_events_table_sql``).
* SERVICE ROLE ONLY, ``tier:service`` (platform telemetry; never a browser surface).
* LOUD: a failed insert is logged at CRITICAL and raised as :class:`LineEventPersistenceError` -- the write that was being
  refused is still not performed (the exception propagates out of the guard), and the failure is never swallowed.
* Request path: one small INSERT on the REFUSAL path only (rare by construction), through the client's own timeout.

Payload carries no message content and no phone: ``line`` is the host label, ``op`` a redacted endpoint.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from noctusai_lib.integrations.whatsapp.line_policy import InMemoryLineEventSink, LineEvent, LineEventSink

logger = logging.getLogger(__name__)

LINE_EVENTS_TABLE = "whatsapp_line_events"


class LineEventPersistenceError(RuntimeError):
    """A line event could not be persisted. Raised, never swallowed: the audit trail is part of the safety property."""


def line_event_row(event: LineEvent) -> dict[str, Any]:
    return {
        "event": event.event,
        "line": event.line,
        "op": event.op,
        "reason": event.reason,
        "policy": dict(event.policy),
        "occurred_at": event.at,
    }


class FakeLineEventSink(InMemoryLineEventSink):
    """Test double with the Real sink's contract: rows shaped exactly as the table, ``fail_with`` to simulate an outage.

    Subclasses the in-memory sink only for its ``events`` deque; it is NOT treated as in-memory by the registry check
    (see ``is_persistent_sink``), so tests can exercise the boot path the product takes in deploy."""

    persistent = True

    def __init__(self, fail_with: Optional[Exception] = None):
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self.fail_with = fail_with

    def record(self, event: LineEvent) -> None:
        if self.fail_with is not None:
            raise LineEventPersistenceError(f"line event {event.event!r} not persisted") from self.fail_with
        self.rows.append(line_event_row(event))
        super().record(event)


class SupabaseLineEventSink:
    """Real sink: one INSERT into ``<schema>.whatsapp_line_events`` with the product's service-role client."""

    persistent = True

    def __init__(self, client_factory: Callable[[], Any], *, schema: str):
        self._client_factory = client_factory
        self._schema = schema

    def record(self, event: LineEvent) -> None:
        try:
            self._client_factory().schema(self._schema).table(LINE_EVENTS_TABLE).insert(line_event_row(event)).execute()
        except Exception as exc:  # noqa: BLE001 -- re-raised typed below; never swallowed
            logger.critical(
                "line event NOT persisted event=%s line=%s op=%s reason=%s err=%s",
                event.event, event.line, event.op, event.reason, type(exc).__name__,
            )
            raise LineEventPersistenceError(f"line event {event.event!r} not persisted: {type(exc).__name__}") from exc
        logger.error("%s line=%s op=%s reason=%s", event.event, event.line, event.op, event.reason)


def make_line_event_sink(
    *, schema: str, client_factory: Optional[Callable[[], Any]] = None, use_fake: bool = False
) -> LineEventSink:
    """Factory: Fake under ``use_fake`` (tests), else Real. No client factory in a non-fake build is a declared refusal."""
    if use_fake:
        return FakeLineEventSink()
    if client_factory is None:
        raise ValueError("make_line_event_sink: a Real sink needs client_factory (the product's service-role client)")
    return SupabaseLineEventSink(client_factory, schema=schema)


__all__ = [
    "FakeLineEventSink", "LINE_EVENTS_TABLE", "LineEventPersistenceError", "SupabaseLineEventSink",
    "line_event_row", "make_line_event_sink",
]
