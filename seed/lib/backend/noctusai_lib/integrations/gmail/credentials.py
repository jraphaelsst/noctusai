"""Per-tenant Gmail credentials + resolver Protocol.

Gmail has **no service-account analogue** for a personal mailbox:
`users.messages.send` / `.list` / `.get` act on *a user's* mailbox, so
the only viable auth is **per-user OAuth refresh-token** (Workspace
Domain-Wide-Delegation exists but most tenants lack it — out of scope
for v1, mirroring the meta read-only-v1 narrowing). This is why the
Gmail credentials surface ships only the OAuth kind — unlike Calendar,
which also supports service accounts.

Products implement `GmailCredentialResolver` to look up credentials
per tenant (typically from Supabase or the seed `CredentialStore`).
The Real adapter consumes the Protocol — it doesn't know HOW
credentials are stored, only how to use them once resolved. Returning
`None` means "no credentials for this tenant" — the factory falls back
to `FakeGmailClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from noctusai_lib.integrations.gmail.types import GMAIL_SEND_SCOPE

_DEFAULT_GMAIL_SCOPES = [GMAIL_SEND_SCOPE]


@dataclass(frozen=True)
class OAuthGmailCredentials:
    """OAuth user-delegated Gmail credentials. `refresh_token` MUST be
    present — `token` (access token) is optional and refreshed on
    demand by `google.oauth2.credentials.Credentials`.

    `scopes` defaults to send-only; a read-touching consumer must pass
    the `gmail.readonly` scope explicitly (consent must have been
    granted for it — the seed cannot widen a scope the user never
    approved)."""

    refresh_token: str
    client_id: str
    client_secret: str
    token: str | None = None
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: list[str] = field(default_factory=lambda: list(_DEFAULT_GMAIL_SCOPES))


class GmailCredentialResolver(Protocol):
    """Product-injected per-tenant credential lookup.

    Implementations resolve credentials however they store them
    (Supabase row, `CredentialStore`, env). Returning `None` means
    "no credentials for this tenant" — the caller (factory) falls
    back to `FakeGmailClient`."""

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> OAuthGmailCredentials | None: ...


__all__ = [
    "GmailCredentialResolver",
    "OAuthGmailCredentials",
]
