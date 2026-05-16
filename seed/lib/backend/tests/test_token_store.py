"""Tests for `noctusai_lib.security.token_store`.

Covers the Protocol contract via the Fake, and the Real
(`SupabaseCredentialStore`) encrypt/decrypt/UPSERT path against a
faithful in-test Supabase query-builder double. The double is NOT a
monkeypatch of our code — it is an injected external-substrate stand-in
that implements exactly the PostgREST chain the adapter calls
(`.table().select().eq().eq().limit().execute()` etc.), so the Real
adapter's load-bearing logic (JSON-serialize → Fernet-encrypt → store;
read → decrypt → JSON-parse; fail-loud on key mismatch) is exercised
end-to-end.
"""

from __future__ import annotations

import pytest

from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_lib.security.token_store import (
    CredentialDecryptError,
    FakeCredentialStore,
    SupabaseCredentialStore,
    make_credential_store,
)


# ---------------------------------------------------------------------------
# Minimal faithful Supabase substrate double (external IO stand-in)
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, table_store, table):
        self._rows = rows
        self._store = table_store
        self._table = table
        self._filters: dict = {}
        self._op = None
        self._insert_payload = None

    # read
    def select(self, *_a, **_k):
        self._op = "select"
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
            return _Resp([dict(r) for r in self._rows if self._matches(r)])
        if self._op == "upsert":
            key = (
                self._insert_payload["org_id"],
                self._insert_payload["provider"],
            )
            self._rows[:] = [
                r
                for r in self._rows
                if (r["org_id"], r["provider"]) != key
            ]
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
        return _Query(rows, self._tables, name)


# ---------------------------------------------------------------------------
# Fake contract
# ---------------------------------------------------------------------------


class TestFakeCredentialStore:
    def test_get_missing_returns_none(self):
        store = FakeCredentialStore()
        assert store.get("org1", "google_calendar") is None

    def test_put_then_get_roundtrips(self):
        store = FakeCredentialStore()
        rec = store.put("org1", "google", {"access_token": "a", "refresh_token": "r"})
        assert rec.org_id == "org1"
        got = store.get("org1", "google")
        assert got is not None
        assert got.tokens == {"access_token": "a", "refresh_token": "r"}

    def test_put_upserts_same_pair(self):
        store = FakeCredentialStore()
        store.put("org1", "google", {"v": 1})
        store.put("org1", "google", {"v": 2})
        assert store.get("org1", "google").tokens == {"v": 2}
        assert store.list_providers("org1") == ["google"]

    def test_delete_idempotent(self):
        store = FakeCredentialStore()
        store.put("org1", "meta", {"t": 1})
        assert store.delete("org1", "meta") is True
        assert store.delete("org1", "meta") is False

    def test_list_providers_scoped_to_org_and_sorted(self):
        store = FakeCredentialStore()
        store.put("org1", "meta", {})
        store.put("org1", "google", {})
        store.put("org2", "vista", {})
        assert store.list_providers("org1") == ["google", "meta"]
        assert store.list_providers("org2") == ["vista"]


# ---------------------------------------------------------------------------
# Real adapter — encrypt/decrypt/UPSERT/fail-loud
# ---------------------------------------------------------------------------


class TestSupabaseCredentialStore:
    def test_requires_fernet_key(self):
        with pytest.raises(ValueError):
            SupabaseCredentialStore(_FakeSupabase(), b"")

    def test_put_encrypts_at_rest(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "google", {"refresh_token": "super-secret"})
        raw = client._tables["oauth_credentials"][0]["encrypted_tokens"]
        # The plaintext secret MUST NOT appear in the stored column.
        assert "super-secret" not in raw

    def test_put_then_get_roundtrips_through_encryption(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "google", {"access_token": "a", "scope": "calendar"})
        got = store.get("org1", "google")
        assert got is not None
        assert got.tokens == {"access_token": "a", "scope": "calendar"}

    def test_put_upserts_on_org_provider(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "google", {"v": 1})
        store.put("org1", "google", {"v": 2})
        assert len(client._tables["oauth_credentials"]) == 1
        assert store.get("org1", "google").tokens == {"v": 2}

    def test_get_fails_loud_on_key_mismatch(self):
        client = _FakeSupabase()
        store_a = SupabaseCredentialStore(client, generate_key())
        store_a.put("org1", "google", {"t": 1})
        store_b = SupabaseCredentialStore(client, generate_key())
        with pytest.raises(CredentialDecryptError):
            store_b.get("org1", "google")

    def test_delete_returns_bool(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "meta", {"t": 1})
        assert store.delete("org1", "meta") is True
        assert store.delete("org1", "meta") is False

    def test_list_providers_no_decrypt(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "google", {})
        store.put("org1", "meta", {})
        assert store.list_providers("org1") == ["google", "meta"]

    def test_metadata_stored_plaintext(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "meta", {"t": 1}, metadata={"auth_mode": "system_user"})
        got = store.get("org1", "meta")
        assert got.metadata == {"auth_mode": "system_user"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestMakeCredentialStore:
    def test_default_is_fake(self):
        assert isinstance(make_credential_store(), FakeCredentialStore)

    def test_fake_when_only_client(self):
        assert isinstance(
            make_credential_store(client=_FakeSupabase()), FakeCredentialStore
        )

    def test_fake_when_only_key(self):
        assert isinstance(
            make_credential_store(fernet_key=generate_key()), FakeCredentialStore
        )

    def test_real_when_client_and_key(self):
        store = make_credential_store(
            client=_FakeSupabase(), fernet_key=generate_key()
        )
        assert isinstance(store, SupabaseCredentialStore)
