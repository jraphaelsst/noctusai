"""Google Calendar v3 adapter using service-account auth.

Ported from
``whatsapp-google-scheduling/app/services/calendar/google_adapter.py``.

The target calendar must be shared with the service account's email
(Settings → Share with specific people) with permission "Make changes
to events". Service accounts CANNOT add attendees on personal-Gmail
calendars without Domain-Wide Delegation; for that the reference repo
ships ``GoogleCalendarOAuthAdapter`` — we omit that for v1 here and
land it as a follow-up if the One Consultoria flow needs it.

Reference: https://developers.google.com/calendar/api/v3/reference
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.services.calendar import _google_api
from app.services.calendar.mappers import event_to_google_body, google_body_to_created_event
from app.services.calendar.types import CreatedEvent, EventInput

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource


CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarAdapter:
    """Service-account-backed Google Calendar adapter.

    Construction takes the path to a service-account JSON file. The
    underlying ``Resource`` is lazy-built on first call so import-time
    failures don't trip when the SA file is absent in dev.
    """

    supports_attendees = False

    def __init__(self, service_account_file: str):
        self._service_account_file = service_account_file
        self._service: "Resource | None" = None

    def _get_service(self) -> "Resource":
        if self._service is None:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self._service_account_file,
                scopes=CALENDAR_SCOPES,
            )
            self._service = build(
                "calendar",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )
        return self._service

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent:
        response = _google_api.insert_event(
            self._get_service(), calendar_id, event_to_google_body(event)
        )
        return google_body_to_created_event(response)

    def get_event(self, calendar_id: str, event_id: str) -> CreatedEvent | None:
        body = _google_api.get_event(self._get_service(), calendar_id, event_id)
        return google_body_to_created_event(body) if body else None

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CreatedEvent]:
        items = _google_api.list_events(self._get_service(), calendar_id, time_min, time_max)
        return [google_body_to_created_event(item) for item in items]

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        _google_api.delete_event(self._get_service(), calendar_id, event_id)
