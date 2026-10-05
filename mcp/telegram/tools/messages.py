"""`telegram.messages.*` — list/search/export (READ) and send (confirm-gated WRITE).

Export writes metadata only (NDJSON, optional markdown) — never media bytes —
and only under the gitignored `mcp/telegram/.exports/`. FloodWait is honoured
with a bounded sleep per error and a bounded retry count.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from mcp.server import Server
from mcp.types import Tool

from .. import client
from ..settings import get_settings
from ..types import MessagesExportInput, MessagesListInput, MessagesSearchInput, MessagesSendInput
from ._run import run_with_gateway

PAGE_SIZE = 100
MAX_FLOOD_RETRIES = 5


async def messages_list(args: dict) -> dict:
    inp = MessagesListInput(**args)

    async def _go(gw):
        rows = await gw.fetch_messages(
            inp.chat, limit=inp.limit, offset_id=inp.offset_id, min_id=inp.min_id, reverse=inp.reverse
        )
        return {"messages": rows, "count": len(rows)}

    return await run_with_gateway(_go, messages=[], count=0)


async def messages_search(args: dict) -> dict:
    inp = MessagesSearchInput(**args)

    async def _go(gw):
        rows = await gw.fetch_messages(inp.chat or "", limit=inp.limit, search=inp.query)
        return {"messages": rows, "count": len(rows)}

    return await run_with_gateway(_go, messages=[], count=0)


def _is_flood_wait(e: Exception) -> bool:
    return type(e).__name__ == "FloodWaitError" and hasattr(e, "seconds")


async def fetch_page_with_flood_wait(
    gw: Any, chat: str, offset_id: int, max_wait: int,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> list[dict]:
    """One page; on FloodWait sleep min(seconds, max_wait) and retry, bounded."""
    for attempt in range(MAX_FLOOD_RETRIES + 1):
        try:
            return await gw.fetch_messages(chat, limit=PAGE_SIZE, offset_id=offset_id)
        except Exception as e:
            if not _is_flood_wait(e) or attempt == MAX_FLOOD_RETRIES:
                raise
            await sleep(min(int(e.seconds), max_wait))
    return []  # unreachable


def _md_line(m: dict) -> str:
    who = (m.get("sender") or {}).get("name") or (m.get("sender") or {}).get("username") or "?"
    media = f" [{m['media']['type']}: {m['media'].get('file_name') or ''}]" if m.get("media") else ""
    return f"- **{m['date']}** #{m['id']} {who}: {m['text']}{media}".rstrip()


async def messages_export(args: dict, *, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> dict:
    inp = MessagesExportInput(**args)
    s = get_settings()
    base = re.sub(r"[^A-Za-z0-9._-]", "_", inp.name or inp.chat).strip("._") or "export"
    out_dir = Path(s.exports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nd_path = out_dir / f"{base}.ndjson"
    md_path = out_dir / f"{base}.md" if inp.markdown else None

    async def _go(gw):
        count, offset = 0, 0
        md_file = md_path.open("w", encoding="utf-8") if md_path else None
        try:
            with nd_path.open("w", encoding="utf-8") as nd:
                while True:
                    page = await fetch_page_with_flood_wait(
                        gw, inp.chat, offset, s.max_flood_wait_seconds, sleep
                    )
                    if not page:
                        break
                    for m in page:
                        nd.write(json.dumps(m, ensure_ascii=False) + "\n")
                        if md_file:
                            md_file.write(_md_line(m) + "\n")
                    count += len(page)
                    offset = min(m["id"] for m in page)
        finally:
            if md_file:
                md_file.close()
        return {"path": str(nd_path), "markdown_path": str(md_path) if md_path else None, "count": count}

    return await run_with_gateway(_go, path=None, count=0)


async def messages_send(args: dict) -> dict:
    inp = MessagesSendInput(**args)
    if not inp.confirm:
        from _kit.errors import typed_error
        return {
            "sent": False,
            "error": typed_error(client.ConfirmationRequiredError(
                "telegram.messages.send", f"sends a message to {inp.chat} from the logged-in account"
            )),
        }

    async def _go(gw):
        return {"sent": True, "message": await gw.send_message(inp.chat, inp.text)}

    return await run_with_gateway(_go, sent=False)


HANDLERS = {
    "telegram.messages.list": messages_list,
    "telegram.messages.search": messages_search,
    "telegram.messages.export": messages_export,
    "telegram.messages.send": messages_send,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="telegram.messages.list",
             description="List messages of a chat (id, date, sender, text, reply_to, media "
             "summary, hashtags); limit<=500. READ.",
             inputSchema=MessagesListInput.model_json_schema()),
        Tool(name="telegram.messages.search",
             description="Search messages (one chat, or global when chat omitted). READ.",
             inputSchema=MessagesSearchInput.model_json_schema()),
        Tool(name="telegram.messages.export",
             description="Export ALL message text + media METADATA (no media bytes) of a chat to "
             "NDJSON (+ optional markdown) under the gitignored mcp/telegram/.exports/. Paginated, "
             "bounded FloodWait handling. READ (writes only a local metadata file).",
             inputSchema=MessagesExportInput.model_json_schema()),
        Tool(name="telegram.messages.send",
             description="Send a text message from the logged-in account. WRITE — confirm-gated: "
             "returns a typed 412 without confirm=true, before any Telegram call.",
             inputSchema=MessagesSendInput.model_json_schema()),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
