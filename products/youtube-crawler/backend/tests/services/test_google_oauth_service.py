"""Tests for `app.services.google_oauth_service`.

Covers:
  - the `make_google_oauth_service` factory with `use_fake=True`
  - initiate → callback → status → disconnect lifecycle against the seed
    `FakeOAuthProvider` (network-free)
  - state-nonce CSRF guard (unknown / expired nonces rejected)
  - the empty-refresh-token defensive error

The Supabase client is a `MagicMock` whose `.schema(...).table(...)`
chain returns controllable handles — same shape as
`products/imobi-scheduling/backend/tests/services/test_tool_audit.py`
(N=2 adopter — pattern proven). The seed `FakeOAuthProvider` is the
canonical Fake of `OAuthProvider`, so no monkey-patching of our own
code happens.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from noctusai_lib.security.oauth import FakeOAuthProvider, TokenSet

from app.services.credential_vault import VaultService
from app.services.google_oauth_service import (
    DEFAULT_SCOPES,
    GoogleOAuthService,
    make_google_oauth_service,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def vault() -> VaultService:
    return VaultService(key=Fernet.generate_key())


@pytest.fixture
def admin_client() -> MagicMock:
    """A MagicMock whose `.schema(...).table(...)` chain is inspectable.

    Tests assert on `.insert.call_args` / `.update.call_args` to verify
    payloads. SELECT chains are configured per-test via
    `_set_select_result(admin_client, [...])`.
    """
    return MagicMock(name="admin_client")


def _table_handle(admin_client: MagicMock) -> MagicMock:
    """The terminal `.table("google_credentials")` handle.

    Reaches through `.schema("youtube_crawler").table("google_credentials")`.
    """
    return admin_client.schema.return_value.table.return_value


def _set_select_result(
    admin_client: MagicMock,
    rows: list[dict[str, Any]],
) -> None:
    """Configure the chain `.select(...).eq(...).eq(...).execute()` to
    return `MagicMock(data=rows)`.

    The chain on the real Supabase client returns self for filter ops and
    a `Response`-shaped object on `execute()`. MagicMock auto-chains
    `return_value`, so we just need the `.execute.return_value`."""
    response = MagicMock()
    response.data = rows
    handle = _table_handle(admin_client)
    # Multiple select-chain endpoints exist (select→eq→eq→.execute(),
    # select→eq→eq→limit→execute()); MagicMock handles all because every
    # chain step returns the same `return_value` recursively.
    handle.select.return_value.eq.return_value.eq.return_value.execute.return_value = response
    handle.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = response
    handle.select.return_value.eq.return_value.limit.return_value.execute.return_value = response


def _make_service(
    *,
    vault: VaultService,
    admin_client: MagicMock,
    fake_provider: FakeOAuthProvider | None = None,
) -> GoogleOAuthService:
    """Build a service wired with the Fake provider + the MagicMock client."""
    provider = fake_provider or FakeOAuthProvider(name="google")
    return GoogleOAuthService(
        provider=provider,
        vault=vault,
        get_admin_client=lambda: admin_client,
        schema="youtube_crawler",
        scopes=DEFAULT_SCOPES,
    )


# ─── make_google_oauth_service factory ───────────────────────────────────────


class TestMakeGoogleOAuthServiceFactory:
    def test_use_fake_returns_service_with_fake_provider(self, vault, admin_client):
        svc = make_google_oauth_service(
            vault=vault,
            get_admin_client=lambda: admin_client,
            client_id="ignored",
            client_secret="ignored",
            use_fake=True,
        )
        assert isinstance(svc._provider, FakeOAuthProvider)

    def test_real_path_requires_client_credentials(self, vault, admin_client):
        with pytest.raises(ValueError, match="non-empty"):
            make_google_oauth_service(
                vault=vault,
                get_admin_client=lambda: admin_client,
                client_id="",
                client_secret="",
                use_fake=False,
            )


# ─── initiate ────────────────────────────────────────────────────────────────


class TestInitiate:
    @pytest.mark.asyncio
    async def test_creates_row_with_state_nonce_when_absent(self, vault, admin_client):
        _set_select_result(admin_client, rows=[])  # no existing row
        svc = _make_service(vault=vault, admin_client=admin_client)

        auth_url = await svc.initiate(
            org_id="org-1",
            user_id="user-1",
            redirect_uri="https://app.test/cb",
        )

        # FakeOAuthProvider returns a deterministic URL.
        assert "fake.invalid" in auth_url.url
        assert auth_url.state  # non-empty CSRF nonce

        # Insert was issued with the state nonce + empty token columns.
        handle = _table_handle(admin_client)
        handle.insert.assert_called_once()
        payload = handle.insert.call_args[0][0]
        assert payload["org_id"] == "org-1"
        assert payload["user_id"] == "user-1"
        assert payload["state_nonce"] == auth_url.state
        assert payload["email"] == ""  # backfilled at callback
        assert payload["refresh_token_encrypted"] == ""

    @pytest.mark.asyncio
    async def test_updates_existing_row_when_present(self, vault, admin_client):
        _set_select_result(admin_client, rows=[{"id": "abc"}])
        svc = _make_service(vault=vault, admin_client=admin_client)

        await svc.initiate(
            org_id="org-1",
            user_id="user-1",
            redirect_uri="https://app.test/cb",
        )

        handle = _table_handle(admin_client)
        # No insert; update was called instead.
        handle.insert.assert_not_called()
        handle.update.assert_called_once()
        payload = handle.update.call_args[0][0]
        assert "state_nonce" in payload
        assert payload["revoked_at"] is None  # re-arms previously-revoked row

    @pytest.mark.asyncio
    async def test_state_nonce_is_non_trivial(self, vault, admin_client):
        """The nonce should be long enough to resist guessing."""
        _set_select_result(admin_client, rows=[])
        svc = _make_service(vault=vault, admin_client=admin_client)
        auth_url = await svc.initiate(
            org_id="org-1", user_id="user-1", redirect_uri="https://app.test/cb"
        )
        # secrets.token_urlsafe(32) yields ~43 chars.
        assert len(auth_url.state) >= 32


# ─── handle_callback ─────────────────────────────────────────────────────────


class TestHandleCallback:
    @pytest.mark.asyncio
    async def test_unknown_state_raises(self, vault, admin_client):
        _set_select_result(admin_client, rows=[])  # no row matches state
        svc = _make_service(vault=vault, admin_client=admin_client)
        with pytest.raises(ValueError, match="unknown or expired state nonce"):
            await svc.handle_callback(
                code="auth-code-1",
                state="ghost-state",
                redirect_uri="https://app.test/cb",
            )

    @pytest.mark.asyncio
    async def test_expired_state_raises(self, vault, admin_client):
        # State expired 1 minute ago.
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        _set_select_result(admin_client, rows=[{
            "id": "row-1",
            "org_id": "org-1",
            "user_id": "user-1",
            "state_nonce": "the-state",
            "state_expires_at": past,
        }])
        svc = _make_service(vault=vault, admin_client=admin_client)
        with pytest.raises(ValueError, match="state nonce expired"):
            await svc.handle_callback(
                code="auth-code-1",
                state="the-state",
                redirect_uri="https://app.test/cb",
            )

    @pytest.mark.asyncio
    async def test_happy_path_persists_encrypted_tokens(self, vault, admin_client):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        _set_select_result(admin_client, rows=[{
            "id": "row-1",
            "org_id": "org-1",
            "user_id": "user-1",
            "state_nonce": "the-state",
            "state_expires_at": future,
        }])
        svc = _make_service(vault=vault, admin_client=admin_client)
        org_id, user_id = await svc.handle_callback(
            code="auth-code-1",
            state="the-state",
            redirect_uri="https://app.test/cb",
        )
        assert (org_id, user_id) == ("org-1", "user-1")

        handle = _table_handle(admin_client)
        handle.update.assert_called_once()
        payload = handle.update.call_args[0][0]

        # The refresh_token / access_token columns hold CIPHERTEXT (not the
        # `fake-refresh-…` plaintext FakeOAuthProvider would emit).
        assert payload["refresh_token_encrypted"]
        assert "fake-refresh-" not in payload["refresh_token_encrypted"]
        # Sanity: the vault can decrypt the stored ciphertext back to the
        # Fake's emitted refresh_token.
        decrypted = vault.decrypt(payload["refresh_token_encrypted"])
        assert decrypted == "fake-refresh-auth-code-1"

        # state nonce wiped after a successful callback.
        assert payload["state_nonce"] is None
        assert payload["state_expires_at"] is None
        assert payload["revoked_at"] is None

    @pytest.mark.asyncio
    async def test_missing_refresh_token_raises(self, vault, admin_client):
        """If the provider returns a TokenSet without refresh_token, we
        refuse to persist (Google's "no refresh_token on re-grant" trap)."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        _set_select_result(admin_client, rows=[{
            "id": "row-1",
            "org_id": "org-1",
            "user_id": "user-1",
            "state_nonce": "the-state",
            "state_expires_at": future,
        }])
        # FakeOAuthProvider with explicitly-no-refresh-token TokenSet.
        fake = FakeOAuthProvider(
            name="google",
            predetermined_tokens=TokenSet(
                access_token="x",
                refresh_token=None,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope=[],
                raw={},
            ),
        )
        svc = _make_service(vault=vault, admin_client=admin_client, fake_provider=fake)
        with pytest.raises(ValueError, match="did not return a refresh_token"):
            await svc.handle_callback(
                code="auth-code-1",
                state="the-state",
                redirect_uri="https://app.test/cb",
            )


# ─── disconnect ──────────────────────────────────────────────────────────────


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_no_row_returns_false(self, vault, admin_client):
        _set_select_result(admin_client, rows=[])
        svc = _make_service(vault=vault, admin_client=admin_client)
        result = await svc.disconnect(org_id="org-1", user_id="user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_already_revoked_returns_false(self, vault, admin_client):
        _set_select_result(admin_client, rows=[{
            "id": "row-1",
            "refresh_token_encrypted": "",
            "revoked_at": "2026-01-01T00:00:00+00:00",
        }])
        svc = _make_service(vault=vault, admin_client=admin_client)
        result = await svc.disconnect(org_id="org-1", user_id="user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_active_revokes_at_provider_and_marks_row(self, vault, admin_client):
        # Pre-encrypt a real refresh token so the service can decrypt it
        # before calling provider.revoke().
        ciphertext = vault.encrypt("real-refresh-tok-xyz")
        _set_select_result(admin_client, rows=[{
            "id": "row-1",
            "refresh_token_encrypted": ciphertext,
            "revoked_at": None,
        }])
        fake = FakeOAuthProvider(name="google")
        svc = _make_service(vault=vault, admin_client=admin_client, fake_provider=fake)

        result = await svc.disconnect(org_id="org-1", user_id="user-1")

        assert result is True
        # Provider tracked the revocation.
        assert fake.revoked_tokens == ["real-refresh-tok-xyz"]
        # Row was marked revoked + ciphertext wiped.
        handle = _table_handle(admin_client)
        handle.update.assert_called_once()
        payload = handle.update.call_args[0][0]
        assert payload["revoked_at"]  # non-None ISO string
        assert payload["refresh_token_encrypted"] == ""
        assert payload["access_token_encrypted"] is None


# ─── status ──────────────────────────────────────────────────────────────────


class TestStatus:
    @pytest.mark.asyncio
    async def test_no_row_returns_disconnected_snapshot(self, vault, admin_client):
        _set_select_result(admin_client, rows=[])
        svc = _make_service(vault=vault, admin_client=admin_client)
        snap = await svc.status(org_id="org-1", user_id="user-1")
        assert snap.connected is False
        assert snap.email is None
        assert snap.scopes == []
        assert snap.connected_at is None
        assert snap.revoked_at is None

    @pytest.mark.asyncio
    async def test_active_row_returns_connected_snapshot(self, vault, admin_client):
        _set_select_result(admin_client, rows=[{
            "email": "operator@example.com",
            "scopes": ["scope.a", "scope.b"],
            "connected_at": "2026-05-11T10:00:00+00:00",
            "revoked_at": None,
            "refresh_token_encrypted": "non-empty-ciphertext",
        }])
        svc = _make_service(vault=vault, admin_client=admin_client)
        snap = await svc.status(org_id="org-1", user_id="user-1")
        assert snap.connected is True
        assert snap.email == "operator@example.com"
        assert snap.scopes == ["scope.a", "scope.b"]
        assert snap.connected_at is not None

    @pytest.mark.asyncio
    async def test_revoked_row_returns_disconnected_snapshot(self, vault, admin_client):
        _set_select_result(admin_client, rows=[{
            "email": "operator@example.com",
            "scopes": ["scope.a"],
            "connected_at": "2026-05-11T10:00:00+00:00",
            "revoked_at": "2026-05-11T11:00:00+00:00",
            "refresh_token_encrypted": "",
        }])
        svc = _make_service(vault=vault, admin_client=admin_client)
        snap = await svc.status(org_id="org-1", user_id="user-1")
        assert snap.connected is False
        assert snap.revoked_at is not None
