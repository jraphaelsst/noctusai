"""Credential vault — Fernet-encrypted refresh/access tokens at rest.

WHY this exists
---------------
Phase 1 of `youtube-crawler-domain-implementation` (see PROJECT.md §6 Phase 1).
The brief asks for `credential_vault.py` exposing a Fernet roundtrip seam.

VERIFY-THE-SEED-SHIPS-IT
------------------------
Seed already ships `noctusai_lib.security.encrypted_tokens` (full surface:
`generate_key` / `encrypt` / `decrypt` / `rotate_key` / `MultiKeyDecryptor`).
This module is a **thin wrapper** over that surface — it adds:

    * settings loading from `YOUTUBE_CRAWLER_VAULT_KEY` env var
    * a single `VaultService` class consumers can inject (so tests can pass
      a deterministic key without monkey-patching env)
    * cached Fernet-key bytes (decoded once per process)

It does NOT re-implement encrypt/decrypt — those delegate verbatim to
`noctusai_lib.security.encrypted_tokens`.

KEY LIFECYCLE
-------------
- Generate with `python -c "from noctusai_lib.security.encrypted_tokens import generate_key; print(generate_key().decode())"`
- Store in `.env` as `YOUTUBE_CRAWLER_VAULT_KEY=…` (gitignored). NEVER commit.
- Rotate via the seed's `rotate_key` + `MultiKeyDecryptor` — out of Phase 1 scope.

LGPD
----
Refresh tokens / access tokens / Google account emails are LGPD-sensitive
(operator's Google account is identifying PII). This vault encrypts the
tokens at rest; the email is stored plaintext (RLS-scoped) so admins can
identify which account is connected without decrypting. Flagged at the
write site in `google_oauth_service.py`.
"""
from __future__ import annotations

from typing import Final

from noctusai_lib.security.encrypted_tokens import decrypt, encrypt


class VaultKeyMissingError(RuntimeError):
    """Raised when the vault is asked to encrypt/decrypt without a configured key.

    Distinct exception type so tests can assert the failure mode and the
    OAuth router can map it to a 503 instead of a generic 500 (the operator
    needs to know it's a deployment-config issue, not a transient error).
    """


class VaultService:
    """Wraps the seed `encrypted_tokens` surface with an injected key.

    Constructor takes the raw Fernet key bytes. Use
    :func:`make_vault_from_settings` for the production path; construct
    directly in tests with `VaultService(key=Fernet.generate_key())` for
    a deterministic per-test key.
    """

    def __init__(self, key: bytes) -> None:
        if not key:
            raise VaultKeyMissingError(
                "VaultService requires a non-empty Fernet key. Generate one "
                "via `Fernet.generate_key()` and set `YOUTUBE_CRAWLER_VAULT_KEY` "
                "in `.env` before deploying."
            )
        # Fernet keys are 44 url-safe base64 bytes (32 bytes entropy + padding);
        # any other length is a misconfiguration. Surface as VaultKeyMissingError
        # so the operator gets a clear "fix your env var" signal instead of a
        # cryptography internal at first use.
        if isinstance(key, str):
            key = key.encode("ascii")
        if len(key) != 44:
            raise VaultKeyMissingError(
                f"YOUTUBE_CRAWLER_VAULT_KEY length is {len(key)} bytes; expected "
                "44 (Fernet's url-safe base64 shape). Regenerate via "
                "`from cryptography.fernet import Fernet; Fernet.generate_key()`."
            )
        self._key: Final[bytes] = key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt `plaintext` with this vault's key. Delegates to seed `encrypt`.

        Raises:
            ValueError: when `plaintext` is empty (propagated from seed —
                empty secrets have no semantic meaning).
        """
        return encrypt(plaintext, self._key)

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt `ciphertext` with this vault's key. Delegates to seed `decrypt`.

        Raises:
            ValueError: when ciphertext is tampered / wrong-key / truncated.
        """
        return decrypt(ciphertext, self._key)


def make_vault_from_settings(settings) -> VaultService:
    """Build a `VaultService` from product settings.

    Reads `settings.youtube_crawler_vault_key` (a str). Tests can bypass this
    by constructing `VaultService(key=...)` directly with a deterministic key.

    Args:
        settings: a `SeedSettings` (or any object exposing the
            `youtube_crawler_vault_key` attribute).

    Raises:
        VaultKeyMissingError: when the env var is unset or empty.
    """
    raw = getattr(settings, "youtube_crawler_vault_key", "") or ""
    if not raw:
        raise VaultKeyMissingError(
            "YOUTUBE_CRAWLER_VAULT_KEY is not set. Generate a key via "
            "`from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())` "
            "and add it to `.env` before deploying. Without it, the credentials "
            "router cannot persist OAuth refresh tokens at rest."
        )
    return VaultService(key=raw.encode("ascii"))


__all__ = [
    "VaultKeyMissingError",
    "VaultService",
    "make_vault_from_settings",
]
