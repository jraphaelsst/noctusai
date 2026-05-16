"""Durable persistence + idempotency for WhatsApp / chat messages.

Mirrors the whatsapp-scheduling pattern: every inbound + outbound is
persisted to `social_wiring.conversation_messages` with
``UNIQUE(provider_message_id)`` driving dedup. The duplicate-INSERT
attempt trips the unique constraint and the caller treats the
exception as "already processed" — atomic across the
``message`` + ``message.any`` race that WAHA subscribes us to.

The Redis-backed memory list under ``whatsapp:chatbot:{session_id}``
stays the runtime-fast recall layer the chatbot reads to build its
OpenAI messages; this store is the durable audit log.
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_TABLE = "conversation_messages"


class DuplicateMessage(Exception):
    """Raised when a record with the same ``provider_message_id`` already
    exists. Webhook handlers catch this and return 200 OK without further
    processing — the inbound is being delivered a second time by WAHA."""


@dataclass(frozen=True)
class StoredMessage:
    id: UUID
    session_id: str
    direction: str
    body: str
    provider_message_id: str | None
    authorized: bool


class MessageStore:
    """Per-request collaborator. Constructed from the service-role client
    (the webhook has no JWT context) — RLS policy is service-role open
    for writes, authenticated-read for the operator UI."""

    def __init__(self, *, admin_supabase, org_id: UUID):
        self._admin = admin_supabase
        self._org_id = org_id

    def record(
        self,
        *,
        session_id: str,
        direction: str,
        body: str,
        provider_message_id: str | None = None,
        raw_sender: str | None = None,
        authorized: bool = True,
        structured_payload: dict[str, Any] | None = None,
    ) -> StoredMessage:
        """Insert a row.

        Raises:
            DuplicateMessage: if ``provider_message_id`` already exists in
                the table. Webhook handlers catch this to drop duplicate
                WAHA deliveries (message + message.any for the same id).
        """
        if direction not in {"inbound", "outbound"}:
            raise ValueError(f"invalid direction: {direction}")
        payload = {
            "id": str(_uuid.uuid4()),
            "org_id": str(self._org_id),
            "session_id": session_id,
            "raw_sender": raw_sender,
            "direction": direction,
            "provider_message_id": provider_message_id or None,
            "body": body,
            "authorized": authorized,
            "structured_payload": (
                json.dumps(structured_payload, separators=(",", ":"))
                if structured_payload
                else None
            ),
        }
        try:
            response = (
                self._admin
                .schema(_SCHEMA)
                .table(_TABLE)
                .insert(payload)
                .execute()
            )
        except Exception as exc:
            if provider_message_id and self._is_duplicate_error(exc, provider_message_id):
                raise DuplicateMessage(provider_message_id) from exc
            raise
        rows = response.data or []
        row = rows[0] if rows else payload
        return StoredMessage(
            id=UUID(row["id"]),
            session_id=row["session_id"],
            direction=row["direction"],
            body=row["body"],
            provider_message_id=row.get("provider_message_id"),
            authorized=bool(row.get("authorized", False)),
        )

    def _is_duplicate_error(self, exc: Exception, provider_message_id: str) -> bool:
        """Best-effort duplicate detection across backends.

        SQLite raises ``sqlite3.IntegrityError`` with ``UNIQUE constraint
        failed: conversation_messages.provider_message_id`` in the
        message. Postgres/PostgREST surfaces it as a structured error
        with code ``23505``. We sniff the message first (cheap) and
        fall back to a SELECT existence check (durable).
        """
        msg = str(exc).lower()
        if "unique" in msg and "provider_message_id" in msg:
            return True
        if "23505" in msg or "duplicate key" in msg:
            return True
        try:
            existing = (
                self._admin
                .schema(_SCHEMA)
                .table(_TABLE)
                .select("id")
                .eq("provider_message_id", provider_message_id)
                .limit(1)
                .execute()
            )
            return bool(existing.data)
        except Exception:
            return False

    def list_for_session(self, *, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent messages for a session, oldest first. Used by
        the chatbot's history-load when Redis memory is cold (e.g. after
        a Redis restart) — falls back to the durable audit log."""
        response = (
            self._admin
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return list(response.data or [])


__all__ = ["DuplicateMessage", "MessageStore", "StoredMessage"]
