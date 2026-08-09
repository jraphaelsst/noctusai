"""Per-org multi-account integration credential service.

Provides CRUD over ``social_wiring.integration_accounts``, using the
seed's Fernet primitive via ``credential_vault.require_fernet`` — zero
inline crypto code here. Follows the same pattern as
``WhatsAppConnectionStore`` (which was the N=1 precedent for this shape).

Design rule (memory feedback_seed_shape_vs_primitive_consume):
  The seed CredentialStore is single-row-per-(org, provider). This service
  handles the multi-row-per-account case. Encryption is still consumed via
  the seed's Fernet primitive through ``credential_vault.require_fernet``.
  NOT a fork of the seed Protocol.

NEVER expose ``encrypted_credential`` or decrypted credential data in the
public ``IntegrationAccount`` response model. ``decrypt_credential`` is
a backend-internal method only (used by services that need to make API
calls — never by REST routes).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken

from app.services.credential_vault import CredentialStoreError, require_fernet

logger = logging.getLogger(__name__)

__all__ = [
    "IntegrationAccount",
    "IntegrationAccountService",
    "IntegrationAccountNotFound",
    "build_integration_account_service",
    "_UNSET",
]

_SCHEMA = "social_wiring"
_TABLE = "integration_accounts"


@dataclass(frozen=True)
class IntegrationAccount:
    """Public representation of an integration account row.

    ``encrypted_credential`` is intentionally absent — this DTO is safe
    to serialize to API responses.
    """

    id: UUID
    org_id: UUID
    provider: str
    account_label: str
    metadata: dict[str, Any]
    is_default: bool
    created_at: Any
    updated_at: Any
    # Channel-object columns (migration 008)
    marca_id: Optional[UUID]
    status: str
    channel_info: dict[str, Any]
    last_synced_at: Any


class IntegrationAccountNotFound(Exception):
    """Raised when an account row doesn't exist or isn't owned by the org."""


# Sentinel for update_account: distinguishes "caller passed None (clear the
# FK)" from "caller did not pass marca_id at all (leave unchanged)".
_UNSET = object()


class IntegrationAccountService:
    """CRUD over ``social_wiring.integration_accounts`` with Fernet
    encryption of the credential blob. Backed by an admin/service-role
    Supabase client; every query filters ``org_id`` explicitly (defense
    in depth on top of RLS)."""

    def __init__(self, client: Any, *, fernet: Fernet):
        self._client = client
        self._fernet = fernet

    # ─── helpers ──────────────────────────────────────────────────────
    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _encrypt(self, credential_dict: dict) -> bytes:
        """Fernet-encrypt the credential dict to bytes."""
        payload = json.dumps(credential_dict).encode("utf-8")
        return self._fernet.encrypt(payload)

    def _decrypt(self, encrypted: Any) -> dict:
        """Fernet-decrypt bytes/str back to a dict.

        Raises ``CredentialStoreError`` on key-mismatch or tampered
        ciphertext — maps to a 503 config-gap at the router layer.
        """
        try:
            raw = encrypted
            if isinstance(raw, memoryview):
                raw = bytes(raw)
            if isinstance(raw, str):
                # PostgREST returns a `bytea` column as a hex-encoded string
                # prefixed with "\x" (e.g. "\x6741414141..."). Encoding that
                # literal string as UTF-8 yields the hex TEXT, not the Fernet
                # token bytes — Fernet then raises InvalidToken, which *looks*
                # like a key mismatch but is really a read-format bug. So
                # hex-decode the bytea repr back to the original token bytes.
                # A non-prefixed str is an ascii-safe Fernet token stored in a
                # TEXT column → encode it directly. (The SQLite test Fake
                # returns bytes, so only the real-PG parity test exercises the
                # "\x" branch — see test_jsonb_payload_shape / cred round-trip.)
                if raw.startswith("\\x"):
                    raw = bytes.fromhex(raw[2:])
                else:
                    raw = raw.encode("utf-8")
            plaintext = self._fernet.decrypt(raw)
            return json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, Exception) as exc:
            raise CredentialStoreError(
                f"credential decryption failed — key mismatch or tampered data: {exc}"
            ) from exc

    def _row_to_account(self, row: dict) -> IntegrationAccount:
        raw_meta = row.get("metadata") or {}
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except Exception:
                raw_meta = {}
        raw_channel_info = row.get("channel_info") or {}
        if isinstance(raw_channel_info, str):
            try:
                raw_channel_info = json.loads(raw_channel_info)
            except Exception:
                raw_channel_info = {}
        raw_marca_id = row.get("marca_id")
        marca_id = UUID(str(raw_marca_id)) if raw_marca_id else None
        return IntegrationAccount(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            provider=row["provider"],
            account_label=row["account_label"],
            metadata=raw_meta,
            is_default=bool(row.get("is_default", False)),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            marca_id=marca_id,
            status=row.get("status") or "validated",
            channel_info=raw_channel_info,
            last_synced_at=row.get("last_synced_at"),
        )

    def _require_row(self, account_id: UUID, org_id: UUID) -> dict:
        """Fetch a row owner-scoped or raise ``IntegrationAccountNotFound``."""
        resp = (
            self._table()
            .select("*")
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise IntegrationAccountNotFound(
                f"integration account {account_id} not found for org {org_id}"
            )
        return rows[0]

    # ─── CRUD ─────────────────────────────────────────────────────────

    def list_accounts(
        self,
        org_id: UUID,
        provider: Optional[str] = None,
        marca_id: Optional[UUID] = None,
    ) -> list[IntegrationAccount]:
        """List integration accounts for an org, optionally filtered by
        provider and/or marca_id."""
        q = self._table().select("*").eq("org_id", str(org_id))
        if provider:
            q = q.eq("provider", provider)
        if marca_id is not None:
            q = q.eq("marca_id", str(marca_id))
        resp = q.execute()
        return [self._row_to_account(r) for r in (resp.data or [])]

    def get_account(
        self,
        account_id: UUID,
        org_id: UUID,
    ) -> Optional[IntegrationAccount]:
        """Fetch one account or return None if it doesn't exist / wrong org."""
        try:
            row = self._require_row(account_id, org_id)
            return self._row_to_account(row)
        except IntegrationAccountNotFound:
            return None

    def create_account(
        self,
        org_id: UUID,
        provider: str,
        account_label: str,
        credential_dict: dict,
        metadata: Optional[dict] = None,
        is_default: bool = False,
        marca_id: Optional[UUID] = None,
        status: str = "validated",
    ) -> IntegrationAccount:
        """Create a new integration account row.

        The credential_dict is Fernet-encrypted before storage; only the
        ciphertext bytes land in the DB.
        """
        encrypted = self._encrypt(credential_dict)
        # bytea is stored as bytes; some clients expect a hex string.
        # Store as hex string so it round-trips through Supabase text columns.
        encrypted_str = encrypted.decode("utf-8") if isinstance(encrypted, bytes) else encrypted

        row_id = str(uuid4())
        data = {
            "id": row_id,
            "org_id": str(org_id),
            "provider": provider,
            "account_label": account_label.strip(),
            "encrypted_credential": encrypted_str,
            "metadata": metadata or {},
            "is_default": is_default,
            "status": status,
        }
        if marca_id is not None:
            data["marca_id"] = str(marca_id)
        if is_default:
            # Clear existing defaults for this provider before inserting.
            self._clear_defaults(org_id=org_id, provider=provider)
        resp = self._table().insert(data).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError("integration_account insert returned no data")
        return self._row_to_account(rows[0])

    def update_account(
        self,
        account_id: UUID,
        org_id: UUID,
        account_label: Optional[str] = None,
        metadata: Optional[dict] = None,
        is_default: Optional[bool] = None,
        marca_id: Any = _UNSET,
        status: Optional[str] = None,
    ) -> IntegrationAccount:
        """Update label / metadata / is_default / marca_id / status.

        ``marca_id`` uses the ``_UNSET`` sentinel so passing ``None``
        explicitly clears the FK, while omitting the arg leaves it unchanged.
        credential cannot be patched via this method — re-create the account
        to rotate keys.
        """
        # Confirm the row exists and belongs to this org.
        self._require_row(account_id, org_id)

        updates: dict = {}
        if account_label is not None:
            updates["account_label"] = account_label.strip()
        if metadata is not None:
            updates["metadata"] = metadata
        if is_default is not None:
            updates["is_default"] = is_default
            if is_default:
                # Fetch the provider to clear other defaults.
                row = self._require_row(account_id, org_id)
                self._clear_defaults(
                    org_id=org_id,
                    provider=row["provider"],
                    exclude_id=account_id,
                )
        if marca_id is not _UNSET:
            # Explicit None clears the FK; a UUID sets it.
            updates["marca_id"] = str(marca_id) if marca_id is not None else None
        if status is not None:
            updates["status"] = status

        if not updates:
            # Nothing to do — return current state.
            return self._row_to_account(self._require_row(account_id, org_id))

        from datetime import timezone
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = (
            self._table()
            .update(updates)
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise IntegrationAccountNotFound(
                f"integration account {account_id} not found for org {org_id}"
            )
        return self._row_to_account(rows[0])

    def delete_account(self, account_id: UUID, org_id: UUID) -> bool:
        """Delete an account. Returns True if deleted, False if not found."""
        resp = (
            self._table()
            .delete()
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        deleted = resp.data or []
        return len(deleted) > 0

    def set_default(self, account_id: UUID, org_id: UUID) -> IntegrationAccount:
        """Atomically clear other defaults for this provider and set this one.

        Invariant: at most one default per (org, provider) at any time.
        """
        row = self._require_row(account_id, org_id)
        provider = row["provider"]
        self._clear_defaults(org_id=org_id, provider=provider, exclude_id=account_id)
        return self.update_account(account_id, org_id, is_default=True)

    def _clear_defaults(
        self,
        org_id: UUID,
        provider: str,
        exclude_id: Optional[UUID] = None,
    ) -> None:
        """Set is_default=false for all accounts of this provider in this org.

        ``exclude_id`` is respected by clearing ALL defaults first, then
        re-setting ``exclude_id`` afterwards (the caller does that via the
        subsequent update call). SQLiteClient only supports ``.eq()`` filters
        — ``.neq()`` is not available. The two-step approach is safe and
        idempotent: clear-all-defaults then set-one.
        """
        (
            self._table()
            .update({"is_default": False})
            .eq("org_id", str(org_id))
            .eq("provider", provider)
            .eq("is_default", True)
            .execute()
        )

    def decrypt_credential(self, account_id: UUID, org_id: UUID) -> dict:
        """Decrypt and return the raw credential dict for backend use ONLY.

        NEVER call this from REST routes — it returns the plaintext secret.
        Use this in services that need to make API calls (e.g. YouTube
        uploads, Drive reads) after resolving the target account.

        Raises ``IntegrationAccountNotFound`` if the account doesn't exist,
        ``CredentialStoreError`` on decryption failure (key mismatch).
        """
        row = self._require_row(account_id, org_id)
        return self._decrypt(row["encrypted_credential"])

    def update_credential(
        self,
        account_id: UUID,
        org_id: UUID,
        credential_dict: dict,
        metadata: Optional[dict] = None,
    ) -> IntegrationAccount:
        """Re-encrypt + persist a refreshed credential bundle for one account.

        This is the token-refresh path (access_token rotation): a service
        that decrypted the bundle, refreshed it against the provider, and
        needs to persist the new bundle BACK to the same row. Distinct from
        ``update_account`` (which deliberately refuses credential edits to
        keep label/metadata patches safe). ``metadata`` is MERGED into the
        existing metadata when provided (so a refresh that only carries new
        ``expires_at`` doesn't clobber ``channel_id`` / ``channel_title``).

        Raises ``IntegrationAccountNotFound`` if the account doesn't exist
        or isn't owned by ``org_id``.
        """
        from datetime import timezone

        row = self._require_row(account_id, org_id)
        encrypted = self._encrypt(credential_dict)
        encrypted_str = (
            encrypted.decode("utf-8") if isinstance(encrypted, bytes) else encrypted
        )
        updates: dict = {
            "encrypted_credential": encrypted_str,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata is not None:
            existing_meta = self._row_to_account(row).metadata
            merged = {**existing_meta, **metadata}
            updates["metadata"] = merged
        resp = (
            self._table()
            .update(updates)
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise IntegrationAccountNotFound(
                f"integration account {account_id} not found for org {org_id}"
            )
        return self._row_to_account(rows[0])


    def update_channel_info(
        self,
        account_id: UUID,
        org_id: UUID,
        *,
        channel_info: dict,
        status: str,
        last_synced_at: Any,
    ) -> IntegrationAccount:
        """Persist channel_info / status / last_synced_at for one account.

        Owner-scoped (org_id filter). Raises ``IntegrationAccountNotFound``
        if the account doesn't exist or isn't owned by ``org_id``.
        """
        from datetime import timezone

        self._require_row(account_id, org_id)
        updates: dict = {
            "channel_info": channel_info,
            "status": status,
            "last_synced_at": last_synced_at.isoformat() if hasattr(last_synced_at, "isoformat") else last_synced_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = (
            self._table()
            .update(updates)
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise IntegrationAccountNotFound(
                f"integration account {account_id} not found for org {org_id}"
            )
        return self._row_to_account(rows[0])


def build_integration_account_service(
    client: Any,
    *,
    encryption_key: Optional[str] = None,
) -> IntegrationAccountService:
    """Build an ``IntegrationAccountService`` wired to the given Supabase client.

    Validates ``encryption_key`` loudly via the product's ``require_fernet``
    seam (maps missing/invalid key to ``EncryptionNotConfigured`` — callers
    translate to a 503 config-gap response). No inline crypto here.

    DI seam: tests inject ``encryption_key=...``; production resolves from
    ``settings.encryption_key`` at the router layer before calling this.
    """
    from app.config import settings as _settings

    key = encryption_key if encryption_key is not None else _settings.encryption_key
    fernet = require_fernet(key)
    return IntegrationAccountService(client, fernet=fernet)
