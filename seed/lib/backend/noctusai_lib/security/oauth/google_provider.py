"""Google OAuth 2.0 provider — concrete implementation of `OAuthProvider`.

Lifted from the per-product Google-OAuth code that today lives in
`integrations/google_calendar/oauth_adapter.py` (server-side token
refresh via the `google.oauth2.credentials` package) and the hand-rolled
`/oauth/google/{init,callback}` router originally in the retired
`media-scheduling` product (consolidated into `social-wiring`
2026-05-16; raw httpx calls to `https://oauth2.googleapis.com/token`).

This module collapses both into a single canonical surface — the
authorization-URL builder + the four-method Protocol — so every product
that needs Google OAuth consumes the same code instead of re-deriving
it. `oauth_adapter.py` keeps working unchanged (it's a calendar-side
concern: it converts an already-resolved `OAuthCalendarCredentials` into
a Google API client). A future project will migrate google_calendar to
consume this module's `refresh()`; not in this scope.

Endpoints
---------
- Authorization: `https://accounts.google.com/o/oauth2/v2/auth`
- Token + refresh + revoke: `https://oauth2.googleapis.com/token`
- Revoke: `https://oauth2.googleapis.com/revoke`

Refresh-token semantics (the gotcha)
------------------------------------
Google issues a refresh_token ONLY on first consent or when the
authorize URL includes `prompt=consent`. Subsequent grants without that
prompt return the access token but NOT the refresh token. This module
always sets `prompt=consent` + `access_type=offline` in the consent URL
so the consumer reliably gets a refresh token. Consumers MUST never
overwrite an existing stored refresh_token with `None` — the
`oauth_router` `on_callback` hook is where that "if-present-update"
logic lives, since persistence is the consumer's concern.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from noctusai_lib.security.oauth.types import AuthorizationURL, TokenSet


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Sibling-module convention: `integrations/vista/client.py` defines
# `DEFAULT_TIMEOUT_SECONDS = 15.0`; `integrations/google_maps` uses
# `timeout=15`. Match the seed convention.
_DEFAULT_TIMEOUT = 15.0

# RFC 7636 §4.1 — verifier MUST be 43–128 chars from the unreserved set
# [A-Z a-z 0-9 - . _ ~]. `secrets.token_urlsafe(n)` returns
# 4*ceil(n/3) base64url chars from a strict subset of that alphabet
# (no padding), satisfying both length + character-class constraints.
# 64 bytes → 86 chars: well above the 43-char minimum, well below the
# 128-char maximum, ~512 bits of entropy.
_PKCE_VERIFIER_BYTES = 64


def _generate_pkce_pair() -> tuple[str, str]:
    """Return `(code_verifier, code_challenge)` per RFC 7636 §4.

    The verifier is the high-entropy random secret the consumer
    persists between authorize-redirect and callback-exchange. The
    challenge — `base64url(sha256(verifier))`, no padding — is what
    we embed in the auth URL as `code_challenge` with
    `code_challenge_method=S256`.

    Implementation note: stdlib only (`secrets` + `hashlib` + `base64`)
    so the seed grows zero new dependencies.
    """
    verifier = secrets.token_urlsafe(_PKCE_VERIFIER_BYTES)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class GoogleProvider:
    """Google OAuth 2.0 provider.

    Constructor takes the OAuth client credentials registered with
    Google Cloud Console. `http_client` is an optional pre-configured
    `httpx.AsyncClient` — useful for tests (inject a mock transport)
    or for connection pooling across many calls. When None, each
    method opens a short-lived client with `_DEFAULT_TIMEOUT`.

    Args:
        client_id: OAuth 2.0 Client ID from Google Cloud Console.
        client_secret: matching client secret.
        http_client: optional injected `httpx.AsyncClient`. When
            supplied, the caller owns its lifecycle (we don't close
            it). When None, a short-lived client is created per call.
        use_pkce: opt-in to RFC 7636 PKCE (Proof Key for Code
            Exchange). Default `False` reproduces the original
            confidential-client behavior verbatim — existing
            consumers see zero observable change. When `True`,
            `authorization_url(...)` generates a fresh
            `code_verifier`, returns it on the `AuthorizationURL`
            DTO, and appends `code_challenge=<base64url-sha256>`
            + `code_challenge_method=S256` to the consent URL;
            `exchange_code(..., code_verifier=<v>)` then includes
            the verifier in the token POST per RFC 7636 §4.5.
            Defense-in-depth even for confidential clients per
            OAuth 2.1 / Google guidance. Codified under
            `KB § PATTERNS/absorbed-product-seed-shape-seam.md` —
            the N=3 worked instance of the absorbed-product-seed-
            shape-seam pattern (the social-wiring YouTube flow
            had PKCE pre-absorption; this seam restores it
            without forking).
    """

    name: str = "google"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        use_pkce: bool = False,
    ) -> None:
        if not client_id:
            raise ValueError("GoogleProvider requires a non-empty client_id")
        if not client_secret:
            raise ValueError("GoogleProvider requires a non-empty client_secret")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_client = http_client
        self._use_pkce = use_pkce

    # ─── authorization_url ────────────────────────────────────────────────

    async def authorization_url(
        self,
        state: str,
        scopes: list[str],
        redirect_uri: str,
    ) -> AuthorizationURL:
        """Build the Google consent screen URL.

        Always includes `access_type=offline` + `prompt=consent` so the
        callback reliably returns a refresh token (see module docstring
        for the gotcha). `include_granted_scopes=true` is the
        recommended Google flag — lets the user incrementally upgrade
        scopes without revoking previous grants.

        When `use_pkce=True` (constructor flag), generates a fresh
        RFC 7636 PKCE verifier + challenge per call, appends
        `code_challenge`/`code_challenge_method=S256` to the URL, and
        returns the verifier on `AuthorizationURL.code_verifier` for
        the consumer to persist (keyed by `state`) and replay at
        `exchange_code(...)` time.
        """
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        code_verifier: str | None = None
        if self._use_pkce:
            code_verifier, code_challenge = _generate_pkce_pair()
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return AuthorizationURL(
            url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}",
            state=state,
            code_verifier=code_verifier,
        )

    # ─── exchange_code ────────────────────────────────────────────────────

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenSet:
        """POST to the Google token endpoint with `grant_type=authorization_code`.

        Returns the canonical `TokenSet`. Raises `httpx.HTTPStatusError`
        on non-2xx — the router catches it and wraps in
        `OAuthCallbackResult(error=...)`.

        When the provider is in PKCE mode (`use_pkce=True` at construction),
        a non-empty `code_verifier` MUST be supplied; we include it in the
        token POST body per RFC 7636 §4.5. Google rejects PKCE-issued
        codes when the verifier is missing or doesn't match the original
        challenge (`invalid_grant: Missing code verifier` /
        `Bad Request — invalid grant`). For non-PKCE consumers (default),
        `code_verifier=None` is correct and the body matches the
        pre-seam shape exactly.
        """
        body = {
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if self._use_pkce:
            if not code_verifier:
                raise ValueError(
                    "GoogleProvider(use_pkce=True).exchange_code() requires a "
                    "non-empty code_verifier — pass the one returned by "
                    "authorization_url(...).code_verifier."
                )
            body["code_verifier"] = code_verifier
        # Non-PKCE path (use_pkce=False, the default): body is
        # bit-identical to the pre-seam shape regardless of whether the
        # caller passes a verifier — we deliberately drop a stray
        # `code_verifier` on a non-PKCE provider so the body asserted
        # by existing back-compat tests stays untouched.
        data = await self._post(GOOGLE_TOKEN_URL, body)
        return _token_response_to_set(data)

    # ─── refresh ──────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> TokenSet:
        """POST to the token endpoint with `grant_type=refresh_token`.

        Google does NOT rotate refresh tokens — the response carries
        only a fresh access_token + expires_in. We therefore preserve
        the original `refresh_token` on the returned `TokenSet` so
        consumers can store the new TokenSet wholesale without losing
        the long-lived credential.
        """
        body = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        data = await self._post(GOOGLE_TOKEN_URL, body)
        token_set = _token_response_to_set(data)
        # Google omits refresh_token on refresh responses — preserve
        # the one the caller passed in so wholesale-replace consumers
        # don't lose it.
        if token_set.refresh_token is None:
            return TokenSet(
                access_token=token_set.access_token,
                refresh_token=refresh_token,
                expires_at=token_set.expires_at,
                scope=token_set.scope,
                raw=token_set.raw,
            )
        return token_set

    # ─── revoke ───────────────────────────────────────────────────────────

    async def revoke(self, token: str) -> None:
        """POST to `https://oauth2.googleapis.com/revoke?token=<token>`.

        Per Google docs the request body is empty; the token rides as
        the only query parameter. 200 on success; 400 on already-revoked
        is treated as success (idempotent). Other non-2xx raise.
        """
        url = f"{GOOGLE_REVOKE_URL}?{urlencode({'token': token})}"
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        try:
            response = await client.post(
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        finally:
            if owns_client:
                await client.aclose()
        # Google returns 400 with `invalid_token` for already-revoked
        # tokens — treat as idempotent success.
        if response.status_code == 400:
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if payload.get("error") in {"invalid_token", "invalid_grant"}:
                return
        response.raise_for_status()

    # ─── internals ────────────────────────────────────────────────────────

    async def _post(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        try:
            response = await client.post(url, data=data)
        finally:
            if owns_client:
                await client.aclose()
        response.raise_for_status()
        return response.json()


def _token_response_to_set(data: dict[str, Any]) -> TokenSet:
    """Map Google's token-endpoint JSON to the canonical `TokenSet`.

    Google's response shape:
      {
        "access_token": "...",
        "expires_in": 3599,        # seconds; convert to absolute datetime
        "refresh_token": "...",    # only on first-consent or prompt=consent
        "scope": "scope1 scope2",  # space-joined
        "token_type": "Bearer",
        "id_token": "..."          # OIDC, only when openid scope requested
      }

    `expires_in` is offset-from-now; we compute the absolute UTC
    `expires_at` so consumers don't repeatedly do the math.
    """
    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    scope_raw = data.get("scope", "")
    scope = scope_raw.split() if scope_raw else []
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=expires_at,
        scope=scope,
        raw=dict(data),
    )


__all__ = ["GoogleProvider", "GOOGLE_AUTH_URL", "GOOGLE_TOKEN_URL", "GOOGLE_REVOKE_URL"]
