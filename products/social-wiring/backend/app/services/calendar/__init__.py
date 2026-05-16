"""Calendar package factory.

Ported from ``whatsapp-google-scheduling/app/services/calendar/__init__.py``
with the credential storage adapted onto our existing
:class:`CredentialStore` (Fernet-encrypted rows in
``social_wiring.credentials`` keyed by ``(org_id, provider)``).

Resolution order:

1. OAuth path — when ``GOOGLE_OAUTH_CLIENT_ID`` /
   ``GOOGLE_OAUTH_CLIENT_SECRET`` are configured AND the org has a
   stored credential row (``provider='google_calendar'``), use the
   OAuth adapter (can add attendees, sends invite emails).
2. Service-account path — when ``GOOGLE_SERVICE_ACCOUNT_FILE`` points
   at a readable JSON file, use the service-account adapter (no
   attendee support on personal-Gmail calendars).
3. Fallback — :class:`FakeCalendarAdapter`. Local dev + tests.

Callers pass the org_id; the factory pulls everything else from
settings + the credential store.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from app.config import settings as default_settings
from app.services.calendar.fake_adapter import FakeCalendarAdapter
from app.services.calendar.google_adapter import GoogleCalendarAdapter
from app.services.calendar.oauth_adapter import (
    CALENDAR_PROVIDER,
    GoogleCalendarOAuthAdapter,
)
from app.services.calendar.types import (
    CalendarAdapter,
    CreatedEvent,
    EventAttendee,
    EventInput,
)

if TYPE_CHECKING:
    from app.services.credential_store import CredentialStore

logger = logging.getLogger(__name__)

__all__ = [
    "CALENDAR_PROVIDER",
    "CalendarAdapter",
    "CreatedEvent",
    "EventAttendee",
    "EventInput",
    "FakeCalendarAdapter",
    "GoogleCalendarAdapter",
    "GoogleCalendarOAuthAdapter",
    "get_calendar_adapter",
]


def get_calendar_adapter(
    *,
    org_id: UUID | None = None,
    credential_store: "CredentialStore | None" = None,
    settings=None,
) -> CalendarAdapter:
    settings = settings or default_settings

    # 1. OAuth — only when client id + secret are configured AND the
    # org has a stored credential row.
    if (
        org_id is not None
        and credential_store is not None
        and settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and _has_oauth_credential(credential_store, org_id)
    ):
        logger.info(
            "Calendar adapter: GoogleCalendarOAuthAdapter (consent stored for org %s)",
            org_id,
        )
        return GoogleCalendarOAuthAdapter(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            credential_store=credential_store,
            org_id=org_id,
        )

    # 2. Service account
    sa_file = settings.google_service_account_file
    if sa_file:
        if Path(sa_file).is_file():
            logger.info("Calendar adapter: GoogleCalendarAdapter (service account)")
            return GoogleCalendarAdapter(sa_file)
        logger.warning(
            "GOOGLE_SERVICE_ACCOUNT_FILE points to %r but the file does not exist; "
            "falling back to FakeCalendarAdapter",
            sa_file,
        )

    # 3. Fake — dev / no credentials yet
    return FakeCalendarAdapter()


def _has_oauth_credential(store: "CredentialStore", org_id: UUID) -> bool:
    try:
        return store.get(org_id=org_id, provider=CALENDAR_PROVIDER) is not None
    except Exception:
        logger.exception("OAuth credential lookup failed; skipping OAuth path")
        return False
