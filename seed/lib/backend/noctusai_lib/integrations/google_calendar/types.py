"""Google Calendar adapter value objects + Protocol.

Ported from
`whatsapp-google-scheduling/app/services/calendar/types.py` 2026-05-03
via `projects/whatsapp-seed-absorption/` Phase 7.
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
    """Calendar event payload. `request_id` enables idempotent
    `events.insert` retries (Google honors a per-request ID for ~24h);
    consumers should derive it from a stable identifier
    (e.g. `appointment_request.id`) so retries don't double-create
    events. See project §6 Phase 7 idempotency-keys note."""

    summary: str
    start_at: datetime
    end_at: datetime
    timezone: str
    description: str | None = None
    location: str | None = None
    attendees: list[EventAttendee] = field(default_factory=list)
    request_id: str | None = None


@dataclass(frozen=True)
class CreatedEvent:
    event_id: str
    html_link: str | None
    raw: dict[str, Any]


class CalendarAdapter(Protocol):
    """Calendar adapter contract. Concrete implementations:
    `FakeCalendarAdapter` (deterministic in-memory),
    `GoogleCalendarAdapter` (service-account; deferred lift),
    `GoogleCalendarOAuthAdapter` (consenting user; deferred lift).

    `supports_attendees` distinguishes service-account adapters
    (cannot add attendees on personal-Gmail calendars without
    Domain-Wide Delegation) from OAuth adapters (can)."""

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
