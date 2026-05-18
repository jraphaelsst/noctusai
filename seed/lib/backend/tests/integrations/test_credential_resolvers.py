"""Colocated tests for `integrations.credential_resolvers`.

Covers the Prereq-2 read-side bridges (CredentialStore → adapter
resolver Protocols) + the Prereq-3 write-side OAuth-callback hook.
Tested against the seam's own `FakeCredentialStore` — the bridge has
no IO of its own, so this exercises every branch the Real path would.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.integrations.credential_resolvers import (
    CALENDAR_PROVIDER,
    META_PROVIDER,
    CredentialStoreCalendarResolver,
    CredentialStoreMetaResolver,
    make_token_persisting_callback,
)
from noctusai_lib.integrations.google_calendar.credentials import (
    OAuthCalendarCredentials,
)
from noctusai_lib.integrations.meta.credentials import OAuthMetaCredentials
from noctusai_lib.security.oauth.types import OAuthCallbackResult, TokenSet
from noctusai_lib.security.token_store import FakeCredentialStore


class TestCalendarResolver:
    def test_returns_oauth_creds_from_stored_bundle(self):
        store = FakeCredentialStore()
        store.put(
            "org1",
            CALENDAR_PROVIDER,
            {"access_token": "AT", "refresh_token": "RT"},
            metadata={"scopes": ["s1"]},
        )
        r = CredentialStoreCalendarResolver(
            store, client_id="cid", client_secret="csec"
        )
        creds = r.get_credentials("org1")
        assert isinstance(creds, OAuthCalendarCredentials)
        assert creds.refresh_token == "RT"
        assert creds.token == "AT"
        assert creds.client_id == "cid"
        assert creds.scopes == ["s1"]

    def test_no_row_returns_none(self):
        r = CredentialStoreCalendarResolver(
            FakeCredentialStore(), client_id="c", client_secret="s"
        )
        assert r.get_credentials("absent") is None

    def test_no_tenant_returns_none(self):
        r = CredentialStoreCalendarResolver(
            FakeCredentialStore(), client_id="c", client_secret="s"
        )
        assert r.get_credentials(None) is None

    def test_missing_refresh_token_returns_none(self):
        store = FakeCredentialStore()
        store.put("o", CALENDAR_PROVIDER, {"access_token": "AT"})
        r = CredentialStoreCalendarResolver(
            store, client_id="c", client_secret="s"
        )
        assert r.get_credentials("o") is None


class TestMetaResolver:
    def test_returns_meta_creds_with_metadata(self):
        store = FakeCredentialStore()
        store.put(
            "org1",
            META_PROVIDER,
            {"access_token": "LL"},
            metadata={"user_id": "u1", "user_name": "N"},
        )
        creds = CredentialStoreMetaResolver(store).get_credentials("org1")
        assert isinstance(creds, OAuthMetaCredentials)
        assert creds.access_token == "LL"
        assert creds.user_id == "u1"
        assert creds.user_name == "N"

    def test_no_row_returns_none(self):
        assert (
            CredentialStoreMetaResolver(FakeCredentialStore()).get_credentials(
                "x"
            )
            is None
        )

    def test_missing_access_token_returns_none(self):
        store = FakeCredentialStore()
        store.put("o", META_PROVIDER, {"refresh_token": "r"})
        assert CredentialStoreMetaResolver(store).get_credentials("o") is None


class TestTokenPersistingCallback:
    @pytest.mark.asyncio
    async def test_success_persists_bundle(self):
        store = FakeCredentialStore()
        cb = make_token_persisting_callback(
            store,
            org_id_from_state=lambda s: s.split(":")[0],
            provider_map={"google": CALENDAR_PROVIDER},
        )
        result = OAuthCallbackResult(
            provider="google",
            state="orgZ:nonce",
            tokens=TokenSet(
                access_token="AT",
                refresh_token="RT",
                expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
                scope=["a"],
            ),
            error=None,
        )
        await cb(result)
        stored = store.get("orgZ", CALENDAR_PROVIDER)
        assert stored is not None
        assert stored.tokens["access_token"] == "AT"
        assert stored.tokens["refresh_token"] == "RT"
        assert stored.tokens["scope"] == ["a"]
        assert stored.tokens["expiry"].startswith("2030-01-01")

    @pytest.mark.asyncio
    async def test_error_result_is_noop(self):
        store = FakeCredentialStore()
        cb = make_token_persisting_callback(
            store, org_id_from_state=lambda s: s
        )
        await cb(
            OAuthCallbackResult(
                provider="google",
                state="o",
                tokens=None,
                error="denied",
            )
        )
        assert store.get("o", "google") is None

    @pytest.mark.asyncio
    async def test_unmapped_provider_stored_verbatim(self):
        store = FakeCredentialStore()
        cb = make_token_persisting_callback(
            store, org_id_from_state=lambda s: s
        )
        await cb(
            OAuthCallbackResult(
                provider="meta",
                state="orgM",
                tokens=TokenSet(
                    access_token="X",
                    refresh_token=None,
                    expires_at=datetime(2031, 6, 1, tzinfo=timezone.utc),
                ),
                error=None,
            )
        )
        assert store.get("orgM", "meta") is not None
