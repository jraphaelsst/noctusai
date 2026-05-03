"""OAuth-backed Google Calendar adapter (user-delegated).

Implements `CalendarAdapter` against Google Calendar v3 using
refresh-token-based OAuth credentials. Use when the calendar belongs
to an end user (personal Gmail or Workspace user) and the user has
consented via the standard OAuth dance.

Token refresh is handled automatically by `google.oauth2.credentials.Credentials`
when it detects the access token is expired — the refresh_token,
client_id, and client_secret must be present.

`supports_attendees=True` — OAuth-acting-as-user can always add
attendees to user-owned calendars.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from noctusai_lib.integrations.google_calendar.credentials import (
    CalendarCredentialResolver,
    OAuthCalendarCredentials,
)
from noctusai_lib.integrations.google_calendar.mappers import (
    event_to_google_body,
    google_body_to_created_event,
)
from noctusai_lib.integrations.google_calendar.types import CreatedEvent, EventInput


class GoogleCalendarOAuthAdapter:
    """OAuth user-delegated Google Calendar adapter."""

    supports_attendees: bool = True

    def __init__(
        self,
        resolver: CalendarCredentialResolver,
        *,
        tenant_id: str | None = None,
    ):
        self._resolver = resolver
        self._tenant_id = tenant_id

    def _service(self) -> Any:
        creds = self._resolver.get_credentials(self._tenant_id)
        if not isinstance(creds, OAuthCalendarCredentials):
            raise RuntimeError(
                "GoogleCalendarOAuthAdapter requires OAuthCalendarCredentials; "
                f"resolver returned {type(creds).__name__}"
            )
        google_creds = Credentials(
            token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            scopes=creds.scopes,
        )
        if not google_creds.valid and google_creds.refresh_token:
            google_creds.refresh(Request())
        return build("calendar", "v3", credentials=google_creds, cache_discovery=False)

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent:
        body = event_to_google_body(event)
        created = (
            self._service()
            .events()
            .insert(calendarId=calendar_id, body=body, sendUpdates="all")
            .execute()
        )
        return google_body_to_created_event(created)

    def get_event(self, calendar_id: str, event_id: str) -> CreatedEvent | None:
        try:
            raw = (
                self._service()
                .events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — surface only 404 as None
            from googleapiclient.errors import HttpError

            if isinstance(exc, HttpError) and exc.resp.status == 404:
                return None
            raise
        return google_body_to_created_event(raw)

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CreatedEvent]:
        result = (
            self._service()
            .events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = result.get("items", [])
        return [google_body_to_created_event(item) for item in items]

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        event: EventInput,
    ) -> CreatedEvent:
        body = event_to_google_body(event)
        updated = (
            self._service()
            .events()
            .update(
                calendarId=calendar_id,
                eventId=event_id,
                body=body,
                sendUpdates="all",
            )
            .execute()
        )
        return google_body_to_created_event(updated)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._service().events().delete(
            calendarId=calendar_id, eventId=event_id, sendUpdates="all"
        ).execute()


__all__ = ["GoogleCalendarOAuthAdapter"]
