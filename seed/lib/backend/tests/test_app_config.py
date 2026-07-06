"""Tests for `noctusai_lib.security.app_config`.

Covers the Protocol contract via the Fake, the Real (`RealAppConfigStore`)
encrypt/decrypt/UPSERT path against a faithful in-test Supabase
query-builder double (mirrors `test_token_store.py`'s substrate double —
an injected external-substrate stand-in, NOT a monkeypatch of our code),
the factory's Real-vs-Fake selection, and `resolve_meta_app_credentials`'s
per-key DB-wins/env-fallback precedence.
"""

from __future__ import annotations

import pytest

from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_lib.security.app_config import (
    META_APP_ID_KEY,
    META_APP_SECRET_KEY,
    AppConfigDecryptError,
    FakeAppConfigStore,
    RealAppConfigStore,
    build_app_config_store,
    resolve_meta_app_credentials,
)


# ---------------------------------------------------------------------------
# Minimal faithful Supabase substrate double (external IO stand-in)
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}
        self._op = None
        self._insert_payload = None
        self._select_cols: tuple = ()

    # read
    def select(self, *cols):
        self._op = "select"
        self._select_cols = cols
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, _n):
        return self

    # write
    def upsert(self, payload, *, on_conflict=None):  # noqa: ARG002
        self._op = "upsert"
        self._insert_payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self._filters.items())

    def execute(self):
        if self._op == "select":
            rows = [dict(r) for r in self._rows if self._matches(r)]
            if self._select_cols and self._select_cols != ("*",):
                rows = [
                    {c: r[c] for c in self._select_cols if c in r} for r in rows
                ]
            return _Resp(rows)
        if self._op == "upsert":
            key = self._insert_payload["key"]
            self._rows[:] = [r for r in self._rows if r["key"] != key]
            self._rows.append(dict(self._insert_payload))
            return _Resp([dict(self._insert_payload)])
        if self._op == "delete":
            removed = [r for r in self._rows if self._matches(r)]
            self._rows[:] = [r for r in self._rows if not self._matches(r)]
            return _Resp([dict(r) for r in removed])
        return _Resp([])


class _FakeSupabase:
    def __init__(self):
        self._tables: dict[str, list] = {}

    def table(self, name):
        rows = self._tables.setdefault(name, [])
        return _Query(rows)


# ---------------------------------------------------------------------------
# Fake contract
# ---------------------------------------------------------------------------


class TestFakeAppConfigStore:
    def test_get_missing_returns_none(self):
        store = FakeAppConfigStore()
        assert store.get("meta_app_id") is None

    def test_put_then_get_roundtrips(self):
        store = FakeAppConfigStore()
        store.put("meta_app_id", "12345")
        assert store.get("meta_app_id") == "12345"

    def test_put_upserts_same_key(self):
        store = FakeAppConfigStore()
        store.put("meta_app_id", "first")
        store.put("meta_app_id", "second")
        assert store.get("meta_app_id") == "second"
        assert store.list_keys() == ["meta_app_id"]

    def test_delete_idempotent(self):
        store = FakeAppConfigStore()
        store.put("meta_app_secret", "s3cr3t")
        assert store.delete("meta_app_secret") is True
        assert store.delete("meta_app_secret") is False

    def test_list_keys_sorted_and_no_values(self):
        store = FakeAppConfigStore()
        store.put("meta_app_secret", "s")
        store.put("meta_app_id", "i")
        assert store.list_keys() == ["meta_app_id", "meta_app_secret"]


# ---------------------------------------------------------------------------
# Real adapter — encrypt/decrypt/UPSERT/fail-loud
# ---------------------------------------------------------------------------


class TestRealAppConfigStore:
    def test_requires_fernet_key(self):
        with pytest.raises(ValueError):
            RealAppConfigStore(_FakeSupabase(), b"")

    def test_put_encrypts_at_rest(self):
        client = _FakeSupabase()
        key = generate_key()
        store = RealAppConfigStore(client, key)
        store.put("meta_app_secret", "super-secret")
        raw = client._tables["app_integration_config"][0]["encrypted_value"]
        # The plaintext secret MUST NOT appear in the stored column.
        assert "super-secret" not in raw

    def test_put_then_get_roundtrips_through_encryption(self):
        client = _FakeSupabase()
        key = generate_key()
        store = RealAppConfigStore(client, key)
        store.put("meta_app_id", "app-id-123")
        assert store.get("meta_app_id") == "app-id-123"

    def test_put_upserts_on_key(self):
        client = _FakeSupabase()
        key = generate_key()
        store = RealAppConfigStore(client, key)
        store.put("meta_app_id", "first")
        store.put("meta_app_id", "second")
        assert len(client._tables["app_integration_config"]) == 1
        assert store.get("meta_app_id") == "second"

    def test_get_fails_loud_on_key_mismatch(self):
        client = _FakeSupabase()
        store_a = RealAppConfigStore(client, generate_key())
        store_a.put("meta_app_id", "a")
        store_b = RealAppConfigStore(client, generate_key())
        with pytest.raises(AppConfigDecryptError):
            store_b.get("meta_app_id")

    def test_delete_returns_bool(self):
        client = _FakeSupabase()
        key = generate_key()
        store = RealAppConfigStore(client, key)
        store.put("meta_app_secret", "s")
        assert store.delete("meta_app_secret") is True
        assert store.delete("meta_app_secret") is False

    def test_list_keys_no_decrypt(self):
        client = _FakeSupabase()
        key = generate_key()
        store = RealAppConfigStore(client, key)
        store.put("meta_app_id", "i")
        store.put("meta_app_secret", "s")
        assert store.list_keys() == ["meta_app_id", "meta_app_secret"]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestBuildAppConfigStore:
    def test_default_is_fake(self):
        assert isinstance(build_app_config_store(), FakeAppConfigStore)

    def test_fake_when_only_client(self):
        assert isinstance(
            build_app_config_store(client=_FakeSupabase()), FakeAppConfigStore
        )

    def test_fake_when_only_key(self):
        assert isinstance(
            build_app_config_store(fernet_key=generate_key()), FakeAppConfigStore
        )

    def test_real_when_client_and_key(self):
        store = build_app_config_store(
            client=_FakeSupabase(), fernet_key=generate_key()
        )
        assert isinstance(store, RealAppConfigStore)


# ---------------------------------------------------------------------------
# resolve_meta_app_credentials — precedence
# ---------------------------------------------------------------------------


class TestResolveMetaAppCredentials:
    def test_db_wins_when_both_keys_set(self):
        store = FakeAppConfigStore()
        store.put(META_APP_ID_KEY, "db-app-id")
        store.put(META_APP_SECRET_KEY, "db-app-secret")
        app_id, app_secret = resolve_meta_app_credentials(
            store, env_app_id="env-app-id", env_app_secret="env-app-secret"
        )
        assert (app_id, app_secret) == ("db-app-id", "db-app-secret")

    def test_env_fallback_when_db_empty(self):
        store = FakeAppConfigStore()
        app_id, app_secret = resolve_meta_app_credentials(
            store, env_app_id="env-app-id", env_app_secret="env-app-secret"
        )
        assert (app_id, app_secret) == ("env-app-id", "env-app-secret")

    def test_partial_db_config_resolved_independently(self):
        store = FakeAppConfigStore()
        store.put(META_APP_ID_KEY, "db-app-id")
        app_id, app_secret = resolve_meta_app_credentials(
            store, env_app_id="env-app-id", env_app_secret="env-app-secret"
        )
        # DB wins for the key it has; env fills the gap for the other.
        assert app_id == "db-app-id"
        assert app_secret == "env-app-secret"

    def test_neither_db_nor_env_returns_none(self):
        store = FakeAppConfigStore()
        app_id, app_secret = resolve_meta_app_credentials(
            store, env_app_id=None, env_app_secret=None
        )
        assert (app_id, app_secret) == (None, None)
