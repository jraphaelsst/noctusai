"""Fernet-based encryption for small secrets at rest.

WHY
---
OAuth refresh tokens, API keys, and similar small secrets are written to
durable storage (Postgres rows, dumped `.env` snapshots, KV stores). If
the storage substrate is ever exfiltrated — backup leak, replicated
read-only standby, log line that captured a row — the secrets are
trivially recoverable when stored plaintext. This module wraps
`cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256, authenticated
symmetric encryption) so consumers can encrypt at the boundary of "about
to write to the DB" and decrypt at the boundary of "about to call the
vendor SDK". The plaintext is only ever in process memory, never on
disk.

WHEN to use
-----------
Any small secret that must persist:
- OAuth refresh tokens (Google, Slack, Stripe Connect, …)
- Vendor API keys stored per-tenant (Resend per-org, Supabase service
  keys for tenant projects, …)
- Webhook secrets stored in the DB (instead of a config file)
- Anything <~4KB that's a secret-from-a-third-party

DO NOT use for:
- User passwords — use a password hash (bcrypt / argon2), not symmetric
  encryption. Passwords are never decrypted; they're verified.
- Bulk content encryption — Fernet is fine for KB-sized blobs but slow
  for large payloads; reach for a streaming AEAD if you're north of
  a few MB.

HOW the key is loaded
---------------------
The module is **key-agnostic**. Consumers choose:
- env var (`FERNET_KEY=…`) — simplest; rotate via env-var swap + worker
  restart.
- SOPS-encrypted YAML / JSON in repo + decrypted at boot — works well
  with KMS / age-based deployment.
- HashiCorp Vault / AWS Secrets Manager / GCP Secret Manager — fetch
  at boot; pin to a short cache TTL.

Generate a fresh key with `generate_key()` (returns 32 url-safe base64
bytes — Fernet's native shape). Store the key OUT-OF-BAND from the
ciphertext (the whole point is that the storage compromise + key
compromise are independent events). Do NOT commit the key.

Rotation
--------
1. Generate `new_key = generate_key()`.
2. Deploy with BOTH keys available (`MultiKeyDecryptor([new_key, old_key])`
   on the read path; `encrypt(..., new_key)` on the write path).
3. Re-encrypt existing rows lazily (`rotate_key(old_ciphertext, old_key,
   new_key)`) or eagerly (one-shot script).
4. After all rows are re-encrypted, drop `old_key` from the decryptor
   list.

Recurrence trip-count
---------------------
- N=1: `whatsapp-google-scheduling` stores Google OAuth creds plaintext
  (2026-04). Filed `whatsapp-google-scheduling-encrypt-tokens-migration`
  follow-up to lift onto this helper.
- N=2: `youtube-crawler` (2026-05) — net-new product, ships using this
  helper from day one.
- N≥2 trips the recurrence rule (`KB § PATTERNS/project-execution.md
  § 2.7`); this helper IS the formalization. Filed in
  `seed-hardening-from-youtube-crawler` Phase 1.2.

Exemption from Protocol+Fake+Real
---------------------------------
Per the canonical-shape rule (`KB § PATTERNS/seed-fake-real-adapter.md`),
pure-crypto modules are exempt: a Fake-of-Fernet would either be Fernet
(= the Real) or a `lambda x: x` that doesn't exercise the same code,
giving negative test value. Ship as a flat module of pure functions.

Public surface
--------------
- `generate_key() -> bytes`
- `encrypt(plaintext: str, key: bytes) -> str`
- `decrypt(ciphertext: str, key: bytes) -> str`
- `rotate_key(ciphertext: str, old_key: bytes, new_key: bytes) -> str`
- `MultiKeyDecryptor([key, …])` with `.decrypt(ciphertext) -> str`
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def generate_key() -> bytes:
    """Generate a fresh Fernet key.

    Returns 44 url-safe base64 bytes (32 bytes of entropy, base64-encoded).
    Store this key OUT-OF-BAND from the ciphertext it will protect:
    env var, SOPS-encrypted file decrypted at boot, Vault, AWS Secrets
    Manager, GCP Secret Manager. Never commit the key.
    """
    return Fernet.generate_key()


def encrypt(plaintext: str, key: bytes) -> str:
    """Encrypt `plaintext` with `key`, returning url-safe-base64 ciphertext.

    Raises:
        ValueError: if `plaintext` is empty (encrypting empty is a
            consumer-side bug — no semantic meaning for the empty
            secret).
    """
    if not plaintext:
        raise ValueError("encrypt() requires non-empty plaintext")
    fernet = Fernet(key)
    token = fernet.encrypt(plaintext.encode("utf-8"))
    # Fernet tokens are already url-safe base64; decode to str for ergonomic
    # storage in TEXT columns / JSON fields.
    return token.decode("ascii")


def decrypt(ciphertext: str, key: bytes) -> str:
    """Decrypt `ciphertext` with `key`, returning the original plaintext.

    Raises:
        ValueError: if the ciphertext is tampered, truncated, or was
            encrypted with a different key. Wraps
            `cryptography.fernet.InvalidToken` so consumers don't have
            to import the cryptography package just to handle errors.
    """
    fernet = Fernet(key)
    try:
        plaintext_bytes = fernet.decrypt(ciphertext.encode("ascii"))
    except InvalidToken as exc:
        logger.warning(
            "encrypted_tokens.decrypt failed — tampered ciphertext or wrong key"
        )
        raise ValueError("invalid ciphertext or wrong key") from exc
    return plaintext_bytes.decode("utf-8")


def rotate_key(ciphertext: str, old_key: bytes, new_key: bytes) -> str:
    """Decrypt with `old_key` and re-encrypt with `new_key`.

    Single-call seam for key rotation jobs. Intended use: iterate over
    a table column, call `rotate_key` per row, write the new ciphertext
    back. After all rows are migrated, drop `old_key` from the read
    path's `MultiKeyDecryptor`.

    Raises:
        ValueError: if `ciphertext` cannot be decrypted with `old_key`
            (propagated from `decrypt`), or if the resulting plaintext
            is empty (propagated from `encrypt`).
    """
    plaintext = decrypt(ciphertext, old_key)
    return encrypt(plaintext, new_key)


class MultiKeyDecryptor:
    """Try a sequence of keys on decrypt, in order; first success wins.

    Lets products stage rotations safely:
    - Write path: `encrypt(..., new_key)` — only one key is the
      "current" write key.
    - Read path: `MultiKeyDecryptor([new_key, old_key]).decrypt(...)` —
      tolerates ciphertext written with either key during the migration
      window. Once all rows are re-encrypted, drop `old_key`.

    Order matters: the most-recently-issued key should be FIRST so the
    common case (already-rotated row) succeeds on the first attempt.
    """

    def __init__(self, keys: Sequence[bytes] | Iterable[bytes]) -> None:
        keys_list = list(keys)
        if not keys_list:
            raise ValueError("MultiKeyDecryptor requires at least one key")
        self._keys: list[bytes] = keys_list

    def decrypt(self, ciphertext: str) -> str:
        """Try each key in order; return plaintext on first success.

        Raises:
            ValueError: if no key in the list can decrypt the ciphertext.
        """
        token_bytes = ciphertext.encode("ascii")
        for index, key in enumerate(self._keys):
            fernet = Fernet(key)
            try:
                plaintext_bytes = fernet.decrypt(token_bytes)
            except InvalidToken:
                logger.debug(
                    "MultiKeyDecryptor key #%d did not match; trying next",
                    index,
                )
                continue
            return plaintext_bytes.decode("utf-8")
        logger.warning(
            "MultiKeyDecryptor exhausted %d keys without a match", len(self._keys)
        )
        raise ValueError("invalid ciphertext or no matching key")
