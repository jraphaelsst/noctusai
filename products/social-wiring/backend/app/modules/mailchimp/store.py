"""Per-org Mailchimp connection store — single row per org with Fernet-encrypted
API key.

Mirrors ``app/services/whatsapp_connection_store.py`` but org-keyed (no
user_id). The API key is write-only: ``get_connection`` never decrypts
unless ``decrypt=True`` is passed (used only by the deps layer when it needs
to build a live client).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.services.credential_vault import (
    CredentialStoreError,
    require_fernet,
)

__all__ = [
    "MailchimpConnectionRecord",
    "MailchimpConnectionStore",
    "build_mailchimp_connection_store",
]

_SCHEMA = "social_wiring"
_TABLE = "mailchimp_connections"


@dataclass(frozen=True)
class MailchimpConnectionRecord:
    """One per-scope Mailchimp connection.

    Scope = ``(org_id, client_id)``. ``client_id`` is ``None`` for the
    org-level default connection, or the owning cliente's id for a
    per-cliente connection (migration 019, mirrors integration_accounts /
    whatsapp_connections).

    ``api_key`` is populated ONLY when the caller explicitly requests
    decryption (``decrypt=True``); it is ``None`` on the read/probe path so
    the secret never rides a GET response.
    """

    id: UUID
    org_id: UUID
    server_prefix: str
    audience_id: Optional[str]
    created_at: Any
    updated_at: Any
    api_key: Optional[str] = None
    client_id: Optional[UUID] = None


class MailchimpConnectionStore:
    """CRUD over ``social_wiring.mailchimp_connections`` with Fernet encryption
    of the API key. Backed by an admin/service-role client; every query filters
    by ``org_id`` explicitly (defense in depth on top of RLS)."""

    def __init__(self, client: Any, *, fernet: Fernet):
        self._client = client
        self._fernet = fernet

    # ─── helpers ──────────────────────────────────────────────────────────
    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _encrypt(self, api_key: str) -> str:
        return self._fernet.encrypt(api_key.encode("utf-8")).decode("ascii")

    def _decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise CredentialStoreError(
                "Mailchimp API key could not be decrypted "
                "(ENCRYPTION_KEY mismatch or tampered ciphertext)."
            ) from exc

    @staticmethod
    def _norm_client_id(value: Any) -> Optional[str]:
        """Normalise a client_id (UUID / str / None / "") to a canonical
        ``str`` or ``None`` for scope comparison."""
        if value in (None, ""):
            return None
        return str(value)

    @classmethod
    def _record(
        cls, row: dict[str, Any], *, api_key: Optional[str] = None
    ) -> MailchimpConnectionRecord:
        raw_cid = row.get("client_id")
        client_id = UUID(str(raw_cid)) if raw_cid not in (None, "") else None
        return MailchimpConnectionRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            server_prefix=row["server_prefix"],
            audience_id=row.get("audience_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            api_key=api_key,
            client_id=client_id,
        )

    def _fetch_scoped_row(
        self, org_id: UUID, client_id: Optional[UUID]
    ) -> Optional[dict[str, Any]]:
        """Return the raw row for ``(org_id, client_id)`` scope or None.

        Filtering by ``client_id IS NULL`` is done in Python (not ``.eq(col,
        None)``): a ``= NULL`` predicate never matches on SQLite and PostgREST
        needs ``is.null`` — resolving in-memory keeps the store portable across
        both the dev SQLiteClient and the prod admin client. Row counts per org
        are tiny (one org-default + one per cliente)."""
        resp = self._table().select("*").eq("org_id", str(org_id)).execute()
        target = self._norm_client_id(client_id)
        for row in list(resp.data or []):
            if self._norm_client_id(row.get("client_id")) == target:
                return row
        return None

    # ─── reads ────────────────────────────────────────────────────────────
    def get_connection(
        self,
        org_id: UUID,
        *,
        client_id: Optional[UUID] = None,
        decrypt: bool = False,
    ) -> Optional[MailchimpConnectionRecord]:
        """Fetch the connection row for ``(org_id, client_id)`` scope.

        ``client_id=None`` resolves the org-level default (client_id IS NULL);
        a UUID resolves that cliente's connection. ``decrypt=True`` populates
        ``record.api_key`` (only for the live-client path)."""
        row = self._fetch_scoped_row(org_id, client_id)
        if row is None:
            return None
        api_key = self._decrypt(row["encrypted_api_key"]) if decrypt else None
        return self._record(row, api_key=api_key)

    # ─── writes ───────────────────────────────────────────────────────────
    def upsert_connection(
        self,
        *,
        org_id: UUID,
        api_key: str,
        server_prefix: str,
        audience_id: Optional[str] = None,
        client_id: Optional[UUID] = None,
    ) -> MailchimpConnectionRecord:
        """Insert-or-replace the connection row for ``(org_id, client_id)``.

        Read-then-write (not DB upsert): the at-most-one-per-scope invariant is
        enforced by two PARTIAL unique indexes (migration 019), which cannot be
        named as a PostgREST ``on_conflict`` target. Resolving the existing row
        first (by scope) then updating it by primary key is portable across the
        dev SQLiteClient and the prod admin client, and keeps NULL client_id
        semantics correct."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self._fetch_scoped_row(org_id, client_id)
        if existing is not None:
            patch: dict[str, Any] = {
                "encrypted_api_key": self._encrypt(api_key),
                "server_prefix": server_prefix,
                "audience_id": audience_id,
                "updated_at": now,
            }
            resp = (
                self._table()
                .update(patch)
                .eq("id", str(existing["id"]))
                .execute()
            )
            rows = list(resp.data or [])
            return self._record(rows[0]) if rows else self.get_connection(
                org_id, client_id=client_id
            ) or self._record({**existing, **patch})

        payload: dict[str, Any] = {
            "org_id": str(org_id),
            "client_id": str(client_id) if client_id is not None else None,
            "encrypted_api_key": self._encrypt(api_key),
            "server_prefix": server_prefix,
            "audience_id": audience_id,
            "updated_at": now,
        }
        resp = self._table().insert(payload).execute()
        rows = list(resp.data or [])
        if not rows:
            # Some SQLite test paths return empty data on insert; re-read.
            return self.get_connection(org_id, client_id=client_id) or self._record(
                payload
            )
        return self._record(rows[0])

    def set_audience(
        self,
        org_id: UUID,
        audience_id: str,
        *,
        client_id: Optional[UUID] = None,
    ) -> Optional[MailchimpConnectionRecord]:
        """Update ``audience_id`` on the scoped connection (org-default when
        ``client_id`` is None). Resolves the scoped row by id first so the
        NULL-client_id case works on both clients."""
        existing = self._fetch_scoped_row(org_id, client_id)
        if existing is None:
            return None
        patch: dict[str, Any] = {
            "audience_id": audience_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = (
            self._table()
            .update(patch)
            .eq("id", str(existing["id"]))
            .execute()
        )
        rows = list(resp.data or [])
        return self._record(rows[0]) if rows else None

    def delete_connection(
        self,
        org_id: UUID,
        *,
        client_id: Optional[UUID] = None,
    ) -> bool:
        """Delete the scoped connection (org-default when ``client_id`` is
        None). Resolves the scoped row by id first."""
        existing = self._fetch_scoped_row(org_id, client_id)
        if existing is None:
            return False
        resp = (
            self._table()
            .delete()
            .eq("id", str(existing["id"]))
            .execute()
        )
        return bool(resp.data)


def build_mailchimp_connection_store(
    client: Any, *, encryption_key: Optional[str] = None
) -> MailchimpConnectionStore:
    """Build a :class:`MailchimpConnectionStore` for ``client``.

    Validates the Fernet key loudly (missing/malformed →
    :class:`EncryptionNotConfigured`, which routers map to 503) — same
    fail-loud pattern as ``build_whatsapp_connection_store``.
    The ``encryption_key`` kwarg is the DI seam: tests inject a test key;
    production resolves ``settings.encryption_key``.
    """
    from app.config import settings

    key = encryption_key if encryption_key is not None else settings.encryption_key
    fernet = require_fernet(key)
    return MailchimpConnectionStore(client, fernet=fernet)
