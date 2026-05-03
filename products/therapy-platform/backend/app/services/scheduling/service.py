"""Scheduling service — wraps `noctusai_lib.domain.scheduling.SchedulingEngine`
for the therapy-platform pilot.

Public functions:
  - `list_blocked_intervals(...)` — pulls existing appointments + GCal
    events into a single `BlockedInterval` list per the Q3 decision.
  - `materialize_availability_lookup(...)` — turns a therapist's
    `availability_slots` rows into the per-date callable consumed by
    `ProfessionalAvailabilityConflict`.
  - `generate_candidate_slots(...)` — assembles the engine, computes
    `WorkingWindow`s from the therapist's availability for each date
    in the requested window, returns ranked `Slot`s.
  - `book_appointment(...)` — inserts into `therapy.appointments`,
    writes GCal event, captures `google_event_id`. Idempotent via
    request_id derived from (therapist, patient, slot.start_at).
  - `cancel_appointment(...)` — cancellation helper used by Phase 4
    reschedule (delete+create since Protocol has no update_event).

Per `feedback_lgpd_first`: appointment data crossing into Google
Calendar is a personal-data export; flagged at endpoint boundary
(see `app/routers/scheduling.py`).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone as _tz
from typing import Any, Callable
from zoneinfo import ZoneInfo

from noctusai_lib.domain.scheduling import (
    BlockedInterval,
    SchedulingEngine,
    SchedulingRules,
    Slot,
    WorkingWindow,
    ZeroTravelLookup,
)
from noctusai_lib.integrations.google_calendar import (
    CalendarAdapter,
    FakeCalendarAdapter,
    get_calendar_adapter,
)
from noctusai_lib.domain.scheduling.engine import DefaultConflict

from app.services.scheduling.calendar_sync import (
    delete_event_from_gcal,
    gcal_events_as_blocked_intervals,
    update_event_on_gcal,
    write_appointment_to_gcal,
)
from app.services.scheduling.conflicts import (
    AvailabilityWindow,
    ProfessionalAvailabilityConflict,
)
from app.services.scheduling.credentials import TherapyGcalCredentialResolver

logger = logging.getLogger(__name__)


_THERAPY_TZ = ZoneInfo("America/Sao_Paulo")
_DEFAULT_BUFFER_MINUTES = 15
_DEFAULT_DURATION_MINUTES = 50

# Statuses that consume a slot — anything else (cancelled, late_cancelled,
# no_show) frees the time. Source of truth: migration 001
# `therapy.appointments.status` CHECK.
_BLOCKING_APPOINTMENT_STATUSES = (
    "waiting",
    "in_progress",
    "paused",
    "completed",
    "payment_pending",
    "payment_failed",
)


# ---------------------------------------------------------------------------
# Reads — pull blocking intervals from internal tables + GCal
# ---------------------------------------------------------------------------


def list_blocked_intervals(
    *,
    therapist_id: str,
    location_id: int | str,
    window_start: datetime,
    window_end: datetime,
    db: Any,
    calendar_adapter: CalendarAdapter | None = None,
    calendar_id: str | None = None,
) -> list[BlockedInterval]:
    """Aggregate blocking intervals from `therapy.appointments` (active
    statuses) + Google Calendar events (when adapter + calendar_id
    supplied). Returns a single sorted-by-start list."""
    intervals: list[BlockedInterval] = []

    appt_resp = (
        db.table("appointments")
        .select("scheduled_start, scheduled_end, status")
        .eq("therapist_id", therapist_id)
        .gte("scheduled_end", window_start.isoformat())
        .lte("scheduled_start", window_end.isoformat())
        .execute()
    )
    for row in (getattr(appt_resp, "data", None) or []):
        if row.get("status") not in _BLOCKING_APPOINTMENT_STATUSES:
            continue
        intervals.append(
            BlockedInterval(
                start=_parse_dt(row["scheduled_start"]),
                end=_parse_dt(row["scheduled_end"]),
                location_id=location_id,
                assignee_id=therapist_id,
            )
        )

    if calendar_adapter is not None and calendar_id:
        intervals.extend(
            gcal_events_as_blocked_intervals(
                calendar_adapter,
                calendar_id,
                location_id=location_id,
                therapist_id=therapist_id,
                time_min=window_start,
                time_max=window_end,
            )
        )

    intervals.sort(key=lambda b: b.start)
    return intervals


def materialize_availability_lookup(
    *,
    therapist_id: str,
    db: Any,
    rules_timezone: ZoneInfo,
) -> Callable[[date], list[AvailabilityWindow]]:
    """Resolve `therapy.availability_slots` rows once and return a
    pure-function lookup keyed by date. Recurring rows expand to every
    matching weekday in the queried date; specific-date rows match
    only their own date; `is_blocked=true` flips the window to a
    block.

    Postgres `extract(dow from x)` uses Sunday=0..Saturday=6;
    `therapy.availability_slots.day_of_week` follows the same
    convention. Python's `date.weekday()` uses Monday=0..Sunday=6 — we
    convert by `(weekday() + 1) % 7`.
    """
    slot_resp = (
        db.table("availability_slots")
        .select(
            "day_of_week, start_time, end_time, "
            "is_recurring, specific_date, is_blocked"
        )
        .eq("therapist_id", therapist_id)
        .execute()
    )
    rows = list(getattr(slot_resp, "data", None) or [])

    def _lookup(d: date) -> list[AvailabilityWindow]:
        windows: list[AvailabilityWindow] = []
        sunday_first_dow = (d.weekday() + 1) % 7
        for row in rows:
            specific = row.get("specific_date")
            if specific:
                if str(specific) != d.isoformat():
                    continue
            elif row.get("is_recurring"):
                if row.get("day_of_week") != sunday_first_dow:
                    continue
            else:
                continue
            start_t = _parse_time(row["start_time"])
            end_t = _parse_time(row["end_time"])
            start_at = datetime.combine(d, start_t, tzinfo=rules_timezone)
            end_at = datetime.combine(d, end_t, tzinfo=rules_timezone)
            windows.append(
                AvailabilityWindow(
                    start_at=start_at,
                    end_at=end_at,
                    is_blocked=bool(row.get("is_blocked")),
                )
            )
        return windows

    return _lookup


# ---------------------------------------------------------------------------
# Engine assembly + slot generation
# ---------------------------------------------------------------------------


def _resolve_clinic_buffer(db: Any, clinic_id: str | None) -> int:
    if not clinic_id:
        return _DEFAULT_BUFFER_MINUTES
    resp = (
        db.table("clinic_settings")
        .select("transition_buffer_minutes")
        .eq("clinic_id", clinic_id)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if rows and rows[0].get("transition_buffer_minutes") is not None:
        return int(rows[0]["transition_buffer_minutes"])
    return _DEFAULT_BUFFER_MINUTES


def generate_candidate_slots(
    *,
    therapist_id: str,
    clinic_id: str | None,
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int = _DEFAULT_DURATION_MINUTES,
    db: Any,
    calendar_adapter: CalendarAdapter | None = None,
    calendar_id: str | None = None,
) -> list[Slot]:
    """Build engine, walk dates in [window_start, window_end), return
    ranked candidates aggregated across the window."""
    location_id = clinic_id or therapist_id
    buffer_minutes = _resolve_clinic_buffer(db, clinic_id)

    rules = SchedulingRules(
        timezone=_THERAPY_TZ,
        transition_buffer_minutes=buffer_minutes,
        default_duration_minutes=duration_minutes,
        same_location_duration_minutes=duration_minutes,
    )

    blocked = list_blocked_intervals(
        therapist_id=therapist_id,
        location_id=location_id,
        window_start=window_start,
        window_end=window_end,
        db=db,
        calendar_adapter=calendar_adapter,
        calendar_id=calendar_id,
    )

    availability_lookup = materialize_availability_lookup(
        therapist_id=therapist_id,
        db=db,
        rules_timezone=_THERAPY_TZ,
    )

    engine = _build_engine(rules, availability_lookup)

    candidates: list[Slot] = []
    for d in _walk_dates(window_start.date(), window_end.date()):
        # Replace engine.rules.working_windows with the therapist's
        # actual windows for this specific date (recurring + specifics).
        date_windows = [w for w in availability_lookup(d) if not w.is_blocked]
        if not date_windows:
            continue
        engine_for_date = _build_engine(
            SchedulingRules(
                timezone=_THERAPY_TZ,
                transition_buffer_minutes=buffer_minutes,
                default_duration_minutes=duration_minutes,
                same_location_duration_minutes=duration_minutes,
                working_windows=[
                    WorkingWindow(
                        name=f"window-{i}",
                        start=w.start_at.timetz().replace(tzinfo=None),
                        end=w.end_at.timetz().replace(tzinfo=None),
                    )
                    for i, w in enumerate(date_windows)
                ],
            ),
            availability_lookup,
        )
        candidates.extend(
            engine_for_date.candidate_slots(
                requested_date=d,
                target_location_id=location_id,
                existing_intervals=blocked,
                duration_override_minutes=duration_minutes,
            )
        )

    return candidates


def _build_engine(
    rules: SchedulingRules,
    availability_lookup: Callable[[date], list[AvailabilityWindow]],
) -> SchedulingEngine:
    return SchedulingEngine(
        rules=rules,
        travel_lookup=ZeroTravelLookup(),
        conflicts=[
            DefaultConflict(),
            ProfessionalAvailabilityConflict(availability_lookup),
        ],
    )


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


def book_appointment(
    *,
    therapist_id: str,
    patient_id: str,
    clinic_id: str | None,
    slot_start: datetime,
    slot_end: datetime,
    db: Any,
    calendar_adapter: CalendarAdapter | None = None,
    calendar_id: str | None = None,
    summary: str = "Sessão de terapia",
) -> dict:
    """Insert appointment + (best-effort) write GCal event. Returns
    the inserted appointment row including `google_event_id`."""
    request_id = hashlib.sha1(
        f"{therapist_id}|{patient_id}|{slot_start.isoformat()}".encode()
    ).hexdigest()

    google_event_id: str | None = None
    if calendar_adapter is not None and calendar_id:
        google_event_id = write_appointment_to_gcal(
            calendar_adapter,
            calendar_id,
            summary=summary,
            start_at=slot_start,
            end_at=slot_end,
            timezone=str(_THERAPY_TZ),
            request_id=request_id,
        )

    # `patient_origin` is required by the CHECK constraint
    # (clinic_sourced / therapist_sourced / independent / platform_assigned).
    # Default to `platform_assigned` for slot-picker bookings; richer
    # attribution (matching, clinic-sourced) is a follow-up.
    payload = {
        "therapist_id": therapist_id,
        "patient_id": patient_id,
        "clinic_id": clinic_id,
        "scheduled_start": slot_start.isoformat(),
        "scheduled_end": slot_end.isoformat(),
        "status": "waiting",
        "patient_origin": "platform_assigned",
        "google_event_id": google_event_id,
    }
    insert_resp = db.table("appointments").insert(payload).execute()
    rows = getattr(insert_resp, "data", None) or []
    return rows[0] if rows else payload


def reschedule_appointment(
    *,
    appointment_id: str,
    new_start: datetime,
    new_end: datetime,
    db: Any,
    calendar_adapter: CalendarAdapter | None = None,
    calendar_id: str | None = None,
    summary: str = "Sessão de terapia",
) -> dict:
    """Move an appointment in-place: update DB row + update GCal event
    via the adapter's `update_event` (preserves event_id, attendees see
    a move rather than a delete-and-new-invite). When the GCal event
    update fails, the DB row still reflects the new times and
    `google_event_id` is left as-is — operator can resync later."""
    fetch = (
        db.table("appointments")
        .select("google_event_id")
        .eq("id", appointment_id)
        .limit(1)
        .execute()
    )
    rows = getattr(fetch, "data", None) or []
    google_event_id = rows[0].get("google_event_id") if rows else None

    if (
        calendar_adapter is not None
        and calendar_id
        and google_event_id
    ):
        update_event_on_gcal(
            calendar_adapter,
            calendar_id,
            google_event_id,
            summary=summary,
            start_at=new_start,
            end_at=new_end,
            timezone=str(_THERAPY_TZ),
        )

    db.table("appointments").update(
        {
            "scheduled_start": new_start.isoformat(),
            "scheduled_end": new_end.isoformat(),
        }
    ).eq("id", appointment_id).execute()
    return {
        "id": appointment_id,
        "scheduled_start": new_start.isoformat(),
        "scheduled_end": new_end.isoformat(),
        "google_event_id": google_event_id,
    }


def cancel_appointment(
    *,
    appointment_id: str,
    db: Any,
    calendar_adapter: CalendarAdapter | None = None,
    calendar_id: str | None = None,
) -> dict:
    """Mark cancelled + delete GCal event (best-effort)."""
    fetch = (
        db.table("appointments")
        .select("google_event_id")
        .eq("id", appointment_id)
        .limit(1)
        .execute()
    )
    rows = getattr(fetch, "data", None) or []
    google_event_id = rows[0].get("google_event_id") if rows else None
    if calendar_adapter is not None and calendar_id and google_event_id:
        delete_event_from_gcal(calendar_adapter, calendar_id, google_event_id)

    db.table("appointments").update({"status": "cancelled"}).eq(
        "id", appointment_id
    ).execute()
    return {"id": appointment_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Adapter resolution helper (factory for routers)
# ---------------------------------------------------------------------------


def resolve_calendar_for_therapist(
    *,
    db: Any,
    therapist_id: str,
    client_id: str | None,
    client_secret: str | None,
) -> tuple[CalendarAdapter, str | None]:
    """Returns (adapter, calendar_id) — the adapter is the real OAuth
    one when credentials resolve, else `FakeCalendarAdapter`."""
    resolver = TherapyGcalCredentialResolver(db, client_id, client_secret)
    adapter = get_calendar_adapter(resolver, tenant_id=therapist_id)

    cal_id_resp = (
        db.table("therapist_profiles")
        .select("gcal_calendar_id")
        .eq("user_id", therapist_id)
        .limit(1)
        .execute()
    )
    rows = getattr(cal_id_resp, "data", None) or []
    calendar_id = rows[0].get("gcal_calendar_id") if rows else None

    if isinstance(adapter, FakeCalendarAdapter) and calendar_id is None:
        calendar_id = "primary"
    return adapter, calendar_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 datetime; pad missing tz as UTC for
    comparison consistency."""
    cleaned = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_tz.utc)
    return parsed


def _parse_time(value: str) -> time:
    """Parse HH:MM or HH:MM:SS to time."""
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def _walk_dates(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)
