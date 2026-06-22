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

Per-connection chat queries (014_whatsapp_chat_per_connection.sql):
  - ``list_chats(connection_id)`` — grouped inbox summary, last_message_at
    DESC.
  - ``list_messages(connection_id, raw_sender, limit, before)`` — thread
    for one chat, oldest-first with optional cursor.

Historical rows (pre-2026-06-22) have ``connection_id = NULL`` and do not
surface in the per-connection inbox — documented in the migration comment.
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
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
    connection_id: UUID | None = None


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
        connection_id: UUID | None = None,
    ) -> StoredMessage:
        """Insert a row.

        Raises:
            DuplicateMessage: if ``provider_message_id`` already exists in
                the table. Webhook handlers catch this to drop duplicate
                WAHA deliveries (message + message.any for the same id).

        ``connection_id`` tags the message with the WhatsApp connection it
        arrived on. NULL for pre-014 messages or when the webhook fires
        via the legacy global route (no connection context).
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
            "connection_id": str(connection_id) if connection_id else None,
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
        raw_cid = row.get("connection_id")
        return StoredMessage(
            id=UUID(row["id"]),
            session_id=row["session_id"],
            direction=row["direction"],
            body=row["body"],
            provider_message_id=row.get("provider_message_id"),
            authorized=bool(row.get("authorized", False)),
            connection_id=UUID(str(raw_cid)) if raw_cid else None,
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

    # ── Per-connection chat inbox queries (014_whatsapp_chat_per_connection) ──

    def list_chats(self, *, connection_id: UUID) -> list[dict[str, Any]]:
        """Return chat-inbox summaries for one connection, ordered by
        last_message_at DESC.

        Each row groups all messages from the same ``raw_sender`` within
        this connection.  The summary shape mirrors the contract:

            {
                chat_id:          str          (= raw_sender JID)
                contact:          str          (display name best-effort)
                last_message:     str
                last_message_at:  str          (ISO 8601 UTC)
                last_direction:   "inbound"|"outbound"
                unread:           int          (inbound after last outbound)
            }

        Fetches the raw rows and aggregates in Python — keeps the query
        simple (no window functions required) for the modest message
        counts expected per connection per operator.

        ``contact`` is the phone digits extracted from the JID (e.g.
        ``55119...`` from ``55119...@c.us``) until a WAHA pushname
        surface is added.  Never null — falls back to the raw JID.
        """
        response = (
            self._admin
            .schema(_SCHEMA)
            .table(_TABLE)
            .select(
                "id, raw_sender, direction, body, created_at, "
                "provider_message_id, structured_payload"
            )
            .eq("connection_id", str(connection_id))
            .eq("org_id", str(self._org_id))
            .order("created_at", desc=False)
            .execute()
        )
        rows = list(response.data or [])

        # Group by raw_sender, building summary per contact.
        # We iterate once: the last row per sender is always up-to-date
        # because we ordered ASC (latest = last encountered).
        by_sender: dict[str, dict[str, Any]] = {}
        # Track last outbound per sender to compute unread count.
        last_outbound_at: dict[str, str | None] = {}

        for row in rows:
            sender = row.get("raw_sender") or ""
            if not sender:
                continue
            direction = row.get("direction", "inbound")
            created_at = row.get("created_at") or ""

            if sender not in by_sender:
                by_sender[sender] = {}
                last_outbound_at[sender] = None

            by_sender[sender] = {
                "last_message": row.get("body") or "",
                "last_message_at": created_at,
                "last_direction": direction,
            }
            if direction == "outbound":
                last_outbound_at[sender] = created_at

        # Compute unread: count inbound messages newer than last outbound.
        unread_counts: dict[str, int] = {s: 0 for s in by_sender}
        for row in rows:
            sender = row.get("raw_sender") or ""
            if not sender or sender not in by_sender:
                continue
            if row.get("direction") != "inbound":
                continue
            last_out = last_outbound_at.get(sender)
            if last_out is None or row.get("created_at", "") > last_out:
                unread_counts[sender] = unread_counts.get(sender, 0) + 1

        summaries = []
        for sender, data in by_sender.items():
            # Best-effort display name: strip JID suffix to get phone digits.
            contact = (
                sender
                .replace("@c.us", "")
                .replace("@s.whatsapp.net", "")
                .replace("@lid", "")
            ) or sender
            summaries.append({
                "chat_id": sender,
                "contact": contact,
                "last_message": data["last_message"],
                "last_message_at": data["last_message_at"],
                "last_direction": data["last_direction"],
                "unread": unread_counts.get(sender, 0),
            })

        # Sort by last_message_at DESC (ISO strings compare correctly).
        summaries.sort(key=lambda s: s["last_message_at"], reverse=True)
        return summaries

    def list_messages(
        self,
        *,
        connection_id: UUID,
        raw_sender: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return messages for one chat thread, oldest-first.

        Filters by ``connection_id`` + ``raw_sender`` + ``org_id``.
        ``before`` is an ISO timestamp cursor — when set, only messages
        with ``created_at < before`` are returned (page-backwards).
        Returned rows carry: id, chat_id (= raw_sender), direction, body,
        created_at, provider_message_id, structured_payload.
        """
        q = (
            self._admin
            .schema(_SCHEMA)
            .table(_TABLE)
            .select(
                "id, raw_sender, direction, body, created_at, "
                "provider_message_id, structured_payload"
            )
            .eq("connection_id", str(connection_id))
            .eq("raw_sender", raw_sender)
            .eq("org_id", str(self._org_id))
        )
        if before:
            q = q.lt("created_at", before)

        response = (
            q
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        rows = list(response.data or [])

        # Normalize to the contract shape.
        result = []
        for row in rows:
            sp = row.get("structured_payload")
            if isinstance(sp, str):
                try:
                    sp = json.loads(sp)
                except Exception:
                    sp = None
            result.append({
                "id": row.get("id"),
                "chat_id": row.get("raw_sender"),
                "direction": row.get("direction"),
                "body": row.get("body") or "",
                "created_at": row.get("created_at"),
                "provider_message_id": row.get("provider_message_id"),
                "structured_payload": sp,
            })
        return result


__all__ = ["DuplicateMessage", "MessageStore", "StoredMessage"]
