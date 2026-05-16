"""Credential persistence with Fernet encryption at rest.

Wraps the ``social_wiring.credentials`` table. Plaintext refresh tokens
never enter the database — every write Fernet-encrypts the JSON token
bundle before INSERT, every read decrypts on the way out. Encryption key
lives in the product's ``.env`` (``ENCRYPTION_KEY``); DB compromise alone
cannot recover tokens.

This is a product-local helper today (N=1 across the platform). If a
second product needs OAuth-token-at-rest (Therapy / Mailing already have
tokenized integrations — Stripe / Resend), absorb into
``noctusai_lib.security.token_store`` and convert this module to a thin
re-export. See KB § PATTERNS/seed-fake-real-adapter.md for the canonical
shape that absorption should produce.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from supabase import Client

logger = logging.getLogger(__name__)

_TABLE = "credentials"
_SCHEMA = "social_wiring"


class CredentialStoreError(Exception):
    """Surface for credential persistence failures.

    Distinct from generic exceptions so router-level handlers can return
    a 503 (configuration / encryption issue) rather than a 500 (server bug).
    """


class EncryptionNotConfigured(CredentialStoreError):
    """ENCRYPTION_KEY missing or invalid — refuse to write plaintext tokens."""


@dataclass
class StoredCredential:
    """Decrypted credential record. Tokens are plaintext in this object —
    never log it, never serialise it raw to API responses."""

    id: UUID
    org_id: UUID
    provider: str
    tokens: dict[str, Any]
    channel_id: str | None
    channel_title: str | None
    scopes: list[str]
    created_at: datetime
    updated_at: datetime


class CredentialStore:
    """Encryption + DB persistence for OAuth credentials.

    The Fernet instance is built once per construct call so an empty /
    invalid ``encryption_key`` fails fast at startup rather than at the
    first write attempt.
    """

    def __init__(self, supabase: Client, encryption_key: str):
        if not encryption_key:
            raise EncryptionNotConfigured(
                "ENCRYPTION_KEY is empty. Generate with `python -c \"from "
                "cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and set it in the "
                "product's .env."
            )
        try:
            self._fernet = Fernet(encryption_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise EncryptionNotConfigured(
                f"ENCRYPTION_KEY is not a valid Fernet key: {exc}. "
                "Regenerate with the snippet in .env.example."
            ) from exc
        self._supabase = supabase

    # ─── Encryption helpers (testable in isolation) ────────────────────
    def encrypt_tokens(self, tokens: dict[str, Any]) -> str:
        """Serialise + encrypt the token bundle to a Fernet ciphertext str."""
        plaintext = json.dumps(tokens, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(plaintext).decode("utf-8")

    def decrypt_tokens(self, ciphertext: str) -> dict[str, Any]:
        """Inverse of :meth:`encrypt_tokens`. Raises CredentialStoreError on
        any cryptographic failure — a tampered or wrong-key ciphertext is
        not silently swallowed."""
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            raise CredentialStoreError(
                "Stored ciphertext failed Fernet decrypt — "
                "key rotation without re-encrypt, or DB tampering."
            ) from exc
        try:
            return json.loads(plaintext)
        except json.JSONDecodeError as exc:
            raise CredentialStoreError(
                "Decrypted payload is not valid JSON — "
                "schema drift or corruption."
            ) from exc

    # ─── DB ops ────────────────────────────────────────────────────────
    def upsert(
        self,
        *,
        org_id: UUID,
        provider: str,
        tokens: dict[str, Any],
        channel_id: str | None = None,
        channel_title: str | None = None,
        scopes: list[str] | None = None,
    ) -> StoredCredential:
        """Insert or update the credential row for (org_id, provider).

        UPSERT semantics — re-running OAuth replaces the prior token bundle
        atomically without leaving a window of two valid records. The
        ciphertext column is fully overwritten on every call (no
        token-merge logic; the OAuth response IS the new full bundle).
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "org_id": str(org_id),
            "provider": provider,
            "encrypted_tokens": self.encrypt_tokens(tokens),
            "channel_id": channel_id,
            "channel_title": channel_title,
            "scopes": scopes or [],
            "updated_at": now,
        }

        response = (
            self._supabase
            .schema(_SCHEMA)
            .table(_TABLE)
            .upsert(payload, on_conflict="org_id,provider")
            .execute()
        )
        if not response.data:
            raise CredentialStoreError(
                f"upsert returned no rows for (org_id={org_id}, provider={provider})"
            )
        return self._row_to_stored(response.data[0])

    def get(self, *, org_id: UUID, provider: str) -> StoredCredential | None:
        """Fetch + decrypt the credential row for (org_id, provider).

        Returns None when no row matches — callers (settings router,
        youtube_service) treat that as "not connected" without raising.
        """
        response = (
            self._supabase
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return self._row_to_stored(response.data[0])

    def delete(self, *, org_id: UUID, provider: str) -> bool:
        """Remove the credential row for (org_id, provider). Returns True
        when a row was deleted, False when no matching row existed.

        Idempotent: deleting an absent record is not an error — that's the
        right shape for the "Disconnect YouTube" UI button.
        """
        response = (
            self._supabase
            .schema(_SCHEMA)
            .table(_TABLE)
            .delete()
            .eq("org_id", str(org_id))
            .eq("provider", provider)
            .execute()
        )
        return bool(response.data)

    def _row_to_stored(self, row: dict[str, Any]) -> StoredCredential:
        return StoredCredential(
            id=UUID(row["id"]),
            org_id=UUID(row["org_id"]),
            provider=row["provider"],
            tokens=self.decrypt_tokens(row["encrypted_tokens"]),
            channel_id=row.get("channel_id"),
            channel_title=row.get("channel_title"),
            scopes=row.get("scopes") or [],
            created_at=_parse_ts(row["created_at"]),
            updated_at=_parse_ts(row["updated_at"]),
        )


def _parse_ts(value: str | datetime) -> datetime:
    """PostgREST returns ISO8601 strings; allow datetime passthrough so
    test fixtures don't have to round-trip through string."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
