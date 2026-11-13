"""Vendor JSON -> domain types (the anti-corruption seam). Nothing outside this module reads raw Bot API JSON."""
from __future__ import annotations

from typing import Any

from .types import BotInfo, ChatInfo, ChatMember, SentMessage, WebhookInfo


def to_bot(raw: dict[str, Any]) -> BotInfo:
    return BotInfo(id=int(raw["id"]), username=raw.get("username") or "", first_name=raw.get("first_name") or "",
                   is_bot=bool(raw.get("is_bot", True)))


def to_chat(raw: dict[str, Any]) -> ChatInfo:
    return ChatInfo(id=int(raw["id"]), type=raw.get("type") or "", title=raw.get("title") or "",
                    username=raw.get("username"))


def to_member(raw: dict[str, Any]) -> ChatMember:
    user = raw.get("user") or {}
    creator = raw.get("status") == "creator"
    return ChatMember(
        status=raw.get("status") or "", user_id=int(user.get("id") or 0),
        can_post_messages=bool(raw.get("can_post_messages", creator)),
        can_edit_messages=bool(raw.get("can_edit_messages", creator)),
        can_delete_messages=bool(raw.get("can_delete_messages", creator)),
    )


def to_sent(raw: dict[str, Any]) -> SentMessage:
    return SentMessage(message_id=int(raw["message_id"]), chat_id=int((raw.get("chat") or {}).get("id") or 0),
                       date=int(raw.get("date") or 0))


def to_webhook_info(raw: dict[str, Any]) -> WebhookInfo:
    return WebhookInfo(url=raw.get("url") or "", pending_update_count=int(raw.get("pending_update_count") or 0),
                       last_error_message=raw.get("last_error_message"),
                       allowed_updates=tuple(raw.get("allowed_updates") or ()))
