"""Value objects for the OAuth callback infrastructure.

Three frozen dataclasses model the three handoff points of any OAuth
authorization-code flow:

1. `AuthorizationURL` — what the consumer redirects the user to (the
   provider's consent screen). Carries the `state` parameter so the
   consumer can persist it (CSRF token + per-tenant nonce) and verify
   on callback.
2. `TokenSet` — what the provider returns from the token endpoint.
   Always contains an `access_token`; refresh tokens are
   provider-and-flow dependent (Google sends one only with
   `prompt=consent`; some providers never issue one). `raw` keeps the
   provider response intact so consumers can read provider-specific
   fields without us re-shipping them in the canonical shape.
3. `OAuthCallbackResult` — what `oauth_router` hands to the
   `on_callback` hook. Carries `error: str | None`; the router never
   raises into the response — every failure surfaces as a result with
   `error` populated, so consumers can persist a failed-attempt audit
   row without the request crashing.

Frozen on purpose: the values flow through async hooks and persistence
layers; immutability rules out subtle aliasing bugs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AuthorizationURL:
    """The URL to redirect the user to for provider consent.

    `state` MUST be the same opaque string that comes back on the
    callback query string — the consumer is responsible for persisting
    it (typically per-tenant + CSRF nonce) before redirect, and
    verifying it on callback.
    """

    url: str
    state: str


@dataclass(frozen=True)
class TokenSet:
    """Tokens returned by an OAuth token-endpoint exchange.

    `access_token` is always present. `refresh_token` may be `None`
    when the provider didn't issue one (e.g. Google without
    `prompt=consent`, or providers that simply never refresh). `scope`
    is the granted scope list as the provider returned it (not the
    requested set — providers may grant a subset or upgrade to a
    superset). `raw` is the full token-endpoint response payload so
    consumers can read provider-specific fields (`id_token`,
    `expires_in`, vendor extensions) without us flattening them.
    """

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OAuthCallbackResult:
    """The outcome of an OAuth callback round-trip.

    Handed to the `on_callback` hook the consumer registers with
    `oauth_router(...)`. `error` is `None` on success and a
    short reason-string on failure (the router maps any
    exchange/refresh exception to this field instead of bubbling it
    into the response — consumers want to persist a failed-attempt
    row without the request crashing).
    """

    provider: str
    state: str
    tokens: TokenSet | None
    error: str | None = None


__all__ = [
    "AuthorizationURL",
    "OAuthCallbackResult",
    "TokenSet",
]
