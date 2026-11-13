"""Telegram "lines": one bot token per row, N per org, ORG-scoped, token encrypted at rest.

Mirrors ``whatsapp/connection_store.py`` (Protocol + Fake + Supabase-backed real). Crypto is the seed primitive
``noctusai_lib.security.encrypted_tokens`` (Fernet; first key writes, ``MultiKeyDecryptor`` reads so a rotation window
works) -- no second crypto path. The list path NEVER decrypts: it exposes only ``token_last4`` (UI shows last-4).
``user_id`` / ``created_by`` is creator provenance, never a scoping predicate (the 2026-09 WhatsApp incident).
A bot can serve only ONE line platform-wide (``bot_id`` unique): two lines on one bot would fight over its webhook.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, Sequence
from uuid import UUID, uuid4

from noctusai_lib.security.encrypted_tokens import MultiKeyDecryptor, encrypt

LINE_STATUSES = ("active", "suspended", "needs_reconnection")
DEFAULT_TABLE = "telegram_lines"


class TelegramLineStoreError(RuntimeError):
    """A stored token could not be decrypted (key mismatch / tampering) -- fail-loud, never a silent None."""


class TelegramLineConflictError(RuntimeError):
    """This bot already backs another line (``bot_id`` is unique)."""


@dataclass(frozen=True)
class TelegramLineRecord:
    id: UUID
    org_id: UUID
    created_by: UUID
    label: str
    bot_id: int
    bot_username: str
    token_last4: str
    webhook_token: str
    status: str = "active"
    created_at: Any = None
    updated_at: Any = None
    #: populated ONLY by ``get_line(decrypt=True)`` (live Bot API ops / secret-token verification).
    bot_token: Optional[str] = field(default=None, repr=False)
    webhook_secret: Optional[str] = field(default=None, repr=False)


class TelegramLineStore(Protocol):
    def create_line(self, *, org_id: UUID, created_by: UUID, label: str, bot_token: str, bot_id: int,
                    bot_username: str) -> TelegramLineRecord: ...
    def list_lines(self, *, org_id: UUID) -> list[TelegramLineRecord]: ...
    def get_line(self, *, line_id: UUID, org_id: UUID, decrypt: bool = False) -> Optional[TelegramLineRecord]: ...
    def get_by_webhook_token(self, token: str, *, decrypt: bool = False) -> Optional[TelegramLineRecord]: ...
    def rotate_token(self, *, line_id: UUID, org_id: UUID, bot_token: str, bot_id: int,
                     bot_username: str) -> Optional[TelegramLineRecord]: ...
    def set_status(self, *, line_id: UUID, org_id: UUID, status: str) -> Optional[TelegramLineRecord]: ...
    def delete_line(self, *, line_id: UUID, org_id: UUID) -> bool: ...


class _Codec:
    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("TelegramLineStore needs at least one encryption key")
        self._write_key = keys[0]
        self._read = MultiKeyDecryptor(list(keys))

    def enc(self, plaintext: str) -> str:
        return encrypt(plaintext, self._write_key)

    def dec(self, ciphertext: str) -> str:
        try:
            return self._read.decrypt(ciphertext)
        except ValueError as exc:
            raise TelegramLineStoreError(
                "Telegram line secret could not be decrypted (encryption key mismatch or tampered ciphertext)."
            ) from exc


def _check_status(status: str) -> str:
    if status not in LINE_STATUSES:
        raise ValueError(f"status must be one of {LINE_STATUSES}, got {status!r}")
    return status


def _new_secrets() -> tuple[str, str]:
    # token_urlsafe emits A-Za-z0-9_-, exactly the setWebhook secret_token alphabet.
    return secrets.token_urlsafe(24), secrets.token_urlsafe(32)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeTelegramLineStore:
    """In-memory store with the Real store's semantics (org scoping, unique bot, encrypted-at-rest ``rows``)."""

    def __init__(self, keys: Sequence[bytes]) -> None:
        self._codec = _Codec(keys)
        self.rows: dict[UUID, dict[str, Any]] = {}

    def _rec(self, row: dict[str, Any], decrypt: bool) -> TelegramLineRecord:
        return _record(row, self._codec if decrypt else None)

    def create_line(self, *, org_id, created_by, label, bot_token, bot_id, bot_username):
        if any(r["bot_id"] == bot_id for r in self.rows.values()):
            raise TelegramLineConflictError("bot already connected to another line")
        wt, ws = _new_secrets()
        row = _insert_payload(self._codec, org_id, created_by, label, bot_token, bot_id, bot_username, wt, ws)
        row.update(id=str(uuid4()), created_at=_now(), updated_at=_now())
        self.rows[UUID(row["id"])] = row
        return self._rec(row, False)

    def list_lines(self, *, org_id):
        rows = [r for r in self.rows.values() if r["org_id"] == str(org_id)]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [self._rec(r, False) for r in rows]

    def get_line(self, *, line_id, org_id, decrypt=False):
        row = self.rows.get(line_id)
        return self._rec(row, decrypt) if row and row["org_id"] == str(org_id) else None

    def get_by_webhook_token(self, token, *, decrypt=False):
        for r in self.rows.values():
            if secrets.compare_digest(r["webhook_token"], token):
                return self._rec(r, decrypt)
        return None

    def rotate_token(self, *, line_id, org_id, bot_token, bot_id, bot_username):
        row = self.rows.get(line_id)
        if not row or row["org_id"] != str(org_id):
            return None
        if any(r["bot_id"] == bot_id and i != line_id for i, r in self.rows.items()):
            raise TelegramLineConflictError("bot already connected to another line")
        row.update(_token_patch(self._codec, bot_token, bot_id, bot_username))
        return self._rec(row, False)

    def set_status(self, *, line_id, org_id, status):
        _check_status(status)
        row = self.rows.get(line_id)
        if not row or row["org_id"] != str(org_id):
            return None
        row.update(status=status, updated_at=_now())
        return self._rec(row, False)

    def delete_line(self, *, line_id, org_id):
        row = self.rows.get(line_id)
        if not row or row["org_id"] != str(org_id):
            return False
        del self.rows[line_id]
        return True


class SupabaseTelegramLineStore:
    """CRUD over ``<schema>.telegram_lines`` through a service-role client. Every query filters ``org_id``
    explicitly: a service-role client bypasses RLS, so this filter is the real enforcement."""

    def __init__(self, client: Any, *, keys: Sequence[bytes], schema: str, table: str = DEFAULT_TABLE) -> None:
        self._client = client
        self._codec = _Codec(keys)
        self._schema = schema
        self._table_name = table

    def _table(self):
        return self._client.schema(self._schema).table(self._table_name)

    def create_line(self, *, org_id, created_by, label, bot_token, bot_id, bot_username):
        if list(self._table().select("id").eq("bot_id", bot_id).execute().data or []):
            raise TelegramLineConflictError("bot already connected to another line")
        wt, ws = _new_secrets()
        payload = _insert_payload(self._codec, org_id, created_by, label, bot_token, bot_id, bot_username, wt, ws)
        rows = list(self._table().insert(payload).execute().data or [])
        return _record(rows[0] if rows else payload, None)

    def list_lines(self, *, org_id):
        rows = list(self._table().select("*").eq("org_id", str(org_id)).execute().data or [])
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return [_record(r, None) for r in rows]

    def get_line(self, *, line_id, org_id, decrypt=False):
        rows = list(self._table().select("*").eq("id", str(line_id)).eq("org_id", str(org_id)).execute().data or [])
        return _record(rows[0], self._codec if decrypt else None) if rows else None

    def get_by_webhook_token(self, token, *, decrypt=False):
        rows = list(self._table().select("*").eq("webhook_token", token).execute().data or [])
        return _record(rows[0], self._codec if decrypt else None) if rows else None

    def rotate_token(self, *, line_id, org_id, bot_token, bot_id, bot_username):
        clash = list(self._table().select("id").eq("bot_id", bot_id).neq("id", str(line_id)).execute().data or [])
        if clash:
            raise TelegramLineConflictError("bot already connected to another line")
        rows = list(self._table().update(_token_patch(self._codec, bot_token, bot_id, bot_username))
                    .eq("id", str(line_id)).eq("org_id", str(org_id)).execute().data or [])
        return _record(rows[0], None) if rows else None

    def set_status(self, *, line_id, org_id, status):
        _check_status(status)
        rows = list(self._table().update({"status": status, "updated_at": _now()})
                    .eq("id", str(line_id)).eq("org_id", str(org_id)).execute().data or [])
        return _record(rows[0], None) if rows else None

    def delete_line(self, *, line_id, org_id):
        return bool(self._table().delete().eq("id", str(line_id)).eq("org_id", str(org_id)).execute().data)


def _insert_payload(codec: _Codec, org_id, created_by, label, bot_token, bot_id, bot_username, wt, ws) -> dict[str, Any]:
    return {
        "org_id": str(org_id), "created_by": str(created_by), "label": label, "bot_id": int(bot_id),
        "bot_username": bot_username, "encrypted_bot_token": codec.enc(bot_token), "token_last4": bot_token[-4:],
        "webhook_token": wt, "encrypted_webhook_secret": codec.enc(ws), "status": "active",
    }


def _token_patch(codec: _Codec, bot_token: str, bot_id: int, bot_username: str) -> dict[str, Any]:
    # a rotated token also rotates the webhook secret: the caller must re-run connect_webhook afterwards
    return {"encrypted_bot_token": codec.enc(bot_token), "token_last4": bot_token[-4:], "bot_id": int(bot_id),
            "bot_username": bot_username, "encrypted_webhook_secret": codec.enc(secrets.token_urlsafe(32)),
            "status": "active", "updated_at": _now()}


def _record(row: dict[str, Any], codec: Optional[_Codec]) -> TelegramLineRecord:
    return TelegramLineRecord(
        id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), created_by=UUID(str(row["created_by"])),
        label=row["label"], bot_id=int(row["bot_id"]), bot_username=row.get("bot_username") or "",
        token_last4=row.get("token_last4") or "", webhook_token=row["webhook_token"],
        status=row.get("status") or "active", created_at=row.get("created_at"), updated_at=row.get("updated_at"),
        bot_token=codec.dec(row["encrypted_bot_token"]) if codec else None,
        webhook_secret=codec.dec(row["encrypted_webhook_secret"]) if codec else None,
    )


def build_telegram_line_store(
    client: Any, *, keys: Sequence[bytes], schema: str, table: str = DEFAULT_TABLE,
) -> SupabaseTelegramLineStore:
    """Real store for ``client``. ``keys`` empty/malformed raises loudly (callers map it to a 503 config gap)."""
    return SupabaseTelegramLineStore(client, keys=keys, schema=schema, table=table)
