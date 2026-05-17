"""Calendar adapter contract.

Ported verbatim from ``whatsapp-google-scheduling/app/services/calendar/types.py``.
The Protocol is the seam our chatbot tools call into; the dataclasses
are the wire shape every adapter (Fake, ServiceAccount, OAuth) returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class EventAttendee:
    email: str
    display_name: str | None = None


@dataclass(frozen=True)
class EventInput:
    summary: str
    start_at: datetime
    end_at: datetime
    timezone: str
    description: str | None = None
    location: str | None = None
    attendees: list[EventAttendee] = field(default_factory=list)


@dataclass(frozen=True)
class CreatedEvent:
    event_id: str
    html_link: str | None
    raw: dict[str, Any]


class CalendarAdapter(Protocol):
    supports_attendees: bool

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent: ...

    def get_event(self, calendar_id: str, event_id: str) -> CreatedEvent | None: ...

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CreatedEvent]: ...

    def delete_event(self, calendar_id: str, event_id: str) -> None: ...
