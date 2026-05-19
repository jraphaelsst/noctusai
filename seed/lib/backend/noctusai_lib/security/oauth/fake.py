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

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from noctusai_lib.security.oauth.types import AuthorizationURL, TokenSet


class FakeOAuthProvider:
    """Deterministic OAuth provider for tests + FakeMode.

    Mirrors `GoogleProvider`'s PKCE seam (`use_pkce` flag) so consumer
    tests using the Fake exercise the same code-paths the Real does —
    see `KB § PATTERNS/absorbed-product-seed-shape-seam.md` for the
    methodology pattern (the Fake-mirrors-Real point of clause 4 §3).
    """

    def __init__(
        self,
        name: str = "fake-google",
        *,
        predetermined_tokens: TokenSet | None = None,
        use_pkce: bool = False,
    ) -> None:
        if not name:
            raise ValueError("FakeOAuthProvider requires a non-empty name")
        self.name = name
        self._predetermined_tokens = predetermined_tokens
        self._use_pkce = use_pkce
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

        When `use_pkce=True` (constructor flag, default `False`),
        mirrors `GoogleProvider`: generates a verifier + challenge per
        call, appends `code_challenge`/`code_challenge_method=S256` to
        the URL, and returns the verifier on
        `AuthorizationURL.code_verifier`.
        """
        params: dict[str, str] = {
            "scope": " ".join(scopes),
            "state": state,
            "redirect_uri": redirect_uri,
        }
        code_verifier: str | None = None
        if self._use_pkce:
            # Same construction as GoogleProvider — stdlib only.
            # Duplicating the 3 lines here (vs importing the private
            # helper) keeps the Fake import-graph independent of the
            # Real and avoids a sibling cycle.
            code_verifier = secrets.token_urlsafe(64)
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            challenge = (
                base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            )
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        return AuthorizationURL(
            url=f"https://fake.invalid/oauth/{self.name}/consent?{urlencode(params)}",
            state=state,
            code_verifier=code_verifier,
        )

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenSet:
        """Return `predetermined_tokens` if supplied, else a default set.

        Default tokens encode `code` so multiple round-trips in one
        test are distinguishable.

        When the Fake is in PKCE mode (`use_pkce=True`), a non-empty
        `code_verifier` MUST be supplied — mirrors Google's contract.
        The verifier rides through to the returned TokenSet's `raw`
        dict so tests can assert the round-trip.
        """
        if self._use_pkce and not code_verifier:
            raise ValueError(
                "FakeOAuthProvider(use_pkce=True).exchange_code() requires a "
                "non-empty code_verifier — pass the one returned by "
                "authorization_url(...).code_verifier."
            )
        if self._predetermined_tokens is not None:
            return self._predetermined_tokens
        now = datetime.now(timezone.utc)
        raw: dict = {
            "code": code,
            "state": state,
            "redirect_uri": redirect_uri,
        }
        if code_verifier is not None:
            raw["code_verifier"] = code_verifier
        return TokenSet(
            access_token=f"fake-access-{code}",
            refresh_token=f"fake-refresh-{code}",
            expires_at=now + timedelta(hours=1),
            scope=[],
            raw=raw,
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
