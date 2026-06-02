"""Tests for the credential-vault seed-consume seam.

Phase 2 replaced the product-local ``credential_store.py`` fork with
``app.services.credential_vault`` — a thin builder over the seed
``noctusai_lib.security.token_store``. Crypto round-trip / tamper /
wrong-key behavior is now the seed's responsibility (verified by the
seed's own ``test_token_store.py`` — 29 passed). These tests cover the
*product seam's* contract:

  1. the loud "ENCRYPTION_KEY not configured" check the routers map to a
     503 (the seed factory would silently return a Fake — the product
     refuses to silently degrade);
  2. the factory wiring returns a working store that round-trips the
     denormalized ``channel_id / channel_title / scopes`` metadata
     through the Phase-1 ``metadata_columns`` seam;
  3. ANTI-FALSE-GREEN: the payload the store hands the Supabase client
     uses ONLY columns that exist in the ``social_wiring.credentials``
     DDL — the mock-shape blind spot cannot hide a column mismatch.
"""
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.services.credential_vault import (
    EncryptionNotConfigured,
    build_credential_store,
)
from noctusai_lib.security.token_store import (
    FakeCredentialStore,
    SupabaseCredentialStore,
)

# The exact column set of ``social_wiring.credentials`` per
# migrations/001_social-wiring.sql. The store may write any SUBSET of
# these; it must NEVER write a key outside this set (that would silently
# 400 against real PostgREST while passing a permissive mock).
_DDL_COLUMNS = {
    "id",
    "org_id",
    "provider",
    "encrypted_tokens",
    "channel_id",
    "channel_title",
    "scopes",
    "created_at",
    "updated_at",
}


class _RecordingClient:
    """Minimal injected Supabase substrate that records the upsert payload.

    Not a monkeypatch of our code — an external-substrate double, the
    same shape the seed's own ``test_token_store.py`` uses. Captures the
    dict handed to ``.table(...).upsert(...)`` so the test can assert its
    key set against the real DDL.
    """

    def __init__(self):
        self.upserted: list[dict] = []
        self._select_rows: list[dict] = []

    # chained query API used by SupabaseCredentialStore
    def table(self, _name):
        return self

    def upsert(self, payload, **_kwargs):
        self.upserted.append(payload)
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def delete(self, *_a, **_k):
        return self

    def execute(self):
        return type("Resp", (), {"data": list(self._select_rows)})()


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


class TestLoudEncryptionCheck:
    """The seed factory silently returns a Fake when the key is absent.
    The product seam must instead fail loud so routers can 503."""

    def test_empty_key_raises(self):
        # Drive the product setting via the DI seam, not our code: inject
        # the config value (an external input), then assert the seam
        # fails loud. Per KB § PATTERNS/di-test-seam.md (Class-B kwarg).
        with pytest.raises(EncryptionNotConfigured):
            build_credential_store(_RecordingClient(), encryption_key="")

    def test_invalid_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            build_credential_store(
                _RecordingClient(), encryption_key="not-a-fernet-key"
            )

    def test_valid_key_builds_real_store(self, fernet_key):
        store = build_credential_store(
            _RecordingClient(), encryption_key=fernet_key
        )
        assert isinstance(store, SupabaseCredentialStore)

    def test_no_client_still_loud_on_bad_key(self):
        """Even with no client, a missing key is a config gap, not a
        silent Fake — the product never silently degrades."""
        with pytest.raises(EncryptionNotConfigured):
            build_credential_store(None, encryption_key="")


class TestMetadataColumnRoundTrip:
    """The Phase-1 metadata_columns seam maps the denormalized
    channel_id / channel_title / scopes columns. put() must flatten them
    into discrete columns; get() must re-inflate them into .metadata."""

    def test_put_flattens_metadata_into_discrete_columns(
        self, fernet_key
    ):
        client = _RecordingClient()
        store = build_credential_store(client, encryption_key=fernet_key)
        org = uuid4()

        store.put(
            str(org),
            "youtube",
            {
                "access_token": "PLAINTEXT-ACCESS-TOKEN-MARKER",
                "refresh_token": "PLAINTEXT-REFRESH-TOKEN-MARKER",
            },
            metadata={
                "channel_id": "UC123",
                "channel_title": "My Channel",
                "scopes": ["a", "b"],
            },
        )

        assert len(client.upserted) == 1
        payload = client.upserted[0]
        # The denormalized keys are discrete columns, NOT a json blob.
        assert payload["channel_id"] == "UC123"
        assert payload["channel_title"] == "My Channel"
        assert payload["scopes"] == ["a", "b"]
        # No "metadata" json column on this absorbed table.
        assert "metadata" not in payload
        # Secret is encrypted at rest, never plaintext. Use long distinctive
        # markers: a short token (e.g. "AT") collides by chance with the random
        # Fernet base64 blob, making the assertion flaky (caught 2026-06-02).
        assert "PLAINTEXT-ACCESS-TOKEN-MARKER" not in payload["encrypted_tokens"]
        assert "PLAINTEXT-REFRESH-TOKEN-MARKER" not in payload["encrypted_tokens"]

    def test_get_reinflates_metadata_from_columns(
        self, fernet_key
    ):
        client = _RecordingClient()
        store = build_credential_store(client, encryption_key=fernet_key)
        org = uuid4()

        # Round-trip: persist, then reflect the recorded payload back as
        # the select row so get() decrypts + re-inflates it.
        store.put(
            str(org),
            "google_calendar",
            {"access_token": "AT"},
            metadata={"channel_title": "Cal", "scopes": ["s1"]},
        )
        client._select_rows = [dict(client.upserted[0])]
        client._select_rows[0]["created_at"] = "2026-05-19T00:00:00+00:00"
        client._select_rows[0]["updated_at"] = "2026-05-19T00:00:00+00:00"

        loaded = store.get(str(org), "google_calendar")
        assert loaded is not None
        assert loaded.tokens == {"access_token": "AT"}
        assert loaded.metadata["channel_title"] == "Cal"
        assert loaded.metadata["scopes"] == ["s1"]


class TestPayloadColumnContract:
    """ANTI-FALSE-GREEN. A permissive mock accepts any payload key; real
    PostgREST 400s on an unknown column. Pin the persisted payload's key
    set to the real ``social_wiring.credentials`` DDL so a column-shape
    drift cannot hide behind the mock."""

    def test_persisted_payload_keys_subset_of_ddl_columns(
        self, fernet_key
    ):
        client = _RecordingClient()
        store = build_credential_store(client, encryption_key=fernet_key)

        store.put(
            str(uuid4()),
            "youtube",
            {"access_token": "AT", "refresh_token": "RT"},
            metadata={
                "channel_id": "UC9",
                "channel_title": "T",
                "scopes": ["x"],
            },
        )

        assert len(client.upserted) == 1
        payload_keys = set(client.upserted[0])
        unknown = payload_keys - _DDL_COLUMNS
        assert not unknown, (
            f"credential_vault wrote columns not in the "
            f"social_wiring.credentials DDL: {sorted(unknown)} "
            f"(payload keys={sorted(payload_keys)}, "
            f"DDL={sorted(_DDL_COLUMNS)})"
        )

    def test_metadata_only_subset_still_legal(
        self, fernet_key
    ):
        """The first OAuth-callback upsert writes scopes only (no channel
        yet). That partial payload must also stay within the DDL."""
        client = _RecordingClient()
        store = build_credential_store(client, encryption_key=fernet_key)

        store.put(
            str(uuid4()),
            "youtube",
            {"access_token": "AT"},
            metadata={"scopes": []},
        )

        assert set(client.upserted[0]) - _DDL_COLUMNS == set()


class TestFakeFallbackIsNotReachableViaSeam:
    """Sanity: build_credential_store NEVER returns a FakeCredentialStore
    — that would be a silent degrade. With a valid key it is always the
    encrypted Real store; without a key it raises (covered above)."""

    def test_seam_never_returns_fake(self, fernet_key):
        store = build_credential_store(
            _RecordingClient(), encryption_key=fernet_key
        )
        assert not isinstance(store, FakeCredentialStore)
        assert isinstance(store, SupabaseCredentialStore)
