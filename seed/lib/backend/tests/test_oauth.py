"""Unit + integration tests for `noctusai_lib.security.oauth`.

Coverage map:
  - `FakeOAuthProvider` contract — deterministic shape, revoke tracking.
  - `GoogleProvider` — authorization URL composition + token-endpoint
    POST shape + refresh token preservation + revoke endpoint contact.
    External-service calls mocked at the `httpx.AsyncClient` boundary
    (correct shape per `KB § PATTERNS/testing.md` external-service
    carve-out).
  - `oauth_router` — round-trip via FastAPI `TestClient`: authorize /
    callback / refresh / revoke / unknown-provider 404.
  - Parity with the existing `integrations/google_calendar/oauth_adapter`
    refresh path — same token URL, same body shape.
  - `make_oauth_provider` factory — google + fake selection +
    unknown-vendor error.
  - Public-surface re-exports — `noctusai_lib.security` exposes `oauth`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.security import oauth as oauth_module
from noctusai_lib.security.oauth import (
    AuthorizationURL,
    FakeOAuthProvider,
    GoogleProvider,
    OAuthCallbackResult,
    OAuthProvider,
    TokenSet,
    make_oauth_provider,
    oauth_router,
)
from noctusai_lib.security.oauth.google_provider import (
    GOOGLE_AUTH_URL,
    GOOGLE_REVOKE_URL,
    GOOGLE_TOKEN_URL,
)


# ───────────────────────────── Public surface ─────────────────────────────


def test_security_module_exposes_oauth_submodule():
    """`from noctusai_lib.security import oauth` works after Phase 2.3."""
    from noctusai_lib.security import oauth  # noqa: F401

    assert hasattr(oauth, "OAuthProvider")
    assert hasattr(oauth, "GoogleProvider")
    assert hasattr(oauth, "FakeOAuthProvider")
    assert hasattr(oauth, "make_oauth_provider")
    assert hasattr(oauth, "oauth_router")
    assert hasattr(oauth, "AuthorizationURL")
    assert hasattr(oauth, "TokenSet")
    assert hasattr(oauth, "OAuthCallbackResult")


def test_oauth_module_all_includes_every_public_symbol():
    public = set(oauth_module.__all__)
    expected = {
            "AuthorizationURL",
            "CallbackHook",
            "FakeOAuthProvider",
            "FakeScopeResolver",
            "GoogleProvider",
            "GoogleScopeResolver",
            "MetaScopeResolver",
            "OAuthCallbackResult",
            "OAuthProvider",
            "ScopeResolver",
            "TokenSet",
            "make_oauth_provider",
            "make_scope_resolver",
            "oauth_router",
        }
    assert expected == public


def test_provider_protocol_runtime_checkable():
    """`isinstance(p, OAuthProvider)` works for the Fake."""
    fake = FakeOAuthProvider()
    assert isinstance(fake, OAuthProvider)


# ───────────────────────────── FakeOAuthProvider ──────────────────────────


@pytest.mark.asyncio
async def test_fake_authorization_url_is_deterministic():
    fake = FakeOAuthProvider(name="fake-google")
    auth = await fake.authorization_url(
        state="csrf-123",
        scopes=["scope.a", "scope.b"],
        redirect_uri="https://my-app.test/cb",
    )
    assert isinstance(auth, AuthorizationURL)
    assert auth.state == "csrf-123"
    parsed = urlparse(auth.url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "fake.invalid"
    assert "/oauth/fake-google/consent" in parsed.path
    qs = parse_qs(parsed.query)
    assert qs["state"] == ["csrf-123"]
    assert qs["scope"] == ["scope.a scope.b"]
    assert qs["redirect_uri"] == ["https://my-app.test/cb"]


@pytest.mark.asyncio
async def test_fake_exchange_code_default_tokens_carry_code():
    fake = FakeOAuthProvider()
    tokens = await fake.exchange_code(
        code="auth-code-abc", state="s1", redirect_uri="https://x.test/cb"
    )
    assert isinstance(tokens, TokenSet)
    assert tokens.access_token == "fake-access-auth-code-abc"
    assert tokens.refresh_token == "fake-refresh-auth-code-abc"
    # expires_at within the next two hours and after now
    now = datetime.now(timezone.utc)
    assert tokens.expires_at > now
    assert tokens.expires_at < now + timedelta(hours=2)
    # raw should preserve the inputs for debugging
    assert tokens.raw["code"] == "auth-code-abc"


@pytest.mark.asyncio
async def test_fake_exchange_code_returns_predetermined_tokens():
    canned = TokenSet(
        access_token="canned-access",
        refresh_token="canned-refresh",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scope=["scope.x"],
        raw={"canned": True},
    )
    fake = FakeOAuthProvider(predetermined_tokens=canned)
    tokens = await fake.exchange_code(
        code="ignored", state="ignored", redirect_uri="ignored"
    )
    assert tokens is canned


@pytest.mark.asyncio
async def test_fake_refresh_extends_expiry_keeps_refresh_token():
    fake = FakeOAuthProvider()
    new = await fake.refresh(refresh_token="rt-xyz")
    assert new.refresh_token == "rt-xyz"
    assert new.access_token == "fake-access-refreshed-rt-xyz"
    assert new.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_fake_revoke_tracks_tokens_idempotently():
    fake = FakeOAuthProvider()
    await fake.revoke("tok-1")
    await fake.revoke("tok-2")
    await fake.revoke("tok-1")  # idempotent — no duplicate
    assert fake.revoked_tokens == ["tok-1", "tok-2"]


def test_fake_rejects_empty_name():
    with pytest.raises(ValueError, match="non-empty name"):
        FakeOAuthProvider(name="")


# ───────────────────────────── GoogleProvider ─────────────────────────────


def test_google_provider_rejects_empty_credentials():
    with pytest.raises(ValueError, match="client_id"):
        GoogleProvider(client_id="", client_secret="cs")
    with pytest.raises(ValueError, match="client_secret"):
        GoogleProvider(client_id="ci", client_secret="")


@pytest.mark.asyncio
async def test_google_authorization_url_includes_canonical_params():
    provider = GoogleProvider(client_id="my-client", client_secret="my-secret")
    auth = await provider.authorization_url(
        state="csrf-state",
        scopes=["openid", "https://www.googleapis.com/auth/calendar"],
        redirect_uri="https://app.test/oauth/google/callback",
    )
    parsed = urlparse(auth.url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == GOOGLE_AUTH_URL
    qs = parse_qs(parsed.query)
    # The four offline-refresh-token-reliable flags MUST be set; that's
    # parity with the retired `media-scheduling` product's
    # `routers/oauth.py::_consent_url` (consolidated into `social-wiring`
    # 2026-05-16).
    assert qs["client_id"] == ["my-client"]
    assert qs["redirect_uri"] == ["https://app.test/oauth/google/callback"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["openid https://www.googleapis.com/auth/calendar"]
    assert qs["access_type"] == ["offline"]
    assert qs["prompt"] == ["consent"]
    assert qs["include_granted_scopes"] == ["true"]
    assert qs["state"] == ["csrf-state"]
    assert auth.state == "csrf-state"


def _mock_async_client_returning(json_payload: dict, status_code: int = 200):
    """Helper — build a mock httpx.AsyncClient context manager that
    returns the given JSON on POST."""
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=json_payload)
    response.raise_for_status = MagicMock(
        side_effect=(
            httpx.HTTPStatusError(
                "boom", request=MagicMock(), response=response
            )
            if status_code >= 400
            else None
        )
    )

    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.aclose = AsyncMock(return_value=None)
    # context-manager interface (we don't use it but guard regression)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_google_exchange_code_posts_to_token_endpoint():
    """GoogleProvider.exchange_code() POSTs the canonical body to
    `https://oauth2.googleapis.com/token`."""
    payload = {
        "access_token": "ya29.access",
        "refresh_token": "1//refresh",
        "expires_in": 3599,
        "scope": "openid email",
        "token_type": "Bearer",
    }
    mock_client = _mock_async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = GoogleProvider(client_id="cid", client_secret="cs")
        tokens = await provider.exchange_code(
            code="auth-code-xyz",
            state="s",
            redirect_uri="https://app/cb",
        )
    # Endpoint hit
    mock_client.post.assert_awaited_once()
    call = mock_client.post.await_args
    assert call.args[0] == GOOGLE_TOKEN_URL
    body = call.kwargs["data"]
    assert body == {
        "code": "auth-code-xyz",
        "client_id": "cid",
        "client_secret": "cs",
        "redirect_uri": "https://app/cb",
        "grant_type": "authorization_code",
    }
    # Token mapping
    assert tokens.access_token == "ya29.access"
    assert tokens.refresh_token == "1//refresh"
    assert tokens.scope == ["openid", "email"]
    # expires_at is approx now + 3599s
    delta = tokens.expires_at - datetime.now(timezone.utc)
    assert timedelta(seconds=3500) < delta < timedelta(seconds=3700)
    # raw preserves the full payload
    assert tokens.raw == payload


@pytest.mark.asyncio
async def test_google_refresh_preserves_refresh_token_when_provider_omits_it():
    """Google does NOT rotate refresh tokens — the response carries
    only access_token + expires_in. Provider must preserve the original."""
    payload = {
        "access_token": "ya29.fresh",
        "expires_in": 3600,
        "scope": "openid email",
        "token_type": "Bearer",
    }
    mock_client = _mock_async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = GoogleProvider(client_id="cid", client_secret="cs")
        tokens = await provider.refresh(refresh_token="original-rt")
    # Endpoint contract
    call = mock_client.post.await_args
    assert call.args[0] == GOOGLE_TOKEN_URL
    body = call.kwargs["data"]
    assert body == {
        "client_id": "cid",
        "client_secret": "cs",
        "refresh_token": "original-rt",
        "grant_type": "refresh_token",
    }
    # Refresh-token preserved despite Google's omission
    assert tokens.refresh_token == "original-rt"
    assert tokens.access_token == "ya29.fresh"


@pytest.mark.asyncio
async def test_google_refresh_passes_through_when_provider_rotates():
    """Some providers re-issue refresh tokens — preserve those instead."""
    payload = {
        "access_token": "ya29.fresh",
        "refresh_token": "1//rotated",
        "expires_in": 3600,
        "scope": "openid",
        "token_type": "Bearer",
    }
    mock_client = _mock_async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = GoogleProvider(client_id="cid", client_secret="cs")
        tokens = await provider.refresh(refresh_token="original-rt")
    assert tokens.refresh_token == "1//rotated"


@pytest.mark.asyncio
async def test_google_revoke_hits_revoke_endpoint():
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.aclose = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=client):
        provider = GoogleProvider(client_id="cid", client_secret="cs")
        await provider.revoke("tok-to-revoke")
    call = client.post.await_args
    url = call.args[0]
    assert url.startswith(GOOGLE_REVOKE_URL)
    assert "token=tok-to-revoke" in url


@pytest.mark.asyncio
async def test_google_revoke_treats_invalid_token_400_as_success():
    """Idempotent revoke: 400 with `error=invalid_token` is a no-op."""
    response = MagicMock()
    response.status_code = 400
    response.json = MagicMock(return_value={"error": "invalid_token"})
    response.raise_for_status = MagicMock(side_effect=AssertionError("should not be called"))
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.aclose = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=client):
        provider = GoogleProvider(client_id="cid", client_secret="cs")
        # Must not raise
        await provider.revoke("already-revoked-tok")


@pytest.mark.asyncio
async def test_google_provider_uses_injected_http_client_without_closing():
    """When http_client is injected, GoogleProvider must NOT close it."""
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(
        return_value={
            "access_token": "a",
            "expires_in": 3600,
            "scope": "",
            "token_type": "Bearer",
        }
    )
    response.raise_for_status = MagicMock()

    injected = MagicMock()
    injected.post = AsyncMock(return_value=response)
    injected.aclose = AsyncMock(return_value=None)

    provider = GoogleProvider(
        client_id="cid", client_secret="cs", http_client=injected
    )
    await provider.exchange_code(code="c", state="s", redirect_uri="r")
    injected.aclose.assert_not_awaited()


# ───────────────────── Parity with calendar oauth_adapter ─────────────────


def test_google_token_url_matches_calendar_adapter_default():
    """Existing `OAuthCalendarCredentials.token_uri` defaults to
    `https://oauth2.googleapis.com/token` — the new generic provider
    MUST hit the same endpoint so a future migration is shape-neutral."""
    from noctusai_lib.integrations.google_calendar.credentials import (
        OAuthCalendarCredentials,
    )

    sample = OAuthCalendarCredentials(
        refresh_token="rt", client_id="ci", client_secret="cs"
    )
    assert sample.token_uri == GOOGLE_TOKEN_URL


# ───────────────────────────── Factory ────────────────────────────────────


def test_make_oauth_provider_google_returns_google_provider():
    p = make_oauth_provider("google", client_id="ci", client_secret="cs")
    assert isinstance(p, GoogleProvider)
    assert p.name == "google"


def test_make_oauth_provider_use_fake_short_circuits_for_any_name():
    p = make_oauth_provider("stripe", use_fake=True)
    assert isinstance(p, FakeOAuthProvider)
    assert p.name == "stripe"


def test_make_oauth_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider: stripe"):
        make_oauth_provider("stripe", client_id="x", client_secret="y")


def test_make_oauth_provider_google_requires_credentials():
    with pytest.raises(ValueError, match="client_id"):
        make_oauth_provider("google")


# ───────────────────────────── oauth_router ────────────────────────────────


def _build_app_with_router(*providers, on_callback=None):
    """Wrap the router in a fresh FastAPI app for `TestClient`."""
    app = FastAPI()
    app.include_router(oauth_router(*providers, on_callback=on_callback))
    return TestClient(app)


def test_oauth_router_requires_at_least_one_provider():
    with pytest.raises(ValueError, match="at least one"):
        oauth_router()


def test_oauth_router_rejects_duplicate_provider_names():
    a = FakeOAuthProvider(name="dup")
    b = FakeOAuthProvider(name="dup")
    with pytest.raises(ValueError, match="duplicate provider name"):
        oauth_router(a, b)


def test_oauth_router_authorize_returns_url():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.get(
        "/api/oauth/vendor-a/authorize",
        params={
            "state": "csrf-1",
            "redirect_uri": "https://app/cb",
            "scopes": ["scope.a", "scope.b"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "csrf-1"
    assert "fake.invalid" in payload["url"]
    assert "scope=scope.a+scope.b" in payload["url"]


def test_oauth_router_authorize_unknown_provider_returns_404():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.get(
        "/api/oauth/no-such-vendor/authorize",
        params={"state": "s", "redirect_uri": "r"},
    )
    assert response.status_code == 404
    assert "unknown provider" in response.json()["detail"]


def test_oauth_router_callback_invokes_on_callback_with_tokens():
    fake = FakeOAuthProvider(name="vendor-a")
    seen: list[OAuthCallbackResult] = []

    async def hook(result: OAuthCallbackResult) -> None:
        seen.append(result)

    client = _build_app_with_router(fake, on_callback=hook)
    response = client.get(
        "/api/oauth/vendor-a/callback",
        params={
            "code": "auth-code",
            "state": "csrf-1",
            "redirect_uri": "https://app/cb",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["state"] == "csrf-1"

    assert len(seen) == 1
    result = seen[0]
    assert result.provider == "vendor-a"
    assert result.tokens is not None
    assert result.tokens.access_token == "fake-access-auth-code"


def test_oauth_router_callback_with_provider_error_query_param_skips_exchange():
    fake = FakeOAuthProvider(name="vendor-a")
    seen: list[OAuthCallbackResult] = []

    async def hook(result: OAuthCallbackResult) -> None:
        seen.append(result)

    client = _build_app_with_router(fake, on_callback=hook)
    response = client.get(
        "/api/oauth/vendor-a/callback",
        params={
            "error": "access_denied",
            "state": "csrf-1",
            "redirect_uri": "https://app/cb",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == "access_denied"
    assert seen[0].tokens is None
    assert seen[0].error == "access_denied"


def test_oauth_router_callback_missing_code_surfaces_as_result_error():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.get(
        "/api/oauth/vendor-a/callback",
        params={"state": "csrf-1", "redirect_uri": "https://app/cb"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "missing authorization code" in payload["error"]


def test_oauth_router_callback_exchange_failure_does_not_500():
    """`exchange_code` raising must NEVER bubble as a 5xx into the response."""

    class ExplodingProvider:
        name = "boom"

        async def authorization_url(self, state, scopes, redirect_uri):
            raise NotImplementedError

        async def exchange_code(self, code, state, redirect_uri):
            raise httpx.HTTPStatusError(
                "boom",
                request=MagicMock(),
                response=MagicMock(status_code=400, text="bad code"),
            )

        async def refresh(self, refresh_token):
            raise NotImplementedError

        async def revoke(self, token):
            raise NotImplementedError

    seen: list[OAuthCallbackResult] = []

    async def hook(result: OAuthCallbackResult) -> None:
        seen.append(result)

    client = _build_app_with_router(ExplodingProvider(), on_callback=hook)
    response = client.get(
        "/api/oauth/boom/callback",
        params={
            "code": "x",
            "state": "s",
            "redirect_uri": "r",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "exchange failed" in response.json()["error"]
    assert seen[0].tokens is None


def test_oauth_router_refresh_returns_token_set_shape():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.post(
        "/api/oauth/vendor-a/refresh", json={"refresh_token": "rt-1"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "fake-access-refreshed-rt-1"
    assert payload["refresh_token"] == "rt-1"
    assert "expires_at" in payload
    # ISO-format parseable
    datetime.fromisoformat(payload["expires_at"])


def test_oauth_router_refresh_rejects_missing_token():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.post("/api/oauth/vendor-a/refresh", json={})
    assert response.status_code == 400


def test_oauth_router_refresh_502_on_provider_failure():
    class FlakyProvider:
        name = "flaky"

        async def authorization_url(self, state, scopes, redirect_uri):
            raise NotImplementedError

        async def exchange_code(self, code, state, redirect_uri):
            raise NotImplementedError

        async def refresh(self, refresh_token):
            raise httpx.ConnectError("boom")

        async def revoke(self, token):
            raise NotImplementedError

    client = _build_app_with_router(FlakyProvider())
    response = client.post(
        "/api/oauth/flaky/refresh", json={"refresh_token": "rt"}
    )
    assert response.status_code == 502
    assert "refresh failed" in response.json()["error"]


def test_oauth_router_revoke_returns_204_and_calls_provider():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.post(
        "/api/oauth/vendor-a/revoke", json={"token": "tok-1"}
    )
    assert response.status_code == 204
    assert fake.revoked_tokens == ["tok-1"]


def test_oauth_router_revoke_rejects_missing_token():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.post("/api/oauth/vendor-a/revoke", json={})
    assert response.status_code == 400


def test_oauth_router_unknown_provider_returns_404_on_all_endpoints():
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    for method, path in [
        ("get", "/api/oauth/nope/authorize?state=s&redirect_uri=r"),
        ("get", "/api/oauth/nope/callback?state=s&redirect_uri=r&code=c"),
    ]:
        response = client.request(method, path)
        assert response.status_code == 404, (method, path)
    response = client.post(
        "/api/oauth/nope/refresh", json={"refresh_token": "rt"}
    )
    assert response.status_code == 404
    response = client.post("/api/oauth/nope/revoke", json={"token": "t"})
    assert response.status_code == 404


def test_oauth_router_works_without_on_callback_hook():
    """If consumer doesn't pass `on_callback`, the callback path still
    succeeds — returns the result echo and that's it."""
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)  # no hook
    response = client.get(
        "/api/oauth/vendor-a/callback",
        params={
            "code": "c",
            "state": "s",
            "redirect_uri": "r",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_oauth_router_on_callback_hook_failure_surfaces_in_response():
    """A failing hook MUST NOT crash the response — the failure shows
    up in the body's `error` field instead."""
    fake = FakeOAuthProvider(name="vendor-a")

    async def explosive_hook(result: OAuthCallbackResult) -> None:
        raise RuntimeError("DB is down")

    client = _build_app_with_router(fake, on_callback=explosive_hook)
    response = client.get(
        "/api/oauth/vendor-a/callback",
        params={
            "code": "c",
            "state": "s",
            "redirect_uri": "r",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "on_callback hook failed" in payload["error"]


# ───────────────────────────── Encrypted-tokens compose ───────────────────


def test_encrypted_tokens_helper_round_trips_a_real_oauth_token():
    """Sanity check that the at-rest encryption helper recommended for
    `on_callback` persistence round-trips the token shape we produce."""
    from noctusai_lib.security.encrypted_tokens import (
        decrypt,
        encrypt,
        generate_key,
    )

    key = generate_key()
    access = "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    refresh = "1//09rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr"
    assert decrypt(encrypt(access, key), key) == access
    assert decrypt(encrypt(refresh, key), key) == refresh


# ──────────────── oauth_router prefix / callback_paths seam ────────────────
# Phase 3a: back-compat-defaulted seam so an absorbed product with
# pre-registered Google-Cloud-Console redirect URIs can preserve them.


def test_oauth_router_default_prefix_is_unchanged():
    """No prefix arg → endpoints stay under the historical /api/oauth."""
    fake = FakeOAuthProvider(name="vendor-a")
    client = _build_app_with_router(fake)
    response = client.get(
        "/api/oauth/vendor-a/callback",
        params={"code": "c", "state": "s", "redirect_uri": "r"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True


def test_oauth_router_custom_prefix_mounts_all_endpoints_there():
    """A custom prefix moves every endpoint; the old /api/oauth path 404s."""
    fake = FakeOAuthProvider(name="vendor-a")
    app = FastAPI()
    app.include_router(oauth_router(fake, prefix="/custom/auth"))
    client = TestClient(app)

    ok = client.get(
        "/custom/auth/vendor-a/callback",
        params={"code": "c", "state": "s", "redirect_uri": "r"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True

    authz = client.get(
        "/custom/auth/vendor-a/authorize",
        params={"state": "s", "redirect_uri": "r"},
    )
    assert authz.status_code == 200, authz.text

    # Old prefix is gone.
    gone = client.get(
        "/api/oauth/vendor-a/callback",
        params={"code": "c", "state": "s", "redirect_uri": "r"},
    )
    assert gone.status_code == 404


def test_oauth_router_callback_paths_preserves_legacy_absolute_path():
    """A provider in callback_paths gets its callback at the exact
    absolute legacy path, independent of `prefix` — the absorbed-product
    pre-registered-redirect-URI seam."""
    captured: list = []

    async def hook(result: OAuthCallbackResult) -> None:
        captured.append(result)

    yt = FakeOAuthProvider(name="youtube")
    cal = FakeOAuthProvider(name="calendar")
    app = FastAPI()
    app.include_router(
        oauth_router(
            yt,
            cal,
            on_callback=hook,
            prefix="/api/oauth",
            callback_paths={
                "youtube": "/api/youtube/oauth/callback",
                "calendar": "/api/calendar/oauth/callback",
            },
        )
    )
    client = TestClient(app)

    yt_resp = client.get(
        "/api/youtube/oauth/callback",
        params={"code": "ytcode", "state": "org:1", "redirect_uri": "r"},
    )
    assert yt_resp.status_code == 200, yt_resp.text
    assert yt_resp.json()["ok"] is True
    assert yt_resp.json()["provider"] == "youtube"

    cal_resp = client.get(
        "/api/calendar/oauth/callback",
        params={"code": "calcode", "state": "org:2", "redirect_uri": "r"},
    )
    assert cal_resp.status_code == 200, cal_resp.text
    assert cal_resp.json()["provider"] == "calendar"

    # Hook fired for both, tokens carried.
    assert {r.provider for r in captured} == {"youtube", "calendar"}
    assert all(r.tokens is not None for r in captured)

    # The default <prefix>/{provider}/callback is NOT mounted for an
    # overridden provider — the legacy path is the only callback surface.
    default = client.get(
        "/api/oauth/youtube/callback",
        params={"code": "c", "state": "s", "redirect_uri": "r"},
    )
    assert default.status_code == 404

    # Non-callback endpoints still live under `prefix` for the
    # overridden provider (only the callback path moves).
    authz = client.get(
        "/api/oauth/youtube/authorize",
        params={"state": "s", "redirect_uri": "r"},
    )
    assert authz.status_code == 200, authz.text


def test_oauth_router_callback_paths_unknown_provider_raises():
    """callback_paths referencing an unregistered provider fails loud at
    construction — not silently ignored."""
    fake = FakeOAuthProvider(name="vendor-a")
    with pytest.raises(ValueError, match="unknown provider"):
        oauth_router(fake, callback_paths={"not-registered": "/x/cb"})


def test_oauth_router_callback_paths_default_none_is_full_back_compat():
    """callback_paths=None (default) → every provider keeps the default
    <prefix>/{provider}/callback; identical to the pre-seam behavior."""
    fake = FakeOAuthProvider(name="vendor-a")
    app = FastAPI()
    app.include_router(oauth_router(fake, callback_paths=None))
    client = TestClient(app)
    resp = client.get(
        "/api/oauth/vendor-a/callback",
        params={"code": "c", "state": "s", "redirect_uri": "r"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


# ──────────────── Phase 3c: PKCE seam (use_pkce flag) ────────────────────
# The N=3 worked instance of the absorbed-product-seed-shape-seam pattern
# (see `KB § PATTERNS/absorbed-product-seed-shape-seam.md`). social-wiring's
# YouTube OAuth flow had PKCE pre-absorption via the `google_auth_oauthlib`
# default; the seed `GoogleProvider` was a confidential-client flow without
# PKCE. The `use_pkce=False` default + this seam restores PKCE for social-
# wiring (and any future absorbed PKCE consumer) without degrading the
# seed's security posture or forking the consumer.


# Back-compat (use_pkce=False default) — proven, not asserted
def test_google_provider_default_use_pkce_is_false_back_compat():
    """Constructor default `use_pkce=False` — existing consumers see
    bit-identical behavior."""
    provider = GoogleProvider(client_id="ci", client_secret="cs")
    # The flag is private; we assert behavior in the URL test below. This
    # test pins the constructor signature default.
    import inspect

    sig = inspect.signature(GoogleProvider.__init__)
    assert sig.parameters["use_pkce"].default is False


@pytest.mark.asyncio
async def test_google_authorization_url_use_pkce_false_omits_pkce_params():
    """`use_pkce=False` (default) — URL matches the pre-seam shape, no
    `code_challenge` / `code_challenge_method`; `code_verifier` is None
    on the returned `AuthorizationURL`."""
    provider = GoogleProvider(client_id="my-client", client_secret="my-secret")
    auth = await provider.authorization_url(
        state="csrf-state",
        scopes=["openid"],
        redirect_uri="https://app.test/cb",
    )
    qs = parse_qs(urlparse(auth.url).query)
    assert "code_challenge" not in qs
    assert "code_challenge_method" not in qs
    assert auth.code_verifier is None


# PKCE-on — authorization_url
@pytest.mark.asyncio
async def test_google_authorization_url_use_pkce_true_emits_challenge_and_verifier():
    """`use_pkce=True` → URL carries `code_challenge` +
    `code_challenge_method=S256`; the verifier comes back to the consumer
    on `AuthorizationURL.code_verifier` for replay at exchange time."""
    provider = GoogleProvider(
        client_id="my-client", client_secret="my-secret", use_pkce=True
    )
    auth = await provider.authorization_url(
        state="csrf-state",
        scopes=["openid"],
        redirect_uri="https://app.test/cb",
    )
    qs = parse_qs(urlparse(auth.url).query)
    assert qs["code_challenge_method"] == ["S256"]
    challenge = qs["code_challenge"][0]
    # Base64url-no-padding of a SHA256 digest → 43 chars
    assert len(challenge) == 43
    # Only the unreserved-no-padding alphabet
    assert all(c.isalnum() or c in "-_" for c in challenge)
    # Verifier comes back; RFC 7636 §4.1 length 43-128
    assert auth.code_verifier is not None
    assert 43 <= len(auth.code_verifier) <= 128
    assert all(c.isalnum() or c in "-._~" for c in auth.code_verifier)


@pytest.mark.asyncio
async def test_google_authorization_url_use_pkce_true_verifier_matches_challenge():
    """The `code_verifier` returned MUST hash to the embedded
    `code_challenge` per RFC 7636 §4.2 (sha256 + base64url-no-padding)."""
    import base64
    import hashlib

    provider = GoogleProvider(
        client_id="ci", client_secret="cs", use_pkce=True
    )
    auth = await provider.authorization_url(
        state="s", scopes=["openid"], redirect_uri="https://app.test/cb"
    )
    assert auth.code_verifier is not None
    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(auth.code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    qs = parse_qs(urlparse(auth.url).query)
    assert qs["code_challenge"] == [expected_challenge]


@pytest.mark.asyncio
async def test_google_authorization_url_each_call_generates_fresh_pkce_pair():
    """A fresh verifier MUST be generated per call — never reused across
    flows. (Anti-pattern: instance-level caching of the verifier.)"""
    provider = GoogleProvider(
        client_id="ci", client_secret="cs", use_pkce=True
    )
    a = await provider.authorization_url(
        state="s1", scopes=["openid"], redirect_uri="r"
    )
    b = await provider.authorization_url(
        state="s2", scopes=["openid"], redirect_uri="r"
    )
    assert a.code_verifier != b.code_verifier


# PKCE-on — exchange_code
@pytest.mark.asyncio
async def test_google_exchange_code_use_pkce_true_includes_verifier_in_body():
    """`exchange_code(..., code_verifier=<v>)` on a PKCE-mode provider
    posts the verifier in the token body per RFC 7636 §4.5."""
    payload = {
        "access_token": "ya29.access",
        "refresh_token": "1//refresh",
        "expires_in": 3599,
        "scope": "openid",
        "token_type": "Bearer",
    }
    mock_client = _mock_async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = GoogleProvider(
            client_id="cid", client_secret="cs", use_pkce=True
        )
        await provider.exchange_code(
            code="auth-code-xyz",
            state="s",
            redirect_uri="https://app/cb",
            code_verifier="verifier-abc-123",
        )
    body = mock_client.post.await_args.kwargs["data"]
    assert body == {
        "code": "auth-code-xyz",
        "client_id": "cid",
        "client_secret": "cs",
        "redirect_uri": "https://app/cb",
        "grant_type": "authorization_code",
        "code_verifier": "verifier-abc-123",
    }


@pytest.mark.asyncio
async def test_google_exchange_code_use_pkce_true_missing_verifier_raises_loud():
    """PKCE-mode provider + missing verifier ⇒ ValueError at the
    consumer's call site (loud, before any network attempt). Without this
    the token endpoint returns Google's `invalid_grant: Missing code
    verifier` and the consumer has to chase the failure across logs."""
    provider = GoogleProvider(
        client_id="cid", client_secret="cs", use_pkce=True
    )
    with pytest.raises(ValueError, match="code_verifier"):
        await provider.exchange_code(
            code="c", state="s", redirect_uri="r"
        )
    with pytest.raises(ValueError, match="code_verifier"):
        await provider.exchange_code(
            code="c", state="s", redirect_uri="r", code_verifier=""
        )


@pytest.mark.asyncio
async def test_google_exchange_code_use_pkce_true_mismatched_verifier_fails_per_google_contract():
    """Mismatched verifier ⇒ Google returns 400 with
    `invalid_grant`. The provider surfaces this as an
    `httpx.HTTPStatusError` (the router wraps it in
    `OAuthCallbackResult.error`)."""
    payload = {"error": "invalid_grant", "error_description": "Bad code verifier"}
    mock_client = _mock_async_client_returning(payload, status_code=400)
    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = GoogleProvider(
            client_id="cid", client_secret="cs", use_pkce=True
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provider.exchange_code(
                code="c",
                state="s",
                redirect_uri="r",
                code_verifier="wrong-verifier",
            )


# Fake parity — same shape as Real
@pytest.mark.asyncio
async def test_fake_provider_use_pkce_default_false_back_compat():
    """`FakeOAuthProvider()` default — `use_pkce=False`, URL has no PKCE
    params, `code_verifier` is None. Existing consumer tests using the
    Fake see zero change."""
    fake = FakeOAuthProvider()
    auth = await fake.authorization_url(
        state="s", scopes=["scope.a"], redirect_uri="https://x.test/cb"
    )
    assert auth.code_verifier is None
    qs = parse_qs(urlparse(auth.url).query)
    assert "code_challenge" not in qs
    assert "code_challenge_method" not in qs


@pytest.mark.asyncio
async def test_fake_provider_use_pkce_true_mirrors_real_shape():
    """`FakeOAuthProvider(use_pkce=True)` mirrors `GoogleProvider`'s
    PKCE shape — same `code_challenge_method=S256`, verifier returned,
    verifier hashes to challenge. Consumer tests using the Fake exercise
    the same code-paths the Real does."""
    import base64
    import hashlib

    fake = FakeOAuthProvider(use_pkce=True)
    auth = await fake.authorization_url(
        state="s", scopes=["openid"], redirect_uri="https://x.test/cb"
    )
    qs = parse_qs(urlparse(auth.url).query)
    assert qs["code_challenge_method"] == ["S256"]
    assert auth.code_verifier is not None
    assert 43 <= len(auth.code_verifier) <= 128
    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(auth.code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    assert qs["code_challenge"] == [expected_challenge]


@pytest.mark.asyncio
async def test_fake_provider_use_pkce_true_round_trip_carries_verifier_in_raw():
    """Round-trip via the Fake: authorize → persist verifier →
    exchange_code with it. Verifier rides into `TokenSet.raw` so a
    consumer test can assert end-to-end shape parity."""
    fake = FakeOAuthProvider(use_pkce=True)
    auth = await fake.authorization_url(
        state="csrf", scopes=["openid"], redirect_uri="https://x.test/cb"
    )
    assert auth.code_verifier is not None
    tokens = await fake.exchange_code(
        code="ac", state="csrf", redirect_uri="https://x.test/cb",
        code_verifier=auth.code_verifier,
    )
    assert tokens.raw["code_verifier"] == auth.code_verifier


@pytest.mark.asyncio
async def test_fake_provider_use_pkce_true_missing_verifier_raises_loud():
    """Fake mirrors Real's loud failure: PKCE-on Fake + missing
    verifier ⇒ ValueError, same message-shape as the Real."""
    fake = FakeOAuthProvider(use_pkce=True)
    with pytest.raises(ValueError, match="code_verifier"):
        await fake.exchange_code(code="c", state="s", redirect_uri="r")


def test_authorization_url_dataclass_has_default_none_code_verifier():
    """`AuthorizationURL(url, state)` (no `code_verifier`) MUST still
    construct — the field defaults to `None` so existing pre-PKCE
    constructors keep working without change."""
    au = AuthorizationURL(url="https://x", state="s")
    assert au.code_verifier is None
