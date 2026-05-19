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


class TestMetadataColumnSeam:
    """Real (`SupabaseCredentialStore`) + Fake parity for the seam.

    Persisted-payload assertions read the in-test Supabase substrate's
    stored row (``client._tables[...]``) — the injected external IO
    stand-in, NOT a monkeypatch of our code (same pattern this module
    already uses for `test_put_encrypts_at_rest`).
    """

    # (a) defaults reproduce historical behavior exactly --------------------
    def test_default_back_compat_real_unchanged(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key)
        store.put("org1", "google", {"t": 1}, metadata={"auth_mode": "system_user"})
        row = client._tables["oauth_credentials"][0]
        # JSON metadata column present and carries the unmapped blob.
        assert row["metadata"] == {"auth_mode": "system_user"}
        got = store.get("org1", "google")
        assert got.tokens == {"t": 1}
        assert got.metadata == {"auth_mode": "system_user"}

    def test_default_back_compat_fake_unchanged(self):
        store = FakeCredentialStore()
        rec = store.put("o", "p", {"t": 1}, metadata={"auth_mode": "user_oauth"})
        assert rec.metadata == {"auth_mode": "user_oauth"}
        assert store.get("o", "p").metadata == {"auth_mode": "user_oauth"}

    def test_default_factory_threads_defaults(self):
        store = make_credential_store(
            client=_FakeSupabase(), fernet_key=generate_key()
        )
        assert isinstance(store, SupabaseCredentialStore)
        store.put("o", "p", {"x": 1}, metadata={"a": "b"})

    # (b) metadata_column=None omits the column on write + read ------------
    def test_metadata_column_none_omits_column_real(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(client, key, metadata_column=None)
        store.put("org1", "google", {"t": 1})
        row = client._tables["oauth_credentials"][0]
        assert "metadata" not in row  # column omitted from persisted payload
        got = store.get("org1", "google")
        assert got.tokens == {"t": 1}
        assert got.metadata == {}  # not read back

    def test_metadata_column_none_omits_column_fake(self):
        store = FakeCredentialStore(metadata_column=None)
        rec = store.put("o", "p", {"t": 1})
        assert rec.metadata == {}
        assert store.get("o", "p").metadata == {}

    def test_metadata_column_none_ignores_stray_db_metadata_on_read(self):
        # A physical row that happens to carry a `metadata` key must NOT
        # be re-inflated when the store is configured column-less.
        client = _FakeSupabase()
        key = generate_key()
        seed_store = SupabaseCredentialStore(client, key)  # default writer
        seed_store.put("org1", "google", {"t": 1}, metadata={"leaked": "x"})
        columnless = SupabaseCredentialStore(client, key, metadata_column=None)
        assert columnless.get("org1", "google").metadata == {}

    # (c) metadata_columns round-trips via discrete columns ----------------
    _MAP = {
        "channel_id": "channel_id",
        "channel_title": "channel_title",
        "scopes": "scopes",
    }

    def test_metadata_columns_roundtrip_real(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(
            client,
            key,
            metadata_column=None,
            metadata_columns=self._MAP,
        )
        store.put(
            "org1",
            "youtube",
            {"refresh_token": "r"},
            metadata={
                "channel_id": "UC123",
                "channel_title": "My Channel",
                "scopes": ["youtube.upload"],
            },
        )
        row = client._tables["oauth_credentials"][0]
        # mapped keys land in discrete columns, NOT a JSON blob
        assert row["channel_id"] == "UC123"
        assert row["channel_title"] == "My Channel"
        assert row["scopes"] == ["youtube.upload"]
        assert "metadata" not in row
        got = store.get("org1", "youtube")
        assert got.tokens == {"refresh_token": "r"}
        assert got.metadata == {
            "channel_id": "UC123",
            "channel_title": "My Channel",
            "scopes": ["youtube.upload"],
        }

    def test_metadata_columns_roundtrip_fake(self):
        store = FakeCredentialStore(
            metadata_column=None, metadata_columns=self._MAP
        )
        rec = store.put(
            "org1",
            "youtube",
            {"refresh_token": "r"},
            metadata={
                "channel_id": "UC123",
                "channel_title": "My Channel",
                "scopes": ["youtube.upload"],
            },
        )
        assert rec.metadata == {
            "channel_id": "UC123",
            "channel_title": "My Channel",
            "scopes": ["youtube.upload"],
        }
        got = store.get("org1", "youtube")
        assert got.metadata == {
            "channel_id": "UC123",
            "channel_title": "My Channel",
            "scopes": ["youtube.upload"],
        }

    def test_metadata_columns_with_json_column_splits_mapped_vs_unmapped(self):
        # mapped keys → discrete columns; unmapped → JSON blob (both set).
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(
            client,
            key,
            metadata_column="metadata",
            metadata_columns={"channel_id": "channel_id"},
        )
        store.put(
            "org1",
            "youtube",
            {"t": 1},
            metadata={"channel_id": "UC9", "auth_mode": "user_oauth"},
        )
        row = client._tables["oauth_credentials"][0]
        assert row["channel_id"] == "UC9"
        assert row["metadata"] == {"auth_mode": "user_oauth"}
        got = store.get("org1", "youtube")
        assert got.metadata == {"channel_id": "UC9", "auth_mode": "user_oauth"}

    # (d) unmapped key + metadata_column=None → fail-loud ValueError -------
    def test_unmapped_key_with_no_metadata_column_raises_real(self):
        client = _FakeSupabase()
        key = generate_key()
        store = SupabaseCredentialStore(
            client,
            key,
            metadata_column=None,
            metadata_columns={"channel_id": "channel_id"},
        )
        with pytest.raises(ValueError, match="no destination"):
            store.put(
                "org1",
                "youtube",
                {"t": 1},
                metadata={"channel_id": "UC1", "auth_mode": "leak"},
            )
        # the failing put must NOT have persisted a partial row
        assert client._tables.get("oauth_credentials", []) == []

    def test_unmapped_key_with_no_metadata_column_raises_fake(self):
        store = FakeCredentialStore(
            metadata_column=None, metadata_columns={"channel_id": "channel_id"}
        )
        with pytest.raises(ValueError, match="no destination"):
            store.put("o", "p", {"t": 1}, metadata={"stray": "x"})
        assert store.get("o", "p") is None

    def test_factory_threads_seam_params(self):
        store = make_credential_store(
            client=_FakeSupabase(),
            fernet_key=generate_key(),
            metadata_column=None,
            metadata_columns={"channel_id": "channel_id"},
        )
        assert isinstance(store, SupabaseCredentialStore)
        assert store._metadata_column is None
        assert store._metadata_columns == {"channel_id": "channel_id"}
        fake = make_credential_store(
            metadata_column=None, metadata_columns={"scopes": "scopes"}
        )
        assert isinstance(fake, FakeCredentialStore)
        assert fake._metadata_column is None
        assert fake._metadata_columns == {"scopes": "scopes"}
