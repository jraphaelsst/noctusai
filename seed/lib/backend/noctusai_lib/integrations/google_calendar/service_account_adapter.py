"""Service-account-backed Google Calendar adapter.

Implements the `CalendarAdapter` Protocol against the Google Calendar
v3 REST API using `googleapiclient` + `google-auth`.

Constraints (server-to-server):
- Calendar must be owned by the service-account OR shared with its
  email address.
- `supports_attendees=False` by default — adding attendees on a
  personal-Gmail calendar requires Domain-Wide Delegation (set
  `delegate_email` on the credentials). When delegation is configured,
  flip `supports_attendees=True` at construction time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from noctusai_lib.integrations.google_calendar.credentials import (
    CalendarCredentialResolver,
    ServiceAccountCalendarCredentials,
)
from noctusai_lib.integrations.google_calendar.mappers import (
    event_to_google_body,
    google_body_to_created_event,
)
from noctusai_lib.integrations.google_calendar.types import CreatedEvent, EventInput


class GoogleCalendarServiceAccountAdapter:
    """Service-account-backed Google Calendar adapter.

    Per-tenant credentials are resolved through a
    `CalendarCredentialResolver` injected at construction. Each call
    re-resolves; consumers wanting to cache should layer that on top."""

    def __init__(
        self,
        resolver: CalendarCredentialResolver,
        *,
        tenant_id: str | None = None,
        supports_attendees: bool = False,
    ):
        self._resolver = resolver
        self._tenant_id = tenant_id
        self.supports_attendees = supports_attendees

    def _service(self) -> Any:
        creds = self._resolver.get_credentials(self._tenant_id)
        if not isinstance(creds, ServiceAccountCalendarCredentials):
            raise RuntimeError(
                "GoogleCalendarServiceAccountAdapter requires "
                "ServiceAccountCalendarCredentials; resolver returned "
                f"{type(creds).__name__}"
            )
        google_creds = service_account.Credentials.from_service_account_info(
            creds.info, scopes=creds.scopes
        )
        if creds.delegate_email:
            google_creds = google_creds.with_subject(creds.delegate_email)
        return build("calendar", "v3", credentials=google_creds, cache_discovery=False)

    def create_event(self, calendar_id: str, event: EventInput) -> CreatedEvent:
        body = event_to_google_body(event)
        kwargs: dict[str, Any] = {"calendarId": calendar_id, "body": body}
        # When supports_attendees is True (DWD-delegated or shared
        # calendar with attendees), notify them. Otherwise leave
        # sendUpdates at Google's default ("none"), which is correct
        # for the typical no-attendees service-account use case.
        if self.supports_attendees:
            kwargs["sendUpdates"] = "all"
        created = self._service().events().insert(**kwargs).execute()
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

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        kwargs: dict[str, Any] = {"calendarId": calendar_id, "eventId": event_id}
        if self.supports_attendees:
            kwargs["sendUpdates"] = "all"
        self._service().events().delete(**kwargs).execute()


__all__ = ["GoogleCalendarServiceAccountAdapter"]
