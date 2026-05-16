"""Per-tenant Meta OAuth credentials + resolver Protocol.

Mirrors `google_calendar/credentials.py`: the seed defines the
Protocol; products implement it (Supabase row, Fernet vault, env).
The real adapter consumes the Protocol — it does NOT know HOW
credentials are stored, only how to use them once resolved. Returning
`None` means "no stored OAuth credential for this tenant"; combined
with no System User Token, the factory falls back to `FakeMetaAdapter`.

There is **one** OAuth credential kind (no service-account analogue —
Meta's identity model has no service accounts; the production path is
the workspace-global System User Token, configured separately on the
adapter, not per-tenant)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OAuthMetaCredentials:
    """A stored long-lived Meta user access token for one tenant.

    `access_token` is the **long-lived (~60d) user token** — the
    adapter resolves Page tokens fresh from `/me/accounts` on every
    construction (Page tokens can rotate; refetching is one cheap
    paged call — see session-notes §2.1). Persist the long-lived
    token only."""

    access_token: str
    user_id: str | None = None
    user_name: str | None = None


class MetaCredentialResolver(Protocol):
    """Product-injected per-tenant Meta OAuth credential lookup.

    `org_id` is the tenant key (Meta credentials are stored one row
    per `(org_id, provider="meta")`). Returning `None` means "no
    stored credential" — the factory falls back appropriately."""

    def get_credentials(
        self, org_id: str | None = None
    ) -> OAuthMetaCredentials | None: ...


__all__ = [
    "MetaCredentialResolver",
    "OAuthMetaCredentials",
]
