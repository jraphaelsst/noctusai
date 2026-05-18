"""Google Calendar adapters — Fake (testable shape) + Service-account
+ OAuth (user-delegated).

Lifted 2026-05-03 by `projects/whatsapp-seed-absorption/` Phase 7 from
`whatsapp-google-scheduling/app/services/calendar/`. Real adapters
landed 2026-05-03.

**What ships:**
- `EventInput`, `EventAttendee`, `CreatedEvent` value objects.
- `CalendarAdapter` Protocol.
- `FakeCalendarAdapter` — deterministic in-memory implementation for
  dev + tests. Mirrors the Google Calendar v3 response shape so
  consumer code can swap real/fake transparently.
- `GoogleCalendarServiceAccountAdapter` — server-to-server, calendar
  must be owned by the service account (or shared / DWD-delegated).
- `GoogleCalendarOAuthAdapter` — user-delegated, refresh-token based.
- `CalendarCredentialResolver` Protocol — product-injected per-tenant
  credential lookup. Adapters resolve through it; they don't know how
  credentials are stored.
- `ServiceAccountCalendarCredentials` + `OAuthCalendarCredentials`
  dataclasses — Protocol return shapes.
- Pure-function mappers (`event_to_google_body`,
  `google_body_to_created_event`, `parse_google_datetime`).

**Default factory** (`get_calendar_adapter`): returns `FakeCalendarAdapter`
when no resolver is supplied (dev/test default). Pass a
`CalendarCredentialResolver` to get a real adapter — the kind is picked
from the credentials returned by `resolver.get_credentials(tenant_id)`.
"""

from noctusai_lib.integrations.google_calendar.credentials import (
    CalendarCredentialResolver,
    CalendarCredentials,
    OAuthCalendarCredentials,
    ServiceAccountCalendarCredentials,
)
from noctusai_lib.integrations.google_calendar.fake_adapter import FakeCalendarAdapter
from noctusai_lib.integrations.google_calendar.mappers import (
    event_to_google_body,
    google_body_to_created_event,
    parse_google_datetime,
)
from noctusai_lib.integrations.google_calendar.types import (
    CalendarAdapter,
    CreatedEvent,
    EventAttendee,
    EventInput,
)


def get_calendar_adapter(
    resolver: CalendarCredentialResolver | None = None,
    *,
    tenant_id: str | None = None,
    credential_store=None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
) -> CalendarAdapter:
    """Return a calendar adapter wired for the supplied resolver, or
    `FakeCalendarAdapter` when no resolver is given.

    Two ways to supply credentials (mutually exclusive — `resolver`
    wins if both are given):

    - `resolver` — a `CalendarCredentialResolver` (full control).
    - `credential_store` (+ `oauth_client_id`/`oauth_client_secret`) —
      the convenience path: pass a
      `noctusai_lib.security.token_store.CredentialStore` directly and
      the factory builds a `CredentialStoreCalendarResolver` internally
      (no per-product resolver bridge). The OAuth-client identity is
      the product's app credentials (not per-tenant) so it's passed
      here, not stored in the bundle.

    Adapter-kind selection uses the credentials returned by
    `resolver.get_credentials(tenant_id)`:
    - `ServiceAccountCalendarCredentials` → `GoogleCalendarServiceAccountAdapter`
    - `OAuthCalendarCredentials`          → `GoogleCalendarOAuthAdapter`
    - `None`                              → `FakeCalendarAdapter` (resolver
      had nothing for this tenant; safe dev/test fallback)
    """
    if resolver is None and credential_store is not None:
        if not (oauth_client_id and oauth_client_secret):
            raise ValueError(
                "get_calendar_adapter(credential_store=...) also requires "
                "oauth_client_id and oauth_client_secret (the product's "
                "OAuth-client app identity)"
            )
        from noctusai_lib.integrations.credential_resolvers import (
            CredentialStoreCalendarResolver,
        )

        resolver = CredentialStoreCalendarResolver(
            credential_store,
            client_id=oauth_client_id,
            client_secret=oauth_client_secret,
        )

    if resolver is None:
        return FakeCalendarAdapter()

    creds = resolver.get_credentials(tenant_id)
    if creds is None:
        return FakeCalendarAdapter()

    # Lazy imports — google-api-python-client is heavy; keep the fake
    # path importable even if the SDK is missing in a slim environment.
    if isinstance(creds, ServiceAccountCalendarCredentials):
        from noctusai_lib.integrations.google_calendar.service_account_adapter import (
            GoogleCalendarServiceAccountAdapter,
        )

        return GoogleCalendarServiceAccountAdapter(resolver, tenant_id=tenant_id)

    if isinstance(creds, OAuthCalendarCredentials):
        from noctusai_lib.integrations.google_calendar.oauth_adapter import (
            GoogleCalendarOAuthAdapter,
        )

        return GoogleCalendarOAuthAdapter(resolver, tenant_id=tenant_id)

    raise RuntimeError(
        f"Unsupported credentials kind: {type(creds).__name__}"
    )


__all__ = [
    "CalendarAdapter",
    "CalendarCredentialResolver",
    "CalendarCredentials",
    "CreatedEvent",
    "EventAttendee",
    "EventInput",
    "FakeCalendarAdapter",
    "OAuthCalendarCredentials",
    "ServiceAccountCalendarCredentials",
    "event_to_google_body",
    "get_calendar_adapter",
    "google_body_to_created_event",
    "parse_google_datetime",
]
