"""Shared HTTP plumbing for Google Calendar v3 calls.

Ported from
``whatsapp-google-scheduling/app/services/calendar/_google_api.py``. Both
``GoogleCalendarAdapter`` (service-account auth) and any future OAuth
adapter call these helpers, passing in their authenticated ``service``
instance. Keeps the wire shape in one place.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def insert_event(service: Any, calendar_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return (
        service.events()
        .insert(calendarId=calendar_id, body=body, sendUpdates="all")
        .execute()
    )


def get_event(service: Any, calendar_id: str, event_id: str) -> dict[str, Any] | None:
    from googleapiclient.errors import HttpError

    try:
        return (
            service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            return None
        raise


def list_events(
    service: Any,
    calendar_id: str,
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    response = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return response.get("items", [])


def delete_event(service: Any, calendar_id: str, event_id: str) -> None:
    (
        service.events()
        .delete(calendarId=calendar_id, eventId=event_id, sendUpdates="all")
        .execute()
    )
