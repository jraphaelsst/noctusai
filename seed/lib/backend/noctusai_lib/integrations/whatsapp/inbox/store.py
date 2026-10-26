"""Chat/message persistence for the WhatsApp inbox: Protocol + Fake + Real +
fake-or-refuse factory.

``WhatsAppChatStore`` is the ONLY thing the ingest path, the backfill and the
router touch; the Real implementation is a Supabase client over the two tables
of :mod:`.ddl`, the Fake keeps the same row dicts in memory (full semantic
parity: dedup, keyset ordering, derived unread, atomic notification claim).

Invariants every implementation honours (tests run the same contract against
both):

* every read/write is scoped by ``org_id`` — the service-role client bypasses
  RLS, so this filter is the real enforcement;
* ``insert_message`` returns ``False`` for a duplicate ``(connection_id,
  waha_message_id)`` — that unique key, not any cache, is the dedup guard;
* ``unread_count`` is RECOMPUTED (inbound messages newer than the read
  cursor), never incremented;
* ``claim_new_chat_notification`` is atomic (conditional UPDATE): at most one
  caller ever wins per chat until it is explicitly released.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, runtime_checkable
from uuid import UUID

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from noctusai_lib.integrations.whatsapp.inbox.ddl import CHATS_TABLE, MESSAGES_TABLE
from noctusai_lib.integrations.whatsapp.inbox.types import (
    ORIGIN_BACKFILL,
    ORIGIN_INBOUND,
    ChatState,
    InboxChat,
    InboxMessage,
    display_name,
)

DEFAULT_PAGE = 30
MAX_PAGE = 200


class InboxStoreNotConfigured(RuntimeError, IntegrationNotConfigured):
    """No database client was supplied and the Fake was not opted into."""


# ─── shared helpers (Real + Fake) ───────────────────────────────────────────


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def to_iso(value: Any) -> Optional[str]:
    parsed = parse_ts(value)
    return parsed.astimezone(timezone.utc).isoformat() if parsed else None


def encode_cursor(ts: Optional[str], tiebreak: str) -> Optional[str]:
    return f"{ts}|{tiebreak}" if ts else None


def decode_cursor(cursor: Optional[str]) -> Optional[tuple[str, Optional[str]]]:
    """``"<iso>|<tiebreak>"`` or a bare ISO timestamp -> ``(iso, tiebreak|None)``.
    A malformed cursor raises ``ValueError`` (the router maps it to 422)."""
    if not cursor:
        return None
    ts_part, _, tie = cursor.partition("|")
    if parse_ts(ts_part) is None:
        raise ValueError("invalid cursor")
    return ts_part, (tie or None)


def _clamp(limit: int) -> int:
    return max(1, min(int(limit), MAX_PAGE))


def _search_text(chat_id: str, name: Optional[str], phone: Optional[str]) -> str:
    digits = (phone or "").lstrip("+")
    return " ".join(p for p in ((name or "").strip().lower(), digits, chat_id.lower()) if p)


def chat_from_row(row: dict[str, Any]) -> InboxChat:
    chat_id = row.get("chat_id") or ""
    phone = row.get("phone")
    return InboxChat(
        chat_id=chat_id,
        name=display_name(chat_id, row.get("name"), phone),
        phone=phone,
        is_group=bool(row.get("is_group")),
        last_message_preview=row.get("last_message_preview") or "",
        last_message_at=to_iso(row.get("last_message_at")),
        last_message_from_me=row.get("last_message_from_me"),
        unread_count=int(row.get("unread_count") or 0),
    )


def message_from_row(row: dict[str, Any]) -> InboxMessage:
    ack = row.get("ack")
    return InboxMessage(
        id=row.get("waha_message_id") or "",
        chat_id=row.get("chat_id") or "",
        from_me=bool(row.get("from_me")),
        body=row.get("body") or "",
        type=row.get("type") or "chat",
        media_url=row.get("media_url"),
        ack=int(ack) if ack is not None else None,
        timestamp=to_iso(row.get("timestamp")) or "",
        sender_name=row.get("sender_name"),
        media_mimetype=row.get("media_mimetype"),
        sender_phone=row.get("sender_phone"),
    )


def message_row(org_id: UUID, connection_id: UUID, message: InboxMessage) -> dict[str, Any]:
    return {
        "org_id": str(org_id),
        "connection_id": str(connection_id),
        "chat_id": message.chat_id,
        "waha_message_id": message.id,
        "from_me": message.from_me,
        "body": message.body,
        "type": message.type,
        "media_url": message.media_url,
        "media_mimetype": message.media_mimetype,
        "ack": message.ack,
        "sender_name": message.sender_name,
        "sender_phone": message.sender_phone,
        "timestamp": message.timestamp,
    }


def _pending(row: dict[str, Any]) -> bool:
    return (
        (row.get("origin") or ORIGIN_INBOUND) == ORIGIN_INBOUND
        and not row.get("is_group")
        and row.get("new_chat_notified_at") is None
    )


def _ack_advances(current: Optional[int], new: int) -> bool:
    """Acks only move forward (WAHA can deliver them out of order); an error
    ack (-1) lands only while the message has not reached the device yet."""
    if current is None:
        return True
    if new < 0:
        return current < 2
    return new > current


@runtime_checkable
class WhatsAppChatStore(Protocol):
    def ensure_chat(
        self, *, org_id: UUID, connection_id: UUID, chat_id: str, name: Optional[str],
        phone: Optional[str], is_group: bool, origin: str,
    ) -> ChatState: ...

    def insert_message(self, *, org_id: UUID, connection_id: UUID, message: InboxMessage) -> bool: ...

    def refresh_chat_after_message(
        self, *, org_id: UUID, connection_id: UUID, chat_id: str, message: InboxMessage,
        name: Optional[str] = None, phone: Optional[str] = None,
    ) -> InboxChat: ...

    def apply_ack(
        self, *, org_id: UUID, connection_id: UUID, waha_message_id: str, ack: int
    ) -> Optional[InboxMessage]: ...

    def get_chat(self, *, org_id: UUID, connection_id: UUID, chat_id: str) -> Optional[InboxChat]: ...

    def list_chats(
        self, *, org_id: UUID, connection_id: UUID, q: Optional[str] = None,
        limit: int = DEFAULT_PAGE, cursor: Optional[str] = None,
    ) -> tuple[list[InboxChat], Optional[str]]: ...

    def list_messages(
        self, *, org_id: UUID, connection_id: UUID, chat_id: str,
        before: Optional[str] = None, limit: int = 50,
    ) -> tuple[list[InboxMessage], bool]: ...

    def mark_read(self, *, org_id: UUID, connection_id: UUID, chat_id: str) -> Optional[InboxChat]: ...

    def claim_new_chat_notification(self, *, org_id: UUID, connection_id: UUID, chat_id: str) -> bool: ...

    def release_new_chat_notification(self, *, org_id: UUID, connection_id: UUID, chat_id: str) -> None: ...

    def get_synced_through(self, *, org_id: UUID, connection_id: UUID, chat_id: str) -> Optional[str]: ...

    def set_synced_through(
        self, *, org_id: UUID, connection_id: UUID, chat_id: str, synced_through: str
    ) -> None: ...

    def list_connection_chat_ids(self, *, org_id: UUID, connection_id: UUID) -> list[str]: ...

    def delete_connection_chats(self, *, org_id: UUID, connection_id: UUID) -> tuple[int, int]:
        """Testing-phase purge: delete ALL of the connection's chats (messages go with them).
        Returns ``(chats_deleted, messages_deleted)``."""
        ...


# ─── Fake ───────────────────────────────────────────────────────────────────


class FakeWhatsAppChatStore:
    """In-memory store with the same semantics as the Real one. Thread-safe
    (the claim/insert atomicity is part of what tests exercise)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.chats: dict[tuple[str, str], dict[str, Any]] = {}
        self.messages: dict[tuple[str, str], dict[str, Any]] = {}

    # keys are (connection_id, chat_id) / (connection_id, waha_message_id)
    def _chat(self, org_id: UUID, connection_id: UUID, chat_id: str) -> Optional[dict[str, Any]]:
        row = self.chats.get((str(connection_id), chat_id))
        return row if row is not None and row["org_id"] == str(org_id) else None

    def _recount(self, row: dict[str, Any]) -> int:
        cursor = parse_ts(row.get("last_read_at"))
        count = 0
        for msg in self.messages.values():
            if msg["connection_id"] != row["connection_id"] or msg["chat_id"] != row["chat_id"]:
                continue
            if msg["from_me"]:
                continue
            if cursor is None or parse_ts(msg["timestamp"]) > cursor:
                count += 1
        return count

    def ensure_chat(self, *, org_id, connection_id, chat_id, name, phone, is_group, origin) -> ChatState:
        with self._lock:
            existing = self._chat(org_id, connection_id, chat_id)
            if existing is not None:
                return ChatState(chat_from_row(existing), existing["origin"], False, _pending(existing))
            now = utc_now_iso()
            row = {
                "connection_id": str(connection_id), "chat_id": chat_id, "org_id": str(org_id),
                "name": name, "phone": phone, "is_group": is_group, "origin": origin,
                "new_chat_notified_at": None, "last_message_at": None, "last_message_preview": "",
                "last_message_from_me": None, "unread_count": 0,
                "last_read_at": now if origin == ORIGIN_BACKFILL else None,
                "synced_through": None, "created_at": now, "updated_at": now,
                "search_text": _search_text(chat_id, name, phone),
            }
            self.chats[(str(connection_id), chat_id)] = row
            return ChatState(chat_from_row(row), origin, True, _pending(row))

    def insert_message(self, *, org_id, connection_id, message) -> bool:
        with self._lock:
            key = (str(connection_id), message.id)
            if key in self.messages:
                return False
            row = message_row(org_id, connection_id, message)
            row["acked_at"] = None
            self.messages[key] = row
            return True

    def refresh_chat_after_message(self, *, org_id, connection_id, chat_id, message, name=None, phone=None):
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            if row is None:
                raise KeyError(f"unknown chat {chat_id!r} (ensure_chat first)")
            current = parse_ts(row["last_message_at"])
            if current is None or parse_ts(message.timestamp) >= current:
                row["last_message_at"] = message.timestamp
                row["last_message_preview"] = _preview_for(message)
                row["last_message_from_me"] = message.from_me
            if name and not (row.get("name") or "").strip():
                row["name"] = name
            if phone and not row.get("phone"):
                row["phone"] = phone
            row["search_text"] = _search_text(chat_id, row.get("name"), row.get("phone"))
            row["unread_count"] = self._recount(row)
            row["updated_at"] = utc_now_iso()
            return chat_from_row(row)

    def apply_ack(self, *, org_id, connection_id, waha_message_id, ack):
        with self._lock:
            row = self.messages.get((str(connection_id), waha_message_id))
            if row is None or row["org_id"] != str(org_id):
                return None
            if _ack_advances(row.get("ack"), ack):
                row["ack"] = ack
                row["acked_at"] = utc_now_iso()
            return message_from_row(row)

    def get_chat(self, *, org_id, connection_id, chat_id):
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            return chat_from_row(row) if row else None

    def list_chats(self, *, org_id, connection_id, q=None, limit=DEFAULT_PAGE, cursor=None):
        limit = _clamp(limit)
        decoded = decode_cursor(cursor)
        with self._lock:
            rows = [
                r for r in self.chats.values()
                if r["org_id"] == str(org_id) and r["connection_id"] == str(connection_id)
                and r["last_message_at"] is not None
            ]
        if q and q.strip():
            needle = q.strip().lower()
            rows = [r for r in rows if needle in (r.get("search_text") or "")]
        rows.sort(key=lambda r: (parse_ts(r["last_message_at"]), r["chat_id"]), reverse=True)
        if decoded:
            ts, tie = decoded
            bound = parse_ts(ts)
            rows = [
                r for r in rows
                if parse_ts(r["last_message_at"]) < bound
                or (tie is not None and parse_ts(r["last_message_at"]) == bound and r["chat_id"] < tie)
            ]
        page = rows[: limit + 1]
        items = [chat_from_row(r) for r in page[:limit]]
        nxt = encode_cursor(items[-1].last_message_at, items[-1].chat_id) if len(page) > limit else None
        return items, nxt

    def list_messages(self, *, org_id, connection_id, chat_id, before=None, limit=50):
        limit = _clamp(limit)
        decoded = decode_cursor(before)
        with self._lock:
            rows = [
                r for r in self.messages.values()
                if r["org_id"] == str(org_id) and r["connection_id"] == str(connection_id)
                and r["chat_id"] == chat_id
            ]
        rows.sort(key=lambda r: (parse_ts(r["timestamp"]), r["waha_message_id"]), reverse=True)
        if decoded:
            ts, tie = decoded
            bound = parse_ts(ts)
            rows = [
                r for r in rows
                if parse_ts(r["timestamp"]) < bound
                or (tie is not None and parse_ts(r["timestamp"]) == bound and r["waha_message_id"] < tie)
            ]
        page = rows[: limit + 1]
        has_more = len(page) > limit
        return [message_from_row(r) for r in reversed(page[:limit])], has_more

    def mark_read(self, *, org_id, connection_id, chat_id):
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            if row is None:
                return None
            row["last_read_at"] = utc_now_iso()
            row["unread_count"] = 0
            return chat_from_row(row)

    def claim_new_chat_notification(self, *, org_id, connection_id, chat_id) -> bool:
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            if (row is None or row["origin"] != ORIGIN_INBOUND or row["is_group"]
                    or row["new_chat_notified_at"] is not None):
                return False
            row["new_chat_notified_at"] = utc_now_iso()
            return True

    def release_new_chat_notification(self, *, org_id, connection_id, chat_id) -> None:
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            if row is not None:
                row["new_chat_notified_at"] = None

    def get_synced_through(self, *, org_id, connection_id, chat_id):
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            return to_iso(row["synced_through"]) if row else None

    def set_synced_through(self, *, org_id, connection_id, chat_id, synced_through) -> None:
        with self._lock:
            row = self._chat(org_id, connection_id, chat_id)
            if row is not None:
                row["synced_through"] = synced_through

    def delete_connection_chats(self, *, org_id, connection_id):
        with self._lock:
            cid, oid = str(connection_id), str(org_id)
            chat_keys = [k for k, r in self.chats.items() if k[0] == cid and r["org_id"] == oid]
            msg_keys = [k for k, r in self.messages.items() if k[0] == cid and r["org_id"] == oid]
            for k in chat_keys:
                del self.chats[k]
            for k in msg_keys:
                del self.messages[k]
            return len(chat_keys), len(msg_keys)

    def list_connection_chat_ids(self, *, org_id, connection_id):
        with self._lock:
            return [
                r["chat_id"] for r in self.chats.values()
                if r["org_id"] == str(org_id) and r["connection_id"] == str(connection_id)
            ]


def _preview_for(message: InboxMessage) -> str:
    from noctusai_lib.integrations.whatsapp.inbox.types import preview_of

    return preview_of(message.body, has_media=bool(message.media_url or message.type != "chat"))


# ─── Real (Supabase) ────────────────────────────────────────────────────────


class SupabaseWhatsAppChatStore:
    """Real store over ``<schema>.whatsapp_chats`` / ``whatsapp_messages``,
    backed by an admin/service-role Supabase client (the webhook has no JWT)."""

    def __init__(
        self, client: Any, *, schema: str, chats_table: str = CHATS_TABLE,
        messages_table: str = MESSAGES_TABLE,
    ) -> None:
        # Bound once: ``client.schema(...)`` is a cheap, reusable PostgREST
        # handle (and keeps a schema-scoped test double's state coherent).
        self._db = client.schema(schema)
        self._chats_name = chats_table
        self._messages_name = messages_table

    def _chats(self):
        return self._db.table(self._chats_name)

    def _messages(self):
        return self._db.table(self._messages_name)

    def _chat_scope(self, query, org_id: UUID, connection_id: UUID, chat_id: str):
        return (query.eq("org_id", str(org_id)).eq("connection_id", str(connection_id))
                .eq("chat_id", chat_id))

    def _chat_row(self, org_id: UUID, connection_id: UUID, chat_id: str) -> Optional[dict[str, Any]]:
        rows = self._chat_scope(self._chats().select("*"), org_id, connection_id, chat_id).limit(1).execute().data
        return dict(rows[0]) if rows else None

    def _keyset(
        self, make_query: Callable[[], Any], ts_col: str, tie_col: str,
        decoded: Optional[tuple[str, Optional[str]]], limit: int,
    ) -> list[dict[str, Any]]:
        """Newest-first page of ``limit`` rows strictly after the cursor in
        ``(ts_col, tie_col)`` DESC order. Two plain queries instead of one
        ``or(...)`` so the shape stays inside the portable filter subset."""
        def run(extra: Callable[[Any], Any]) -> list[dict[str, Any]]:
            q = extra(make_query())
            return list(q.order(ts_col, desc=True).order(tie_col, desc=True).limit(limit).execute().data or [])

        if decoded is None:
            return run(lambda q: q)
        ts, tie = decoded
        rows: list[dict[str, Any]] = []
        if tie is not None:
            rows.extend(run(lambda q: q.eq(ts_col, ts).lt(tie_col, tie)))
        rows.extend(run(lambda q: q.lt(ts_col, ts)))
        return rows[:limit]

    def ensure_chat(self, *, org_id, connection_id, chat_id, name, phone, is_group, origin) -> ChatState:
        row = {
            "connection_id": str(connection_id), "chat_id": chat_id, "org_id": str(org_id),
            "name": name, "phone": phone, "is_group": is_group, "origin": origin,
            "search_text": _search_text(chat_id, name, phone),
        }
        if origin == ORIGIN_BACKFILL:
            row["last_read_at"] = utc_now_iso()  # history is not "unread"
        inserted = self._chats().upsert(
            row, on_conflict="connection_id,chat_id", ignore_duplicates=True
        ).execute().data
        stored = self._chat_row(org_id, connection_id, chat_id)
        if stored is None:  # pragma: no cover - the upsert just wrote/ignored it
            raise RuntimeError(f"whatsapp chat {chat_id!r} missing right after ensure_chat")
        return ChatState(
            chat_from_row(stored), stored.get("origin") or origin, bool(inserted), _pending(stored)
        )

    def insert_message(self, *, org_id, connection_id, message) -> bool:
        resp = self._messages().upsert(
            message_row(org_id, connection_id, message),
            on_conflict="connection_id,waha_message_id", ignore_duplicates=True,
        ).execute()
        return bool(resp.data)

    def refresh_chat_after_message(self, *, org_id, connection_id, chat_id, message, name=None, phone=None):
        row = self._chat_row(org_id, connection_id, chat_id)
        if row is None:
            raise KeyError(f"unknown chat {chat_id!r} (ensure_chat first)")
        patch: dict[str, Any] = {"updated_at": utc_now_iso()}
        current = parse_ts(row.get("last_message_at"))
        if current is None or parse_ts(message.timestamp) >= current:
            patch.update(
                last_message_at=message.timestamp,
                last_message_preview=_preview_for(message),
                last_message_from_me=message.from_me,
            )
        new_name = row.get("name") or None
        if name and not (row.get("name") or "").strip():
            patch["name"] = new_name = name
        new_phone = row.get("phone")
        if phone and not new_phone:
            patch["phone"] = new_phone = phone
        patch["search_text"] = _search_text(chat_id, new_name, new_phone)
        patch["unread_count"] = self._count_unread(org_id, connection_id, chat_id, row.get("last_read_at"))
        self._chat_scope(self._chats().update(patch), org_id, connection_id, chat_id).execute()
        fresh = self._chat_row(org_id, connection_id, chat_id)
        return chat_from_row(fresh or {**row, **patch})

    def _count_unread(self, org_id: UUID, connection_id: UUID, chat_id: str, last_read_at: Any) -> int:
        query = self._chat_scope(
            self._messages().select("id", count="exact"), org_id, connection_id, chat_id
        ).eq("from_me", False)
        if last_read_at:
            query = query.gt("timestamp", to_iso(last_read_at))
        resp = query.execute()
        count = getattr(resp, "count", None)
        return int(count if count is not None else len(resp.data or []))

    def apply_ack(self, *, org_id, connection_id, waha_message_id, ack):
        rows = (self._messages().select("*").eq("org_id", str(org_id))
                .eq("connection_id", str(connection_id)).eq("waha_message_id", waha_message_id)
                .limit(1).execute().data)
        if not rows:
            return None
        row = dict(rows[0])
        if _ack_advances(row.get("ack"), ack):
            patch = {"ack": ack, "acked_at": utc_now_iso()}
            (self._messages().update(patch).eq("org_id", str(org_id))
             .eq("connection_id", str(connection_id)).eq("waha_message_id", waha_message_id).execute())
            row.update(patch)
        return message_from_row(row)

    def get_chat(self, *, org_id, connection_id, chat_id):
        row = self._chat_row(org_id, connection_id, chat_id)
        return chat_from_row(row) if row else None

    def list_chats(self, *, org_id, connection_id, q=None, limit=DEFAULT_PAGE, cursor=None):
        limit = _clamp(limit)
        needle = _escape_like(q.strip().lower()) if q and q.strip() else None

        def base():
            query = (self._chats().select("*").eq("org_id", str(org_id))
                     .eq("connection_id", str(connection_id)).not_.is_("last_message_at", "null"))
            return query.ilike("search_text", f"%{needle}%") if needle else query

        rows = self._keyset(base, "last_message_at", "chat_id", decode_cursor(cursor), limit + 1)
        items = [chat_from_row(r) for r in rows[:limit]]
        nxt = encode_cursor(items[-1].last_message_at, items[-1].chat_id) if len(rows) > limit else None
        return items, nxt

    def list_messages(self, *, org_id, connection_id, chat_id, before=None, limit=50):
        limit = _clamp(limit)

        def base():
            return self._chat_scope(self._messages().select("*"), org_id, connection_id, chat_id)

        rows = self._keyset(base, "timestamp", "waha_message_id", decode_cursor(before), limit + 1)
        return [message_from_row(r) for r in reversed(rows[:limit])], len(rows) > limit

    def mark_read(self, *, org_id, connection_id, chat_id):
        if self._chat_row(org_id, connection_id, chat_id) is None:
            return None
        self._chat_scope(
            self._chats().update({"last_read_at": utc_now_iso(), "unread_count": 0}),
            org_id, connection_id, chat_id,
        ).execute()
        return self.get_chat(org_id=org_id, connection_id=connection_id, chat_id=chat_id)

    def claim_new_chat_notification(self, *, org_id, connection_id, chat_id) -> bool:
        resp = self._chat_scope(
            self._chats().update({"new_chat_notified_at": utc_now_iso()}),
            org_id, connection_id, chat_id,
        ).eq("origin", ORIGIN_INBOUND).eq("is_group", False).is_("new_chat_notified_at", "null").execute()
        return bool(resp.data)

    def release_new_chat_notification(self, *, org_id, connection_id, chat_id) -> None:
        self._chat_scope(
            self._chats().update({"new_chat_notified_at": None}), org_id, connection_id, chat_id
        ).execute()

    def get_synced_through(self, *, org_id, connection_id, chat_id):
        row = self._chat_row(org_id, connection_id, chat_id)
        return to_iso(row.get("synced_through")) if row else None

    def set_synced_through(self, *, org_id, connection_id, chat_id, synced_through) -> None:
        self._chat_scope(
            self._chats().update({"synced_through": synced_through}), org_id, connection_id, chat_id
        ).execute()

    def list_connection_chat_ids(self, *, org_id, connection_id):
        rows = (self._chats().select("chat_id").eq("org_id", str(org_id))
                .eq("connection_id", str(connection_id)).execute().data or [])
        return [r["chat_id"] for r in rows]

    def delete_connection_chats(self, *, org_id, connection_id):
        # messages first, explicitly: correctness must not depend on a product's FK cascade being declared
        def scoped(query):
            return query.eq("org_id", str(org_id)).eq("connection_id", str(connection_id))

        messages = scoped(self._messages().delete()).execute()
        chats = scoped(self._chats().delete()).execute()
        return len(chats.data or []), len(messages.data or [])


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ─── factory (fake-or-refuse) ───────────────────────────────────────────────


def build_whatsapp_chat_store(
    client: Any = None,
    *,
    schema: str,
    allow_fake: bool = False,
    chats_table: str = CHATS_TABLE,
    messages_table: str = MESSAGES_TABLE,
) -> WhatsAppChatStore:
    """Real store when ``client`` is supplied; the Fake ONLY under an explicit
    ``allow_fake=True`` (tests / local dev); otherwise a loud
    :class:`InboxStoreNotConfigured` — a production process must never run the
    inbox on an in-memory store and look healthy (NOC-REMEDIATE[fake-or-refuse-seed]
    is satisfied by construction)."""
    def _refuse() -> WhatsAppChatStore:
        raise InboxStoreNotConfigured(
            "WhatsApp inbox store has no database client; pass allow_fake=True only in tests/dev"
        )

    return resolve_fake_or_refuse(
        configured=client is not None,
        build_real=lambda: SupabaseWhatsAppChatStore(
            client, schema=schema, chats_table=chats_table, messages_table=messages_table
        ),
        build_fake=FakeWhatsAppChatStore,
        allow_fake=allow_fake,
        unconfigured=_refuse,
    )
