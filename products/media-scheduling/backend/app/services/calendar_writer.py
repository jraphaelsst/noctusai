"""Google Calendar writer — wraps the seed `get_calendar_adapter`.

Real-estate-specific event mapping (title from service_type + property
address; description with agent + crew contact) lives here, NOT in the
seed adapter.

Credential resolution: `OAuthCredentialResolver` reads `media_scheduling.
oauth_credentials` (one row per `(provider, account_email)`). The seed
`GoogleCalendarOAuthAdapter` consumes the resolver — it doesn't know
that the storage is Supabase.

For the MVP we resolve the SINGLE `provider='google'` row (the source
repo also uses one calendar account for the whole tenant). Multi-tenant
expansion would key on `tenant_id` → distinct `account_email`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from noctusai_lib.integrations.google_calendar import (
    CalendarAdapter,
    CalendarCredentials,
    CreatedEvent,
    EventAttendee,
    EventInput,
    OAuthCalendarCredentials,
    get_calendar_adapter,
)

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


class OAuthCredentialResolver:
    """`CalendarCredentialResolver` Protocol impl reading from Supabase.

    Returns `OAuthCalendarCredentials` when a row exists for `(provider=
    'google', account_email=tenant_account_email)`; `None` otherwise
    (the factory then returns a `FakeCalendarAdapter`, safe dev fallback).

    `tenant_account_email` is the configured calendar-owning email for
    this product instance; today there's one (the agency's gmail).
    """

    def __init__(
        self,
        supabase: "Client",
        client_id: str,
        client_secret: str,
        tenant_account_email: str,
    ):
        self._sb = supabase
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_account_email = tenant_account_email

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> CalendarCredentials | None:
        # `tenant_id` accepted to match the seed Protocol surface; today
        # we resolve a single row keyed on the configured account email.
        try:
            response = (
                self._sb.schema("media_scheduling")
                .table("oauth_credentials")
                .select("refresh_token, access_token, scopes")
                .eq("provider", "google")
                .eq("account_email", self._tenant_account_email)
                .single()
                .execute()
            )
        except Exception:
            logger.warning(
                "OAuthCredentialResolver lookup failed for %s",
                self._tenant_account_email,
                exc_info=True,
            )
            return None

        row = response.data if response is not None else None
        if not row or not row.get("refresh_token"):
            return None

        scopes_str = row.get("scopes") or "https://www.googleapis.com/auth/calendar"
        scopes = [s.strip() for s in scopes_str.split() if s.strip()] or [
            "https://www.googleapis.com/auth/calendar"
        ]
        return OAuthCalendarCredentials(
            refresh_token=row["refresh_token"],
            client_id=self._client_id,
            client_secret=self._client_secret,
            token=row.get("access_token"),
            scopes=scopes,
        )


class CalendarWriter:
    """Thin wrapper exposing `create_event` / `delete_event` against the
    seed adapter — the only two operations the LLM tool handlers use.

    `tenant_id` is forwarded to the resolver so future multi-tenant
    expansions don't require touching this surface.
    """

    def __init__(
        self,
        adapter: CalendarAdapter,
        calendar_id: str = "primary",
    ):
        self._adapter = adapter
        self._calendar_id = calendar_id

    def create_event(self, event: EventInput) -> CreatedEvent:
        return self._adapter.create_event(self._calendar_id, event)

    def delete_event(self, event_id: str) -> None:
        self._adapter.delete_event(self._calendar_id, event_id)


def build_event_input(
    *,
    summary: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[EventAttendee] | None = None,
    request_id: str | None = None,
) -> EventInput:
    """Compose an `EventInput` with the real-estate-specific summary
    convention pre-applied. Currently a thin pass-through; centralized
    so the title-mapping rule can evolve in one place."""
    return EventInput(
        summary=summary,
        start_at=start_at,
        end_at=end_at,
        timezone=timezone,
        description=description,
        location=location,
        attendees=list(attendees) if attendees else [],
        request_id=request_id,
    )


def make_calendar_writer(
    supabase: "Client",
    *,
    google_oauth_client_id: str,
    google_oauth_client_secret: str,
    tenant_account_email: str,
    calendar_id: str = "primary",
    org_id: str | None = None,
) -> CalendarWriter:
    """Compose a `CalendarWriter` against the seed adapter factory.

    When OAuth credentials aren't yet stored (Phase 3 OAuth flow not
    completed), the factory returns a `FakeCalendarAdapter` — safe
    dev fallback. `org_id` is the seed-vocabulary `tenant_id`.
    """
    resolver = OAuthCredentialResolver(
        supabase=supabase,
        client_id=google_oauth_client_id,
        client_secret=google_oauth_client_secret,
        tenant_account_email=tenant_account_email,
    )
    adapter = get_calendar_adapter(resolver=resolver, tenant_id=org_id)
    return CalendarWriter(adapter=adapter, calendar_id=calendar_id)
