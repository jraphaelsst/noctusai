"""Tests for credential_store — Fernet encrypt/decrypt + DB ops via mock."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.services.credential_store import (
    CredentialStore,
    CredentialStoreError,
    EncryptionNotConfigured,
)


class TestEncryptionConfig:
    def test_empty_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            CredentialStore(MagicMock(), "")

    def test_invalid_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            CredentialStore(MagicMock(), "not-a-fernet-key")

    def test_valid_key_constructs(self):
        key = Fernet.generate_key().decode()
        store = CredentialStore(MagicMock(), key)
        assert store is not None


class TestRoundTrip:
    """Encryption is the most failure-rich seam — round-trip every shape
    we expect to ship through it."""

    def setup_method(self):
        self.key = Fernet.generate_key().decode()
        self.store = CredentialStore(MagicMock(), self.key)

    def test_simple_dict_round_trips(self):
        original = {"access_token": "abc123", "refresh_token": "xyz789"}
        ciphertext = self.store.encrypt_tokens(original)
        assert ciphertext != original
        assert self.store.decrypt_tokens(ciphertext) == original

    def test_nested_dict_round_trips(self):
        original = {
            "access_token": "abc",
            "scopes": ["read", "write"],
            "metadata": {"source": "oauth", "issued": 1735689600},
        }
        ciphertext = self.store.encrypt_tokens(original)
        assert self.store.decrypt_tokens(ciphertext) == original

    def test_empty_dict_round_trips(self):
        ciphertext = self.store.encrypt_tokens({})
        assert self.store.decrypt_tokens(ciphertext) == {}

    def test_unicode_round_trips(self):
        original = {"token": "日本語テスト 🔑"}
        assert self.store.decrypt_tokens(
            self.store.encrypt_tokens(original)
        ) == original


class TestTamperDetection:
    """Fernet is authenticated encryption — any modification of the
    ciphertext must surface as CredentialStoreError, never silently
    decrypt to garbage."""

    def setup_method(self):
        self.key = Fernet.generate_key().decode()
        self.store = CredentialStore(MagicMock(), self.key)

    def test_truncated_ciphertext_raises(self):
        ct = self.store.encrypt_tokens({"access_token": "x"})
        with pytest.raises(CredentialStoreError):
            self.store.decrypt_tokens(ct[:-10])

    def test_wrong_key_raises(self):
        ct = self.store.encrypt_tokens({"access_token": "x"})
        other_store = CredentialStore(MagicMock(), Fernet.generate_key().decode())
        with pytest.raises(CredentialStoreError):
            other_store.decrypt_tokens(ct)


class TestUpsertContract:
    """The ciphertext column never contains plaintext — verify the
    payload the store hands the supabase client has been encrypted."""

    def setup_method(self):
        self.key = Fernet.generate_key().decode()
        self.supabase = MagicMock()
        self.store = CredentialStore(self.supabase, self.key)

    def test_upsert_encrypts_before_persisting(self):
        tokens = {"access_token": "PLAINTEXT-SECRET", "refresh_token": "RT-XYZ"}
        org_id = uuid4()

        # MockSupabaseClient.upsert returns a response with the row back; we
        # simulate that directly with the chained-call pattern PostgREST uses.
        chain = self.supabase.schema.return_value.table.return_value.upsert.return_value
        chain.execute.return_value = MagicMock(
            data=[{
                "id": str(uuid4()),
                "org_id": str(org_id),
                "provider": "youtube",
                "encrypted_tokens": "doesn-t-matter-we-just-passed-this-through",
                "channel_id": None,
                "channel_title": None,
                "scopes": [],
                "created_at": "2026-05-06T12:00:00+00:00",
                "updated_at": "2026-05-06T12:00:00+00:00",
            }]
        )

        # Replace stored ciphertext with one we know decrypts back
        ct = self.store.encrypt_tokens(tokens)
        chain.execute.return_value.data[0]["encrypted_tokens"] = ct

        self.store.upsert(org_id=org_id, provider="youtube", tokens=tokens)

        # Inspect what was passed to .upsert(...)
        call_args = self.supabase.schema.return_value.table.return_value.upsert.call_args
        assert call_args is not None
        payload = call_args.args[0] if call_args.args else call_args.kwargs.get("json")
        assert "PLAINTEXT-SECRET" not in payload["encrypted_tokens"]
        assert "RT-XYZ" not in payload["encrypted_tokens"]
        # The ciphertext is what we'd get back from Fernet — it's an
        # opaque str of base64. Sanity: it's longer than the plaintext
        # (Fernet adds version + IV + HMAC).
        assert len(payload["encrypted_tokens"]) > len(str(tokens))
