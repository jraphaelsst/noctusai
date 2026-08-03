"""Materialized per-conversation state for the WhatsApp inbox.

WHY THIS EXISTS
---------------
``MessageStore.list_chats`` derives the inbox by SELECTing **every** message
row for a connection and grouping them in Python (``message_store.py:183``).
That is O(all messages) per page-load and gets slower every day the product is
used. It also cannot express read-state at all: its ``unread`` is the heuristic
"inbound messages newer than my last outbound", which is not what unread means
and which the WAHA-merge path discarded entirely (hardcoded ``0``).

This store replaces that with one row per conversation in
``social_wiring.whatsapp_chats`` (migration 040), so the chat list is a single
indexed read over ``(connection_id, archived, last_message_at DESC)`` — the
index exists precisely for this query — and read-state is a real cursor.

WRITE PATH vs READ PATH
-----------------------
- Ingest (webhook / backfill) calls :meth:`record_message` on every persisted
  message. That keeps ``last_message_*`` current and recounts unread.
- The read endpoints call :meth:`list_chats` / :meth:`get_chat`, which touch
  **only** this table — WAHA is never on the read path.
- :meth:`mark_read` advances the cursor and zeroes the counter.

UNREAD IS RECOUNTED, NOT INCREMENTED
------------------------------------
``record_message`` recomputes unread with a single indexed COUNT scoped to one
chat rather than doing read-modify-write on a counter. An increment would race
whenever WAHA delivers two messages for the same chat concurrently (it does —
``message`` and ``message.any`` fire for the same send), and the lost update
would be silent and permanent. A scoped COUNT over
``(connection_id, chat_id, created_at DESC)`` is cheap, and it is *derived*, so
it self-heals: a dropped webhook cannot leave the badge permanently wrong.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_CHATS = "whatsapp_chats"
_MESSAGES = "conversation_messages"

#: Preview text is truncated at write time so the list endpoint never has to
#: ship (or trim) a full message body per row.
_PREVIEW_MAX = 140


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(body: str | None, *, has_media: bool = False) -> str:
    text = (body or "").strip()
    if not text:
        return "[mídia]" if has_media else ""
    if len(text) <= _PREVIEW_MAX:
        return text
    return text[: _PREVIEW_MAX - 1].rstrip() + "…"


@dataclass(frozen=True)
class ChatSummary:
    """One conversation, as the inbox renders it.

    Field names are the wire contract — they match ``ChatDTO`` in the
    initiative's contract appendix exactly. Renaming here is a contract bump.
    """

    chat_id: str
    title: str
    last_message_at: str | None
    last_message_preview: str
    last_direction: str | None
    unread_count: int
    last_read_at: str | None
    archived: bool
    pinned: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ChatSummary:
        chat_id = row.get("chat_id") or ""
        return cls(
            chat_id=chat_id,
            # Never null: fall back to the phone digits, then the raw JID, so
            # the UI never has to render a blank thread header.
            title=row.get("title") or _display_from_jid(chat_id),
            last_message_at=row.get("last_message_at"),
            last_message_preview=row.get("last_message_preview") or "",
            last_direction=row.get("last_direction"),
            unread_count=int(row.get("unread_count") or 0),
            last_read_at=row.get("last_read_at"),
            archived=bool(row.get("archived")),
            pinned=bool(row.get("pinned")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "title": self.title,
            "last_message_at": self.last_message_at,
            "last_message_preview": self.last_message_preview,
            "last_direction": self.last_direction,
            "unread_count": self.unread_count,
            "last_read_at": self.last_read_at,
            "archived": self.archived,
            "pinned": self.pinned,
        }


def _display_from_jid(jid: str) -> str:
    """``5511999999999@c.us`` → ``5511999999999``. Never returns empty for a
    non-empty JID — a blank contact label is worse than a raw one."""
    return (
        jid.replace("@c.us", "")
        .replace("@s.whatsapp.net", "")
        .replace("@lid", "")
        .replace("@g.us", "")
    ) or jid


class WhatsAppChatStore:
    """Per-request collaborator over ``social_wiring.whatsapp_chats``.

    Constructed from the **service-role** client: the webhook has no JWT
    context, and migration 040's RLS is authenticated-read / service-role-write
    exactly like every other table in this schema.
    """

    def __init__(self, *, admin_supabase, org_id: UUID):
        self._admin = admin_supabase
        self._org_id = org_id

    # ── read path (used by the chat endpoints) ─────────────────────────────

    def list_chats(
        self,
        *,
        connection_id: UUID,
        limit: int = 30,
        before: str | None = None,
        archived: bool | None = False,
    ) -> list[ChatSummary]:
        """Keyset-paginated inbox for one connection, newest first.

        ``before`` is the ``last_message_at`` of the last row the caller
        already has — keyset rather than OFFSET so paging stays O(limit) as
        history grows, and so a message arriving mid-scroll cannot shift the
        window and duplicate a row.

        ``archived=None`` returns both archived and active chats.
        """
        query = (
            self._admin.schema(_SCHEMA)
            .table(_CHATS)
            .select(
                "chat_id, title, last_message_at, last_message_preview, "
                "last_direction, unread_count, last_read_at, archived, pinned"
            )
            .eq("connection_id", str(connection_id))
            .eq("org_id", str(self._org_id))
        )
        if archived is not None:
            query = query.eq("archived", archived)
        if before:
            query = query.lt("last_message_at", before)

        response = (
            query.order("last_message_at", desc=True)
            .limit(max(1, min(limit, 200)))
            .execute()
        )
        return [ChatSummary.from_row(row) for row in (response.data or [])]

    def get_chat(self, *, connection_id: UUID, chat_id: str) -> ChatSummary | None:
        response = (
            self._admin.schema(_SCHEMA)
            .table(_CHATS)
            .select(
                "chat_id, title, last_message_at, last_message_preview, "
                "last_direction, unread_count, last_read_at, archived, pinned"
            )
            .eq("connection_id", str(connection_id))
            .eq("org_id", str(self._org_id))
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return ChatSummary.from_row(rows[0]) if rows else None

    # ── write path (used by ingest + backfill) ─────────────────────────────

    def record_message(
        self,
        *,
        connection_id: UUID,
        chat_id: str,
        direction: str,
        body: str | None,
        created_at: str,
        title: str | None = None,
        has_media: bool = False,
    ) -> ChatSummary:
        """Fold one persisted message into its conversation row.

        Idempotent by construction: every field written is derived from the
        message plus a recount, never from the row's previous value, so
        replaying the same webhook converges instead of drifting.

        ``last_message_*`` is only advanced when ``created_at`` is at least as
        new as what is stored — a backfill walking history backwards must not
        rewrite the header with an old message.
        """
        if not chat_id:
            raise ValueError("chat_id is required to record a chat message")

        existing = self.get_chat(connection_id=connection_id, chat_id=chat_id)
        is_newer = (
            existing is None
            or not existing.last_message_at
            or created_at >= existing.last_message_at
        )

        row: dict[str, Any] = {
            "connection_id": str(connection_id),
            "org_id": str(self._org_id),
            "chat_id": chat_id,
            "updated_at": _utc_now_iso(),
        }
        if is_newer:
            row["last_message_at"] = created_at
            row["last_message_preview"] = _preview(body, has_media=has_media)
            row["last_direction"] = direction
        # Only ever fill a title in; never overwrite a resolved contact name
        # with a worse one (a later webhook may carry no pushName at all).
        if title and (existing is None or not existing.title or existing.title == chat_id):
            row["title"] = title
        elif existing is None:
            row["title"] = _display_from_jid(chat_id)

        self._admin.schema(_SCHEMA).table(_CHATS).upsert(
            row, on_conflict="connection_id,chat_id"
        ).execute()

        # Recount rather than increment — see the module docstring.
        unread = self._recount_unread(
            connection_id=connection_id,
            chat_id=chat_id,
            last_read_at=(existing.last_read_at if existing else None),
        )
        self._admin.schema(_SCHEMA).table(_CHATS).update(
            {"unread_count": unread}
        ).eq("connection_id", str(connection_id)).eq("chat_id", chat_id).execute()

        refreshed = self.get_chat(connection_id=connection_id, chat_id=chat_id)
        if refreshed is None:  # pragma: no cover — upsert just wrote this row
            raise RuntimeError(
                f"whatsapp_chats row vanished immediately after upsert "
                f"(connection={connection_id}, chat={chat_id})"
            )
        return refreshed

    def mark_read(
        self,
        *,
        connection_id: UUID,
        chat_id: str,
        up_to_message_id: str | None = None,
        read_at: str | None = None,
    ) -> ChatSummary:
        """Advance the read cursor and zero the badge.

        Deliberately sets ``unread_count`` to 0 directly rather than
        recounting: the cursor moves to *now*, so a recount would return 0
        anyway, and doing it in one write keeps the endpoint fast enough to
        clear the badge optimistically.
        """
        stamp = read_at or _utc_now_iso()
        update: dict[str, Any] = {
            "last_read_at": stamp,
            "unread_count": 0,
            "updated_at": _utc_now_iso(),
        }
        if up_to_message_id:
            update["last_read_message_id"] = up_to_message_id

        self._admin.schema(_SCHEMA).table(_CHATS).update(update).eq(
            "connection_id", str(connection_id)
        ).eq("org_id", str(self._org_id)).eq("chat_id", chat_id).execute()

        refreshed = self.get_chat(connection_id=connection_id, chat_id=chat_id)
        if refreshed is None:
            raise ValueError(
                f"cannot mark unknown chat as read "
                f"(connection={connection_id}, chat={chat_id})"
            )
        return refreshed

    def set_synced_through(
        self, *, connection_id: UUID, chat_id: str, synced_through: str
    ) -> None:
        """Backfill watermark — how far back history has been pulled for this
        chat. The backfill job reads it to know where to resume, so a restart
        never re-walks history it already has."""
        self._admin.schema(_SCHEMA).table(_CHATS).update(
            {"synced_through": synced_through, "updated_at": _utc_now_iso()}
        ).eq("connection_id", str(connection_id)).eq("org_id", str(self._org_id)).eq(
            "chat_id", chat_id
        ).execute()

    def set_archived(
        self, *, connection_id: UUID, chat_id: str, archived: bool
    ) -> None:
        self._admin.schema(_SCHEMA).table(_CHATS).update(
            {"archived": archived, "updated_at": _utc_now_iso()}
        ).eq("connection_id", str(connection_id)).eq("org_id", str(self._org_id)).eq(
            "chat_id", chat_id
        ).execute()

    # ── internals ─────────────────────────────────────────────────────────

    def _recount_unread(
        self,
        *,
        connection_id: UUID,
        chat_id: str,
        last_read_at: str | None,
    ) -> int:
        """Count inbound messages newer than the read cursor.

        Rides ``idx_sw_conv_msgs_connection_chat_id (connection_id, chat_id,
        created_at DESC)`` from migration 040, so this is an index range scan
        over one conversation — not a table scan.
        """
        query = (
            self._admin.schema(_SCHEMA)
            .table(_MESSAGES)
            .select("id", count="exact")
            .eq("connection_id", str(connection_id))
            .eq("org_id", str(self._org_id))
            .eq("chat_id", chat_id)
            .eq("direction", "inbound")
        )
        if last_read_at:
            query = query.gt("created_at", last_read_at)

        response = query.execute()
        # Supabase returns the exact count out-of-band; fall back to the row
        # length only when the driver did not supply it. Never guess a number.
        count = getattr(response, "count", None)
        if count is None:
            count = len(response.data or [])
        return int(count)
