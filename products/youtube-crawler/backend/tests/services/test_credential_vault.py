"""Tests for `app.services.credential_vault`.

The vault is a thin wrapper over `noctusai_lib.security.encrypted_tokens`.
These tests cover:
  - the wrapping contract (encrypt → decrypt round-trips losslessly)
  - the misconfig error mode (missing / malformed key)
  - the settings-loading factory (`make_vault_from_settings`)

Per `KB § PATTERNS/testing.md`, pure-crypto modules are exempt from
Protocol+Fake+Real. We test against the real Fernet primitive here.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.services.credential_vault import (
    VaultKeyMissingError,
    VaultService,
    make_vault_from_settings,
)


# ─── VaultService construction ────────────────────────────────────────────────


class TestVaultServiceConstruction:
    """Construction-time validation surfaces deployment errors loudly."""

    def test_constructs_with_valid_fernet_key(self):
        key = Fernet.generate_key()
        vault = VaultService(key=key)
        assert vault is not None

    def test_empty_bytes_raises_vault_key_missing(self):
        with pytest.raises(VaultKeyMissingError, match="non-empty Fernet key"):
            VaultService(key=b"")

    def test_wrong_length_raises_vault_key_missing(self):
        # 32 bytes — looks like raw entropy, not a Fernet (44-byte b64) key.
        with pytest.raises(VaultKeyMissingError, match="length is 32"):
            VaultService(key=b"a" * 32)

    def test_string_key_is_coerced_to_bytes(self):
        # Users frequently store the key as a plain str in .env; the
        # constructor should accept the str → bytes coercion.
        key_str = Fernet.generate_key().decode("ascii")
        vault = VaultService(key=key_str)  # type: ignore[arg-type]
        # Round-trip proves the coerced key was usable.
        ct = vault.encrypt("hello")
        assert vault.decrypt(ct) == "hello"


# ─── Roundtrip ───────────────────────────────────────────────────────────────


class TestRoundtrip:
    """Encrypt → decrypt must return the original plaintext verbatim."""

    def test_roundtrip_simple_string(self):
        vault = VaultService(key=Fernet.generate_key())
        original = "google-refresh-token-1//XYZ_abc-DEF456"
        ct = vault.encrypt(original)
        assert ct != original  # the ciphertext is NOT the plaintext
        assert vault.decrypt(ct) == original

    def test_roundtrip_unicode(self):
        vault = VaultService(key=Fernet.generate_key())
        original = "operator@noctusai.com.br ✓ joão"
        ct = vault.encrypt(original)
        assert vault.decrypt(ct) == original

    def test_two_encrypts_of_same_plaintext_differ(self):
        """Fernet embeds an IV — same plaintext yields different ciphertext.

        This is a property tests *must* hold: deterministic ciphertext would
        leak plaintext-equality.
        """
        vault = VaultService(key=Fernet.generate_key())
        ct1 = vault.encrypt("same")
        ct2 = vault.encrypt("same")
        assert ct1 != ct2
        # Both still decrypt to the same plaintext.
        assert vault.decrypt(ct1) == vault.decrypt(ct2) == "same"

    def test_empty_plaintext_raises(self):
        vault = VaultService(key=Fernet.generate_key())
        with pytest.raises(ValueError, match="non-empty plaintext"):
            vault.encrypt("")

    def test_decrypt_with_wrong_key_raises(self):
        v1 = VaultService(key=Fernet.generate_key())
        v2 = VaultService(key=Fernet.generate_key())
        ct = v1.encrypt("secret")
        with pytest.raises(ValueError, match="invalid ciphertext or wrong key"):
            v2.decrypt(ct)

    def test_decrypt_tampered_ciphertext_raises(self):
        vault = VaultService(key=Fernet.generate_key())
        ct = vault.encrypt("secret")
        # Tamper: flip the last char (Fernet's HMAC catches this).
        tampered = ct[:-1] + ("A" if ct[-1] != "A" else "B")
        with pytest.raises(ValueError, match="invalid ciphertext or wrong key"):
            vault.decrypt(tampered)


# ─── Factory ─────────────────────────────────────────────────────────────────


class _FakeSettings:
    """Tiny stand-in for SeedSettings — avoids importing the live settings."""

    def __init__(self, key: str | None = None) -> None:
        # Mirror the SeedSettings attribute name exactly.
        self.youtube_crawler_vault_key = key or ""


class TestMakeVaultFromSettings:
    """The factory loads the key out-of-band from settings."""

    def test_builds_vault_when_key_set(self):
        key = Fernet.generate_key().decode("ascii")
        settings = _FakeSettings(key=key)
        vault = make_vault_from_settings(settings)
        # Sanity: roundtrip with the resulting vault.
        ct = vault.encrypt("hello")
        assert vault.decrypt(ct) == "hello"

    def test_missing_key_raises_vault_key_missing(self):
        settings = _FakeSettings(key="")
        with pytest.raises(VaultKeyMissingError, match="YOUTUBE_CRAWLER_VAULT_KEY is not set"):
            make_vault_from_settings(settings)

    def test_attribute_absent_raises_vault_key_missing(self):
        """Settings object without the attribute also raises (defensive)."""
        class _Bare:
            pass
        with pytest.raises(VaultKeyMissingError):
            make_vault_from_settings(_Bare())
