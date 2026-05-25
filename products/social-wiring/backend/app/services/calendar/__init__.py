"""Calendar package — **thin seed-consume seam**.

Phase 5 of ``projects/social-wiring-google-seed-consume/`` retired the
hand-rolled googleapiclient + ``_get_service`` Credentials-object
machinery in favour of ``noctusai_lib.integrations.google_calendar``
(the canonical Protocol + Fake + ServiceAccount + OAuth + factory the
seed already ships). Phase 3b previously moved OAuth lifecycle
(authorize/exchange/refresh/revoke) onto ``GoogleProvider``; this
phase finishes the migration by delegating the API layer too.

The product factory ``get_calendar_adapter`` is a thin selector that
maps the absorbed (org_id, credential_store, settings) shape into the
seed factory's ``(resolver, tenant_id)`` shape. Resolution order is
preserved verbatim:

1. OAuth path — when ``GOOGLE_OAUTH_CLIENT_ID`` /
   ``GOOGLE_OAUTH_CLIENT_SECRET`` are configured AND the org has a
   stored credential row (``provider='google_calendar'``), use the
   seed ``GoogleCalendarOAuthAdapter`` via
   ``CredentialStoreCalendarResolver`` (the seed bridge).
2. Service-account path — when ``GOOGLE_SERVICE_ACCOUNT_FILE`` points
   at a readable JSON file, load it + wrap in a tiny SA resolver and
   use seed ``GoogleCalendarServiceAccountAdapter``.
3. Fallback — seed ``FakeCalendarAdapter``. Local dev + tests.

``GoogleCalendarAdapter`` is re-exported as an alias for the seed
``GoogleCalendarServiceAccountAdapter`` so the historic
``isinstance(adapter, GoogleCalendarAdapter)`` checks in
``calendar_router._adapter_label`` keep distinguishing the SA branch
from the OAuth branch. ``CALENDAR_PROVIDER`` is re-exported from the
seed ``credential_resolvers`` module — the canonical provider key
that both the read (resolver) and the write (oauth_router callback)
paths must agree on.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from noctusai_lib.integrations.credential_resolvers import (
    CALENDAR_PROVIDER,
    CredentialStoreCalendarResolver,
)
from noctusai_lib.integrations.google_calendar import (
    CalendarAdapter,
    CreatedEvent,
    EventAttendee,
    EventInput,
    FakeCalendarAdapter,
    ServiceAccountCalendarCredentials,
    get_calendar_adapter as _seed_get_calendar_adapter,
)
from noctusai_lib.integrations.google_calendar.oauth_adapter import (
    GoogleCalendarOAuthAdapter,
)
from noctusai_lib.integrations.google_calendar.service_account_adapter import (
    GoogleCalendarServiceAccountAdapter,
)

from app.config import settings as default_settings
from app.utils import has_oauth_credential

if TYPE_CHECKING:
    from app.services.credential_vault import CredentialStore

logger = logging.getLogger(__name__)

# Back-compat alias — the SA-backed adapter used to be called
# ``GoogleCalendarAdapter`` in the absorbed product. ``calendar_router``
# does ``isinstance(adapter, GoogleCalendarAdapter)`` to label the
# service-account branch in status responses; alias preserves that.
GoogleCalendarAdapter = GoogleCalendarServiceAccountAdapter

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


class _ServiceAccountCalendarResolver:
    """Tiny resolver that returns the same SA-loaded credentials for
    every tenant. Mirrors the absorbed product behavior: one SA JSON
    file per deployment, shared across orgs."""

    def __init__(self, info: dict) -> None:
        self._creds = ServiceAccountCalendarCredentials(info=info)

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> ServiceAccountCalendarCredentials | None:
        return self._creds


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
        and has_oauth_credential(credential_store, org_id, CALENDAR_PROVIDER)
    ):
        logger.info(
            "Calendar adapter: GoogleCalendarOAuthAdapter (consent stored for org %s)",
            org_id,
        )
        resolver = CredentialStoreCalendarResolver(
            credential_store,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
        )
        return _seed_get_calendar_adapter(resolver=resolver, tenant_id=str(org_id))

    # 2. Service account
    sa_file = settings.google_service_account_file
    if sa_file:
        if Path(sa_file).is_file():
            logger.info("Calendar adapter: GoogleCalendarAdapter (service account)")
            try:
                info = json.loads(Path(sa_file).read_text())
            except (OSError, ValueError):
                logger.exception(
                    "Failed to load service-account file %r; falling back to FakeCalendarAdapter",
                    sa_file,
                )
                return FakeCalendarAdapter()
            resolver = _ServiceAccountCalendarResolver(info)
            return _seed_get_calendar_adapter(resolver=resolver)
        logger.warning(
            "GOOGLE_SERVICE_ACCOUNT_FILE points to %r but the file does not exist; "
            "falling back to FakeCalendarAdapter",
            sa_file,
        )

    # 3. Fake — dev / no credentials yet
    return FakeCalendarAdapter()
