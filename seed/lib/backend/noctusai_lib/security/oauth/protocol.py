"""`OAuthProvider` Protocol — the seam every concrete provider implements.

WHY a Protocol (not an ABC)
---------------------------
Per `KB § PATTERNS/seed-fake-real-adapter.md`, IO-touching seed modules
ship in the canonical Protocol+Fake+Real+factory shape. Protocol gives
us structural typing — `FakeOAuthProvider` and `GoogleProvider` share
no inheritance edge but both satisfy the contract because they expose
the right methods. Tests + consumers depend on the contract, not on a
class hierarchy.

Naming for the callback path
----------------------------
The `name` attribute is the path segment used by `oauth_router(...)`:
`/api/oauth/<name>/callback`. Pick lowercase, no spaces, no slashes —
"google", "stripe", "slack". The factory raises if a duplicate name is
registered with the router.

All methods are async by design
-------------------------------
Token endpoints are network calls. Even the Fake declares its methods
async so consumers can write `await provider.exchange_code(...)`
without branching on provider kind. (The Fake's bodies are
non-blocking; it's pure shape parity.)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from noctusai_lib.security.oauth.types import AuthorizationURL, TokenSet


@runtime_checkable
class OAuthProvider(Protocol):
    """The contract every OAuth provider satisfies.

    `runtime_checkable` so consumers can `isinstance(p, OAuthProvider)`
    in a registry without importing every provider type.
    """

    name: str
    """Vendor name used in the callback path (`/api/oauth/<name>/callback`).

    Lowercase, no slashes, no spaces. Examples: `"google"`, `"stripe"`,
    `"slack"`. The factory + router treat this as the registry key.
    """

    async def authorization_url(
        self,
        state: str,
        scopes: list[str],
        redirect_uri: str,
    ) -> AuthorizationURL:
        """Return the URL the user should be redirected to for consent.

        `state` is the consumer-supplied opaque token (typically
        CSRF-nonce + per-tenant id, signed). `scopes` is the requested
        scope list — providers may grant a subset; the granted set
        comes back in `TokenSet.scope`. `redirect_uri` MUST exactly
        match a redirect-URI registered with the provider, otherwise
        the consent screen rejects with `redirect_uri_mismatch`.
        """
        ...

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> TokenSet:
        """Exchange an authorization code for an access + refresh token.

        Called from the `/api/oauth/<name>/callback` handler with the
        `code` and `state` Google (or any provider) appended to the
        redirect. The implementation POSTs to the token endpoint and
        returns the canonical `TokenSet`. `redirect_uri` MUST match the
        one used to obtain the code — providers reject mismatches.
        """
        ...

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Refresh an expired access token.

        Returns a `TokenSet` with a fresh `access_token` and updated
        `expires_at`. `refresh_token` field on the new TokenSet may be
        `None` (most providers re-issue rotating refresh tokens; Google
        does not — the original keeps working). Consumers persist the
        new access_token + expires_at; rotate refresh_token only if the
        new TokenSet carries one.
        """
        ...

    async def revoke(self, token: str) -> None:
        """Revoke an access OR refresh token at the provider.

        Implementations call the provider's revocation endpoint. Idempotent:
        calling on an already-revoked token returns successfully (nothing
        to undo). On network failure, raises — the consumer decides whether
        to persist a "revocation pending" row and retry.
        """
        ...


__all__ = ["OAuthProvider"]
