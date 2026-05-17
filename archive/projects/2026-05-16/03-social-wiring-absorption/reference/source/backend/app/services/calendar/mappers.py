"""EventInput ↔ Google Calendar v3 body mappers.

Ported from
``whatsapp-google-scheduling/app/services/calendar/mappers.py``. The
fake adapter relies on the same body shape so it can replay events
indistinguishably from the real API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.calendar.types import CreatedEvent, EventInput


def event_to_google_body(event: EventInput) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": event.summary,
        "start": {"dateTime": event.start_at.isoformat(), "timeZone": event.timezone},
        "end": {"dateTime": event.end_at.isoformat(), "timeZone": event.timezone},
    }
    if event.description:
        body["description"] = event.description
    if event.location:
        body["location"] = event.location
    if event.attendees:
        body["attendees"] = [
            {
                "email": a.email,
                **({"displayName": a.display_name} if a.display_name else {}),
            }
            for a in event.attendees
        ]
    return body


def google_body_to_created_event(body: dict[str, Any]) -> CreatedEvent:
    return CreatedEvent(
        event_id=body["id"],
        html_link=body.get("htmlLink"),
        raw=body,
    )


def parse_google_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
