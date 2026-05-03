"""In-memory deterministic fake CalendarAdapter for dev + tests.

Ported verbatim from
`whatsapp-google-scheduling/app/services/calendar/fake_adapter.py`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 7.

Mirrors the Google Calendar v3 response shape so consumer code can
swap between real/fake without notice.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from noctusai_lib.integrations.google_calendar.mappers import (
    event_to_google_body,
    google_body_to_created_event,
    parse_google_datetime,
)
from noctusai_lib.integrations.google_calendar.types import CreatedEvent, EventInput


class FakeCalendarAdapter:
    """In-memory fake. Use it for local development and tests until
    a real service-account JSON or OAuth credential is configured."""

    def __init__(self, *, supports_attendees: bool = False) -> None:
        self._events: dict[str, dict[str, dict[str, Any]]] = {}
        self.supports_attendees = supports_attendees

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent:
        event_id = uuid.uuid4().hex
        body = event_to_google_body(event)
        body["id"] = event_id
        body["status"] = "confirmed"
        body["htmlLink"] = (
            f"https://calendar.google.com/calendar/event?eid={event_id}"
        )
        body["creator"] = {"email": "fake-calendar@noctusai.local"}
        body["organizer"] = {"email": calendar_id, "self": True}
        if event.request_id:
            body["x_request_id"] = event.request_id
        self._events.setdefault(calendar_id, {})[event_id] = body
        return google_body_to_created_event(body)

    def get_event(self, calendar_id: str, event_id: str) -> CreatedEvent | None:
        body = self._events.get(calendar_id, {}).get(event_id)
        return google_body_to_created_event(body) if body else None

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CreatedEvent]:
        items: list[CreatedEvent] = []
        for body in self._events.get(calendar_id, {}).values():
            start = parse_google_datetime(body["start"]["dateTime"])
            if time_min <= start <= time_max:
                items.append(google_body_to_created_event(body))
        items.sort(key=lambda created: created.raw["start"]["dateTime"])
        return items

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._events.get(calendar_id, {}).pop(event_id, None)
