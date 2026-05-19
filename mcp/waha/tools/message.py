"""waha.message.* + waha.chat.* tools — messaging.

Reads (no gate): chat.list / message.list.
Write (confirm-gated, OUTWARD-FACING): message.send_text — the
strongest gate; a sent WhatsApp message cannot be unsent.

Routes through the single `api.request_json` HTTP seam (tests patch
`waha.api.request_json`).
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    ChatListInput,
    ChatListOutput,
    MessageListInput,
    MessageListOutput,
    SendTextInput,
    SendTextOutput,
    resolve_chat_id,
)

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    s = get_settings()
    return {
        "base_url": s.base_url or "",
        "api_key": s.api_key or "",
        "timeout": s.timeout_seconds,
    }


def _sess(name: Optional[str]) -> str:
    return name or get_settings().default_session


async def send_text(args: dict) -> dict:
    inp = SendTextInput(**args)
    if not inp.confirm:
        return SendTextOutput(
            error=typed_error(
                api.ConfirmationRequiredError("waha.message.send_text")
            )
        ).model_dump()
    chat_id = resolve_chat_id(inp.chat_id, inp.phone)
    body = {
        "session": _sess(inp.session),
        "chatId": chat_id,
        "text": inp.text,
    }
    try:
        data = api.request_json("POST", "/api/sendText", body=body, **_ctx())
    except api.WahaApiError as e:
        return SendTextOutput(error=typed_error(e)).model_dump()
    mid = None
    if isinstance(data, dict):
        mid = data.get("id") or (data.get("key") or {}).get("id")
    return SendTextOutput(
        sent=True, message_id=str(mid) if mid else None, result=data
    ).model_dump()


async def chat_list(args: dict) -> dict:
    inp = ChatListInput(**args)
    name = _sess(inp.session)
    try:
        data = api.request_json(
            "GET", f"/api/{name}/chats",
            params={"limit": inp.limit}, **_ctx(),
        )
    except api.WahaApiError as e:
        return ChatListOutput(error=typed_error(e)).model_dump()
    return ChatListOutput(
        chats=data if isinstance(data, list) else []
    ).model_dump()


async def message_list(args: dict) -> dict:
    inp = MessageListInput(**args)
    name = _sess(inp.session)
    chat_id = resolve_chat_id(inp.chat_id, inp.phone)
    try:
        data = api.request_json(
            "GET", f"/api/{name}/chats/{chat_id}/messages",
            params={"limit": inp.limit}, **_ctx(),
        )
    except api.WahaApiError as e:
        return MessageListOutput(error=typed_error(e)).model_dump()
    return MessageListOutput(
        messages=data if isinstance(data, list) else []
    ).model_dump()


HANDLERS = {
    "waha.message.send_text": send_text,
    "waha.message.list": message_list,
    "waha.chat.list": chat_list,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="waha.message.send_text",
             description="Send a WhatsApp text (chat_id OR phone). WRITE / "
             "OUTWARD-FACING — strongest confirm gate (412; a sent "
             "message cannot be unsent).",
             inputSchema=SendTextInput.model_json_schema()),
        Tool(name="waha.message.list",
             description="Recent messages in a chat (chat_id OR phone). "
             "READ-ONLY.",
             inputSchema=MessageListInput.model_json_schema()),
        Tool(name="waha.chat.list",
             description="List chats for a session. READ-ONLY.",
             inputSchema=ChatListInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
