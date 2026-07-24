"""Tests for the app_config_store product seam (Wave 2 — app-wide, DB-backed
+ env-fallback config; currently the Meta App ID / App Secret pair).

Mirrors ``test_credential_vault.py``'s structure — the SAME
"loud-EncryptionNotConfigured, no silent Fake" contract, plus the resolver's
DB-wins / env-fallback / graceful-degrade behavior that
``noctusai_lib.security.app_config.resolve_meta_app_credentials`` documents.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.services.app_config_store import (
    META_AD_ACCOUNT_ID_KEY,
    META_ADS_ORG_ID_KEY,
    META_APP_ID_KEY,
    META_APP_SECRET_KEY,
    META_SYSTEM_USER_TOKEN_KEY,
    build_app_config_store,
    resolve_meta_ads_config,
    resolve_meta_app_creds,
)
from app.services.credential_vault import EncryptionNotConfigured
from noctusai_lib.security.app_config import FakeAppConfigStore, RealAppConfigStore


class _Settings:
    """Minimal product-settings stand-in — mirrors test_meta_integration.py's
    ``_Settings`` fixture shape."""

    def __init__(self, *, app_id: str = "", app_secret: str = "") -> None:
        self.meta_app_id = app_id
        self.meta_app_secret = app_secret


class _RecordingClient:
    """External-substrate double (not a monkeypatch of our code) — the same
    minimal chained-query shape ``test_credential_vault.py`` uses."""

    def __init__(self):
        self._select_rows: list[dict] = []
        self.upserted: list[dict] = []

    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def upsert(self, payload, **_kwargs):
        self.upserted.append(payload)
        return self

    def delete(self, *_a, **_k):
        return self

    def execute(self):
        return type("Resp", (), {"data": list(self._select_rows)})()


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


# ─── build_app_config_store — loud EncryptionNotConfigured, no silent Fake ──
class TestLoudEncryptionCheck:
    def test_empty_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            build_app_config_store(_RecordingClient(), encryption_key="")

    def test_invalid_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            build_app_config_store(
                _RecordingClient(), encryption_key="not-a-fernet-key"
            )

    def test_valid_key_builds_real_store(self, fernet_key):
        store = build_app_config_store(_RecordingClient(), encryption_key=fernet_key)
        assert isinstance(store, RealAppConfigStore)
        assert not isinstance(store, FakeAppConfigStore)


# ─── resolve_meta_app_creds — DB-first, env-fallback, per-key independent ───
class TestResolveMetaAppCreds:
    def test_no_store_falls_back_to_env(self):
        """store=FakeAppConfigStore() with nothing set → env wins outright."""
        app_id, app_secret = resolve_meta_app_creds(
            settings=_Settings(app_id="env-id", app_secret="env-secret"),
            store=FakeAppConfigStore(),
        )
        assert app_id == "env-id"
        assert app_secret == "env-secret"

    def test_db_value_wins_over_env_for_both_keys(self):
        store = FakeAppConfigStore()
        store.put(META_APP_ID_KEY, "db-id")
        store.put(META_APP_SECRET_KEY, "db-secret")

        app_id, app_secret = resolve_meta_app_creds(
            settings=_Settings(app_id="env-id", app_secret="env-secret"),
            store=store,
        )
        assert app_id == "db-id"
        assert app_secret == "db-secret"

    def test_partial_db_config_resolves_each_key_independently(self):
        """Only app_id set in the DB → app_id from DB, app_secret from env
        (never all-or-nothing)."""
        store = FakeAppConfigStore()
        store.put(META_APP_ID_KEY, "db-id")

        app_id, app_secret = resolve_meta_app_creds(
            settings=_Settings(app_id="env-id", app_secret="env-secret"),
            store=store,
        )
        assert app_id == "db-id"
        assert app_secret == "env-secret"

    def test_neither_db_nor_env_returns_none_for_both(self):
        app_id, app_secret = resolve_meta_app_creds(
            settings=_Settings(), store=FakeAppConfigStore()
        )
        assert app_id is None
        assert app_secret is None

    def test_degrades_to_env_when_store_none_and_encryption_key_missing(
        self, monkeypatch
    ):
        """store=None (the production default) + an unbuildable store →
        the resolver degrades to env-only, NEVER hard-failing a read-only
        Meta OAuth/scopes/status call.

        The EncryptionNotConfigured precondition is forced EXPLICITLY.
        This test used to rely on the ambient environment happening to
        have no ENCRYPTION_KEY ("the app's real ENCRYPTION_KEY is empty
        in this test env"): green on a clean checkout, RED on any machine
        with a real root `.env`. Worse, where it was green it was green
        by accident — a build_app_config_store() that stopped raising
        would not have been caught.
        """
        def _raise():
            raise EncryptionNotConfigured("no key in this test")

        # self-patch-ok: forces the degrade PRECONDITION, not the guard
        # under test (the degrade branch itself is still exercised).
        monkeypatch.setattr(
            "app.services.app_config_store.build_app_config_store", _raise
        )

        app_id, app_secret = resolve_meta_app_creds(
            settings=_Settings(app_id="env-id", app_secret="env-secret")
        )
        assert app_id == "env-id"
        assert app_secret == "env-secret"

    def test_default_settings_used_when_none_passed(self, monkeypatch):
        """settings=None → falls back to the product's default_settings
        singleton.

        Asserts the fallback POSITIVELY (the singleton's values come
        back) instead of asserting emptiness. The old form
        (`assert app_id in (None, "")`) only held while the ambient env
        was empty — it read a developer's real META_APP_ID off the root
        `.env` and failed, and on CI it passed without proving the
        singleton was consulted at all.
        """
        # self-patch-ok: substitutes the settings SOURCE to isolate the
        # test from the developer's real .env; the resolver's fallback
        # path is what's under test.
        monkeypatch.setattr(
            "app.services.app_config_store.default_settings",
            _Settings(app_id="singleton-id", app_secret="singleton-secret"),
        )

        app_id, app_secret = resolve_meta_app_creds(store=FakeAppConfigStore())
        assert app_id == "singleton-id"
        assert app_secret == "singleton-secret"


# ─── resolve_meta_ads_config — DB-first, env-fallback (prod-from-DB model) ───
class TestResolveMetaAdsConfig:
    @staticmethod
    def _settings(*, token="", account="", org=""):
        from types import SimpleNamespace

        return SimpleNamespace(
            meta_system_user_token=token,
            meta_ad_account_id=account,
            meta_ads_org_id=org,
        )

    def test_env_fallback_when_db_empty(self):
        token, account, org = resolve_meta_ads_config(
            settings=self._settings(token="env-tok", account="act_1", org="org-1"),
            store=FakeAppConfigStore(),
        )
        assert (token, account, org) == ("env-tok", "act_1", "org-1")

    def test_db_wins_over_env_per_key(self):
        store = FakeAppConfigStore()
        store.put(META_SYSTEM_USER_TOKEN_KEY, "db-tok")
        store.put(META_AD_ACCOUNT_ID_KEY, "act_db")
        # org NOT in DB → env fallback for org only (per-key independence).
        token, account, org = resolve_meta_ads_config(
            settings=self._settings(token="env-tok", account="act_env", org="org-env"),
            store=store,
        )
        assert token == "db-tok"
        assert account == "act_db"
        assert org == "org-env"

    def test_none_when_neither(self):
        token, account, org = resolve_meta_ads_config(
            settings=self._settings(), store=FakeAppConfigStore()
        )
        assert (token, account, org) == (None, None, None)
