"""`TelegramGateway` DI seam — every live `telegram.*` tool builds its client
through `get_client()` (module slot default `None`, populated by
`configure_client(...)`, mirrors `mcp/trello/client.py`).

The real gateway wraps Telethon (asyncio-native, MTProto). It connects lazily
on first use and the tool layer always calls `disconnect()` in a `finally`
(see `tools/_run.py`), so the stdio server never holds a socket between calls
and never hangs on a dangling connection. Telethon is imported lazily so the
package (registry, tests, settings) imports without it installed.

Gateway methods return PLAIN dicts (shaped by the pure `shape_*` helpers
below, which duck-type Telethon objects), so tests inject a fake gateway at
the dict level — dependency injection, not monkeypatching.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from _kit.errors import confirmation_required_message

from .settings import get_settings


class TelegramApiError(Exception):
    """A Telegram call could not produce a real result. `status` feeds the
    connector-MCP typed-error contract (`_kit.errors.typed_error`)."""

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(TelegramApiError):
    def __init__(self, action: str, effect: str = ""):
        super().__init__(confirmation_required_message(action, effect), status=412)


class NotConfiguredError(TelegramApiError):
    def __init__(self, message: str):
        super().__init__(message, status=424)


_HASHTAG = re.compile(r"#\w+", re.UNICODE)


def parse_chat(chat: str) -> Any:
    """`'123'`/`'-100123'` -> int id; anything else (`@user`, `user`) stays a str."""
    c = chat.strip()
    if re.fullmatch(r"-?\d+", c):
        return int(c)
    return c


def media_summary(msg: Any) -> Optional[dict]:
    if getattr(msg, "media", None) is None:
        return None
    kind = "other"
    for attr, name in (
        ("photo", "photo"), ("voice", "voice"), ("video_note", "video_note"),
        ("video", "video"), ("audio", "audio"), ("sticker", "sticker"),
        ("gif", "gif"), ("document", "document"),
    ):
        if getattr(msg, attr, None):
            kind = name
            break
    f = getattr(msg, "file", None)
    return {
        "type": kind,
        "file_name": getattr(f, "name", None),
        "size": getattr(f, "size", None),
        "mime_type": getattr(f, "mime_type", None),
        "duration": getattr(f, "duration", None),
    }


def _sender_label(msg: Any) -> Optional[dict]:
    sender = getattr(msg, "sender", None)
    sid = getattr(msg, "sender_id", None)
    if sender is None and sid is None:
        return None
    name = " ".join(
        p for p in (getattr(sender, "first_name", None), getattr(sender, "last_name", None)) if p
    ) or getattr(sender, "title", None)
    return {"id": sid, "username": getattr(sender, "username", None), "name": name}


def shape_message(msg: Any) -> dict:
    text = getattr(msg, "message", None) or getattr(msg, "text", None) or ""
    date = getattr(msg, "date", None)
    reply = getattr(msg, "reply_to", None)
    return {
        "id": msg.id,
        "date": date.isoformat() if hasattr(date, "isoformat") else date,
        "sender": _sender_label(msg),
        "text": text,
        "reply_to": getattr(reply, "reply_to_msg_id", None) if reply else None,
        "media": media_summary(msg),
        "hashtags": _HASHTAG.findall(text),
    }


def shape_dialog(d: Any) -> dict:
    kind = "channel" if getattr(d, "is_channel", False) and not getattr(d, "is_group", False) else (
        "group" if getattr(d, "is_group", False) else "user"
    )
    ent = getattr(d, "entity", None)
    return {
        "id": getattr(d, "id", None),
        "title": getattr(d, "name", None) or getattr(d, "title", None),
        "type": kind,
        "unread": getattr(d, "unread_count", 0),
        "username": getattr(ent, "username", None),
    }


class TelegramGateway:
    """Real gateway over Telethon. One lazily-created client per instance."""

    def __init__(self, *, api_id: int, api_hash: str, session_base: str, session_file: str):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_base = session_base
        self._session_file = session_file
        self._tg: Any = None

    async def _connected(self) -> Any:
        if self._tg is None:
            if not Path(self._session_file).exists():
                raise NotConfiguredError(
                    "No Telegram session — run `mcp/noctusai/.venv/bin/python "
                    "mcp/telegram/login.py` once, interactively."
                )
            try:
                from telethon import TelegramClient  # lazy: optional at import time
            except ImportError as e:  # pragma: no cover - env dependent
                raise NotConfiguredError(
                    "telethon is not installed in this interpreter "
                    "(pip install 'telethon>=1.36,<2')."
                ) from e
            self._tg = TelegramClient(self._session_base, self._api_id, self._api_hash)
        if not self._tg.is_connected():
            await self._tg.connect()
        if not await self._tg.is_user_authorized():
            raise NotConfiguredError(
                "Telegram session is not authorized — re-run mcp/telegram/login.py."
            )
        return self._tg

    async def disconnect(self) -> None:
        if self._tg is not None and self._tg.is_connected():
            await self._tg.disconnect()

    async def is_authorized(self) -> bool:
        try:
            from telethon import TelegramClient
        except ImportError:
            return False
        tg = self._tg or TelegramClient(self._session_base, self._api_id, self._api_hash)
        self._tg = tg
        if not tg.is_connected():
            await tg.connect()
        return bool(await tg.is_user_authorized())

    async def get_me(self) -> dict:
        me = await (await self._connected()).get_me()
        name = " ".join(p for p in (me.first_name, me.last_name) if p) or None
        return {"id": me.id, "username": me.username, "name": name}  # no phone, by design

    async def list_dialogs(self, *, limit: int, query: Optional[str]) -> list[dict]:
        tg = await self._connected()
        out: list[dict] = []
        q = query.lower() if query else None
        async for d in tg.iter_dialogs():
            shaped = shape_dialog(d)
            if q and q not in (shaped["title"] or "").lower() and q not in (shaped["username"] or "").lower():
                continue
            out.append(shaped)
            if len(out) >= limit:
                break
        return out

    async def fetch_messages(
        self, chat: str, *, limit: int, offset_id: int = 0, min_id: int = 0,
        reverse: bool = False, search: Optional[str] = None,
    ) -> list[dict]:
        tg = await self._connected()
        kwargs: dict[str, Any] = {"limit": limit, "offset_id": offset_id, "min_id": min_id, "reverse": reverse}
        if search:
            kwargs["search"] = search
        entity = parse_chat(chat) if chat else None
        return [shape_message(m) async for m in tg.iter_messages(entity, **kwargs)]

    async def download_media(self, chat: str, message_ids: list[int], out_dir: str) -> list[dict]:
        tg = await self._connected()
        msgs = await tg.get_messages(parse_chat(chat), ids=message_ids)
        results: list[dict] = []
        for mid, m in zip(message_ids, msgs):
            if m is None or getattr(m, "media", None) is None:
                results.append({"id": mid, "path": None, "size": None, "error": "no media"})
                continue
            path = await tg.download_media(m, file=out_dir.rstrip("/") + "/")
            size = Path(path).stat().st_size if path else None
            results.append({"id": mid, "path": str(path) if path else None, "size": size})
        return results

    async def send_message(self, chat: str, text: str) -> dict:
        m = await (await self._connected()).send_message(parse_chat(chat), text)
        return {"id": m.id, "date": m.date.isoformat() if m.date else None}


_client_override: Optional[Any] = None


def configure_client(c: Optional[Any]) -> None:
    """Install (or clear with `None`) the gateway the tools use — the test seam."""
    global _client_override
    _client_override = c


def get_client() -> Any:
    if _client_override is not None:
        return _client_override
    s = get_settings()
    if not s.configured:
        raise NotConfiguredError(
            "Telegram connector not configured — set TELEGRAM_API_ID and "
            "TELEGRAM_API_HASH in mcp/telegram/.env."
        )
    return TelegramGateway(
        api_id=int(s.api_id), api_hash=s.api_hash,
        session_base=s.session_base, session_file=s.session_file,
    )
