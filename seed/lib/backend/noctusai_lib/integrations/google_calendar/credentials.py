"""Per-tenant Google Calendar credentials + resolver Protocol.

Products implement `CalendarCredentialResolver` to look up credentials
per tenant (typically from Supabase or a vault). The real adapters
(`GoogleCalendarServiceAccountAdapter`, `GoogleCalendarOAuthAdapter`)
consume the Protocol — they don't know HOW credentials are stored,
only how to use them once resolved.

Two credential kinds:
- **Service-account** — server-to-server. Calendar must be owned by
  the service account OR shared with its email. Domain-Wide Delegation
  (set `delegate_email`) is the only way to act on Workspace-user
  calendars without per-user OAuth consent.
- **OAuth** — user-delegated, refresh-token-based. Required for
  personal Gmail calendars and any flow where the end user must consent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Union


_DEFAULT_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass(frozen=True)
class ServiceAccountCalendarCredentials:
    """Service-account credentials. `info` is the JSON keyfile dict
    (`json.loads(open("sa.json").read())`)."""

    info: dict
    scopes: list[str] = field(default_factory=lambda: list(_DEFAULT_CALENDAR_SCOPES))
    delegate_email: str | None = None


@dataclass(frozen=True)
class OAuthCalendarCredentials:
    """OAuth user-delegated credentials. `refresh_token` MUST be
    present — `token` (access token) is optional and refreshed
    on demand."""

    refresh_token: str
    client_id: str
    client_secret: str
    token: str | None = None
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: list[str] = field(default_factory=lambda: list(_DEFAULT_CALENDAR_SCOPES))


CalendarCredentials = Union[ServiceAccountCalendarCredentials, OAuthCalendarCredentials]


class CalendarCredentialResolver(Protocol):
    """Product-injected per-tenant credential lookup.

    Implementations resolve credentials however they store them
    (Supabase row, vault, env). Returning `None` means "no
    credentials for this tenant" — caller (factory) falls back to
    `FakeCalendarAdapter`."""

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> CalendarCredentials | None: ...


__all__ = [
    "CalendarCredentialResolver",
    "CalendarCredentials",
    "OAuthCalendarCredentials",
    "ServiceAccountCalendarCredentials",
]
