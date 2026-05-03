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
    """Calendar event payload.

    `request_id` is consumer-provided metadata intended for idempotent
    retries — derive it from a stable identifier (e.g.
    `appointment_request.id`). **Adapters do NOT currently translate
    `request_id` into Google's wire-level idempotency.** True idempotency
    requires deriving `body["id"]` from `request_id` and swallowing 409
    on duplicate insert; that work is deferred until a consumer hits
    a real retry-storm (see `google-calendar-real-adapters` PROJECT.md
    §11 #3). Until then, consumers must enforce idempotency at the call
    site (e.g. by checking their own DB before invoking `create_event`)."""

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
    `FakeCalendarAdapter` (deterministic in-memory; dev/test default),
    `GoogleCalendarServiceAccountAdapter` (server-to-server; optional
    Domain-Wide Delegation via `delegate_email`),
    `GoogleCalendarOAuthAdapter` (user-delegated, refresh-token-based).

    `supports_attendees` distinguishes service-account adapters acting
    on a calendar without DWD (cannot add attendees on personal-Gmail
    calendars) from OAuth / DWD-delegated adapters (can). The factory
    `get_calendar_adapter(resolver, tenant_id)` picks the concrete
    adapter from the credentials kind returned by the resolver."""

    supports_attendees: bool

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent: ...

    def get_event(self, calendar_id: str, event_id: str) -> CreatedEvent | None: ...

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CreatedEvent]: ...

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        event: EventInput,
    ) -> CreatedEvent: ...

    def delete_event(self, calendar_id: str, event_id: str) -> None: ...
