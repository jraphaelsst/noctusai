"""Tests for `noctusai_lib.security.encrypted_tokens`.

Pure-crypto module; tests are network-free and deterministic. We
generate fresh keys per test (no fixed test vectors — Fernet tokens
embed a timestamp + nonce so byte-equality assertions would be flaky
anyway).
"""

from __future__ import annotations

import pytest

from noctusai_lib.security.encrypted_tokens import (
    MultiKeyDecryptor,
    decrypt,
    encrypt,
    generate_key,
    rotate_key,
)


class TestGenerateKey:
    def test_returns_bytes(self):
        key = generate_key()
        assert isinstance(key, bytes)

    def test_length_44(self):
        # Fernet keys are 32 bytes of entropy, url-safe-base64-encoded
        # → 44 ASCII bytes (with the trailing `=` padding char).
        key = generate_key()
        assert len(key) == 44

    def test_each_call_distinct(self):
        # Sanity check that we're not seeing constant output. Probabilistic
        # but the collision space is 2**256.
        assert generate_key() != generate_key()


class TestRoundTrip:
    def test_simple_ascii(self):
        key = generate_key()
        plaintext = "ya29.a0AfH6SMB-mock-oauth-refresh-token"
        ciphertext = encrypt(plaintext, key)
        assert decrypt(ciphertext, key) == plaintext

    def test_unicode_emoji(self):
        key = generate_key()
        plaintext = "secret with emoji 🔐 and accents àéîõü"
        ciphertext = encrypt(plaintext, key)
        assert decrypt(ciphertext, key) == plaintext

    def test_long_payload(self):
        # OAuth tokens are typically <2KB; verify a 4KB payload still works.
        key = generate_key()
        plaintext = "x" * 4096
        ciphertext = encrypt(plaintext, key)
        assert decrypt(ciphertext, key) == plaintext

    def test_ciphertext_is_str(self):
        key = generate_key()
        ciphertext = encrypt("hello", key)
        assert isinstance(ciphertext, str)


class TestErrorPaths:
    def test_empty_plaintext_raises_value_error(self):
        key = generate_key()
        with pytest.raises(ValueError, match="non-empty plaintext"):
            encrypt("", key)

    def test_tampered_ciphertext_raises_value_error(self):
        key = generate_key()
        ciphertext = encrypt("hello", key)
        # Flip a character in the middle of the ciphertext body
        # (avoiding the trailing `=` padding which Fernet may not check).
        tampered = list(ciphertext)
        flip_at = len(tampered) // 2
        tampered[flip_at] = "A" if tampered[flip_at] != "A" else "B"
        tampered_str = "".join(tampered)
        with pytest.raises(ValueError, match="invalid ciphertext"):
            decrypt(tampered_str, key)

    def test_wrong_key_raises_value_error(self):
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt("hello", key1)
        with pytest.raises(ValueError, match="invalid ciphertext"):
            decrypt(ciphertext, key2)

    def test_invalid_token_not_leaked(self):
        # Consumers should not need to import cryptography just to catch
        # decryption failures — we wrap InvalidToken in ValueError.
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt("hello", key1)
        try:
            decrypt(ciphertext, key2)
        except ValueError:
            pass
        else:
            pytest.fail("expected ValueError on wrong key")


class TestRotation:
    def test_rotate_then_decrypt_with_new(self):
        old_key = generate_key()
        new_key = generate_key()
        plaintext = "oauth-refresh-token-abc123"
        old_ciphertext = encrypt(plaintext, old_key)

        new_ciphertext = rotate_key(old_ciphertext, old_key, new_key)

        assert decrypt(new_ciphertext, new_key) == plaintext

    def test_rotated_ciphertext_does_not_decrypt_with_old_key(self):
        old_key = generate_key()
        new_key = generate_key()
        plaintext = "oauth-refresh-token-abc123"
        old_ciphertext = encrypt(plaintext, old_key)

        new_ciphertext = rotate_key(old_ciphertext, old_key, new_key)

        with pytest.raises(ValueError):
            decrypt(new_ciphertext, old_key)

    def test_rotate_with_wrong_old_key_raises(self):
        wrong_old_key = generate_key()
        actual_old_key = generate_key()
        new_key = generate_key()
        ciphertext = encrypt("hello", actual_old_key)

        with pytest.raises(ValueError):
            rotate_key(ciphertext, wrong_old_key, new_key)


class TestMultiKeyDecryptor:
    def test_first_key_wins(self):
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt("hello", key1)
        decryptor = MultiKeyDecryptor([key1, key2])
        assert decryptor.decrypt(ciphertext) == "hello"

    def test_second_key_falls_through(self):
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt("hello-from-key2", key2)
        decryptor = MultiKeyDecryptor([key1, key2])
        assert decryptor.decrypt(ciphertext) == "hello-from-key2"

    def test_no_matching_key_raises(self):
        key1 = generate_key()
        key2 = generate_key()
        rogue_key = generate_key()
        ciphertext = encrypt("hello", rogue_key)
        decryptor = MultiKeyDecryptor([key1, key2])
        with pytest.raises(ValueError, match="no matching key"):
            decryptor.decrypt(ciphertext)

    def test_empty_keys_list_raises(self):
        with pytest.raises(ValueError, match="at least one key"):
            MultiKeyDecryptor([])

    def test_single_key_works(self):
        key = generate_key()
        ciphertext = encrypt("solo", key)
        decryptor = MultiKeyDecryptor([key])
        assert decryptor.decrypt(ciphertext) == "solo"

    def test_iterable_keys_accepted(self):
        # Generators / arbitrary iterables should work, not just lists.
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt("hello", key2)
        decryptor = MultiKeyDecryptor(iter([key1, key2]))
        assert decryptor.decrypt(ciphertext) == "hello"
