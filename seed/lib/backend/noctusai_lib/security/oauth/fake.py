"""`FakeOAuthProvider` — deterministic, network-free `OAuthProvider`.

Drop-in for tests + dev FakeMode where:
- Real Google / Stripe / Slack consent screens aren't available.
- Tests must be hermetic + reproducible.
- A consumer wants to exercise its own `on_callback` hook end-to-end
  without standing up an OAuth dance.

Behavior contract
-----------------
- `authorization_url(state, scopes, redirect_uri)` returns a stable
  fake URL (`https://fake.invalid/oauth/<name>/consent?...`) that
  embeds state + scopes for assertion. The redirect_uri rides as a
  query param so tests can verify it round-tripped.
- `exchange_code(code, state, redirect_uri)` returns the
  `predetermined_tokens` if supplied, otherwise a deterministic default
  (`access_token=f"fake-access-{code}"`, `refresh_token=f"fake-refresh-{code}"`,
  `expires_at=now+1h`). The `code` shows up in the access token so
  multiple round-trips in one test are distinguishable.
- `refresh(refresh_token)` returns a new TokenSet with the same
  refresh_token, a fresh access token (`fake-access-refreshed-<refresh>`),
  and `expires_at=now+1h`.
- `revoke(token)` no-ops, but appends `token` to `revoked_tokens` so
  tests can assert revocation happened. Idempotent on duplicates.

The Fake honors the canonical `Protocol+Fake+Real+factory` shape: same
interface as `GoogleProvider`, no network, fully deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from noctusai_lib.security.oauth.types import AuthorizationURL, TokenSet


class FakeOAuthProvider:
    """Deterministic OAuth provider for tests + FakeMode."""

    def __init__(
        self,
        name: str = "fake-google",
        *,
        predetermined_tokens: TokenSet | None = None,
    ) -> None:
        if not name:
            raise ValueError("FakeOAuthProvider requires a non-empty name")
        self.name = name
        self._predetermined_tokens = predetermined_tokens
        self.revoked_tokens: list[str] = []

    async def authorization_url(
        self,
        state: str,
        scopes: list[str],
        redirect_uri: str,
    ) -> AuthorizationURL:
        """Build a deterministic fake consent URL.

        Embeds state + scope + redirect_uri so tests can assert the
        consumer passed everything through. Path includes `self.name`
        so tests can disambiguate multiple Fakes.
        """
        params = {
            "scope": " ".join(scopes),
            "state": state,
            "redirect_uri": redirect_uri,
        }
        return AuthorizationURL(
            url=f"https://fake.invalid/oauth/{self.name}/consent?{urlencode(params)}",
            state=state,
        )

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> TokenSet:
        """Return `predetermined_tokens` if supplied, else a default set.

        Default tokens encode `code` so multiple round-trips in one
        test are distinguishable.
        """
        if self._predetermined_tokens is not None:
            return self._predetermined_tokens
        now = datetime.now(timezone.utc)
        return TokenSet(
            access_token=f"fake-access-{code}",
            refresh_token=f"fake-refresh-{code}",
            expires_at=now + timedelta(hours=1),
            scope=[],
            raw={"code": code, "state": state, "redirect_uri": redirect_uri},
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Return a new TokenSet with a fresh access_token + same refresh_token.

        Mirrors Google's no-rotation behavior (refresh_token preserved).
        `expires_at` advances to now+1h so tests of expiry-extension
        logic see a different value from the initial exchange.
        """
        now = datetime.now(timezone.utc)
        return TokenSet(
            access_token=f"fake-access-refreshed-{refresh_token}",
            refresh_token=refresh_token,
            expires_at=now + timedelta(hours=1),
            scope=[],
            raw={"refreshed": True, "refresh_token": refresh_token},
        )

    async def revoke(self, token: str) -> None:
        """Track the token in `revoked_tokens`. Idempotent on duplicates."""
        if token not in self.revoked_tokens:
            self.revoked_tokens.append(token)


__all__ = ["FakeOAuthProvider"]
