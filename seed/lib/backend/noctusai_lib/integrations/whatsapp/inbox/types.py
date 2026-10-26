"""Wire/domain types of the WhatsApp inbox organ.

``InboxChat`` / ``InboxMessage`` field names ARE the wire contract the
frontend organ (`@noctusai/lib` ``WhatsAppInbox``) reads — renaming one is a
contract bump on both sides in the same commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

#: How a chat row first came to exist. ONLY ``inbound`` chats are eligible for
#: ``on_new_chat`` — a chat the line's owner started from the phone, or one
#: imported from WAHA history, is not a "new contact reaching out".
ORIGIN_INBOUND = "inbound"
ORIGIN_OUTBOUND = "outbound"
ORIGIN_BACKFILL = "backfill"

#: WAHA ack levels: -1 error, 0 pending, 1 server, 2 device, 3 read, 4 played.
ACK_ERROR = -1


@dataclass(frozen=True)
class InboxChat:
    """One conversation as the inbox list renders it."""

    chat_id: str
    name: str
    phone: Optional[str]  # E.164 ("+5511...") or None (group / unresolved @lid)
    is_group: bool
    last_message_preview: str
    last_message_at: Optional[str]
    last_message_from_me: Optional[bool]
    unread_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "name": self.name,
            "phone": self.phone,
            "is_group": self.is_group,
            "last_message_preview": self.last_message_preview,
            "last_message_at": self.last_message_at,
            "last_message_from_me": self.last_message_from_me,
            "unread_count": self.unread_count,
        }


@dataclass(frozen=True)
class InboxMessage:
    """One message. ``id`` is the WAHA message id (the dedup key and the
    key ack updates address). ``media_mimetype`` / ``sender_phone`` are stored
    but are not part of the wire shape (``as_dict`` omits them)."""

    id: str
    chat_id: str
    from_me: bool
    body: str
    type: str
    media_url: Optional[str]
    ack: Optional[int]
    timestamp: str  # ISO-8601 UTC
    sender_name: Optional[str]
    media_mimetype: Optional[str] = None
    sender_phone: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "from_me": self.from_me,
            "body": self.body,
            "type": self.type,
            "media_url": self.media_url,
            "ack": self.ack,
            "timestamp": self.timestamp,
            "sender_name": self.sender_name,
        }


@dataclass(frozen=True)
class ChatState:
    """A chat row plus the bookkeeping the ingest path needs (not wire)."""

    chat: InboxChat
    origin: str
    created: bool  # True only for the call that inserted the row
    #: inbound + non-group + not yet claimed: an ``on_new_chat`` is still owed
    #: (a prior attempt failed and was released, or this call created the row).
    notification_pending: bool = False


def display_name(chat_id: str, name: Optional[str], phone: Optional[str]) -> str:
    """A chat is never rendered nameless: name, else phone, else the JID's
    local part."""
    if name and name.strip():
        return name.strip()
    if phone:
        return phone
    return chat_id.split("@", 1)[0] or chat_id


def e164(digits: Optional[str]) -> Optional[str]:
    """``5511999999999`` -> ``+5511999999999`` (None for empty/non-numeric)."""
    if not digits:
        return None
    cleaned = digits.lstrip("+").strip()
    return f"+{cleaned}" if cleaned.isdigit() else None


def preview_of(body: str, *, has_media: bool = False, limit: int = 140) -> str:
    text = (body or "").strip()
    if not text:
        return "[mídia]" if has_media else ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
