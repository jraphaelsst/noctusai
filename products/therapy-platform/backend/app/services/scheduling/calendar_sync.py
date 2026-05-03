"""Google Calendar sync helpers — read GCal events as `BlockedInterval`s
for slot generation, write confirmed appointments back to the
therapist's calendar.

The adapter is supplied by the caller (resolved via
`get_calendar_adapter(TherapyGcalCredentialResolver(...), tenant_id=...)`),
so tests can pass `FakeCalendarAdapter` directly. Per the Q3 + Q4
decisions in PROJECT.md §2: tests use Fake; production uses the real
OAuth adapter when credentials resolve.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from noctusai_lib.domain.scheduling import BlockedInterval
from noctusai_lib.integrations.google_calendar import (
    CalendarAdapter,
    EventAttendee,
    EventInput,
)

logger = logging.getLogger(__name__)


def gcal_events_as_blocked_intervals(
    adapter: CalendarAdapter,
    calendar_id: str,
    location_id: int | str,
    therapist_id: str,
    time_min: datetime,
    time_max: datetime,
) -> list[BlockedInterval]:
    """List events in [time_min, time_max) and convert to BlockedIntervals.

    Off-platform GCal events become first-class blocks during slot
    generation per the Q3 decision (catches phone-calendar-only events
    the platform never saw)."""
    try:
        events = adapter.list_events(calendar_id, time_min, time_max)
    except Exception:
        logger.exception(
            "GCal list_events failed for therapist=%s calendar=%s; "
            "treating as empty interval set",
            therapist_id,
            calendar_id,
        )
        return []

    intervals: list[BlockedInterval] = []
    for ev in events:
        raw = ev.raw or {}
        start_obj = (raw.get("start") or {})
        end_obj = (raw.get("end") or {})
        start_str = start_obj.get("dateTime") or start_obj.get("date")
        end_str = end_obj.get("dateTime") or end_obj.get("date")
        if not start_str or not end_str:
            continue
        try:
            from noctusai_lib.integrations.google_calendar import parse_google_datetime
            start_at = parse_google_datetime(start_str)
            end_at = parse_google_datetime(end_str)
        except Exception:
            logger.warning("GCal event %s has unparseable dates; skipping", ev.event_id)
            continue
        intervals.append(
            BlockedInterval(
                start=start_at,
                end=end_at,
                location_id=location_id,
                assignee_id=therapist_id,
            )
        )
    return intervals


def write_appointment_to_gcal(
    adapter: CalendarAdapter,
    calendar_id: str,
    *,
    summary: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    request_id: str | None = None,
    description: str | None = None,
    attendees: Iterable[EventAttendee] = (),
) -> str | None:
    """Insert an event in the therapist's GCal; returns the event_id
    (or None if write failed). Idempotent via `request_id` per
    Google's events.insert per-request-id contract."""
    try:
        created = adapter.create_event(
            calendar_id,
            EventInput(
                summary=summary,
                start_at=start_at,
                end_at=end_at,
                timezone=timezone,
                description=description,
                attendees=list(attendees),
                request_id=request_id,
            ),
        )
    except Exception:
        logger.exception(
            "GCal create_event failed (calendar=%s, summary=%s); "
            "appointment written without google_event_id",
            calendar_id,
            summary,
        )
        return None
    return created.event_id


def delete_event_from_gcal(
    adapter: CalendarAdapter,
    calendar_id: str,
    event_id: str,
) -> None:
    """Best-effort delete; logs but doesn't raise."""
    try:
        adapter.delete_event(calendar_id, event_id)
    except Exception:
        logger.exception(
            "GCal delete_event failed (calendar=%s, event=%s); "
            "may leave a stale event in the user's calendar",
            calendar_id,
            event_id,
        )


def update_event_on_gcal(
    adapter: CalendarAdapter,
    calendar_id: str,
    event_id: str,
    *,
    summary: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    request_id: str | None = None,
    description: str | None = None,
    attendees: Iterable[EventAttendee] = (),
) -> str | None:
    """Update an existing event in-place; returns the (unchanged)
    event_id on success or None on failure. Preserves the calendar
    event identity across reschedules so attendees see the move
    instead of a delete+new-invite churn."""
    try:
        updated = adapter.update_event(
            calendar_id,
            event_id,
            EventInput(
                summary=summary,
                start_at=start_at,
                end_at=end_at,
                timezone=timezone,
                description=description,
                attendees=list(attendees),
                request_id=request_id,
            ),
        )
    except Exception:
        logger.exception(
            "GCal update_event failed (calendar=%s, event=%s); "
            "the calendar event may be out of sync with the appointment",
            calendar_id,
            event_id,
        )
        return None
    return updated.event_id
