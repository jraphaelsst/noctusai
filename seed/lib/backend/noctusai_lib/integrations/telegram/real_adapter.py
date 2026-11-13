"""Real Telegram Bot API client (httpx). Every call is paced by ``rate.paced``; vendor JSON stops at ``mappers``.

Formatting is HTML (``parse_mode=HTML``): MarkdownV2 escaping breaks on scraped titles. The token lives only in
the URL path built here; errors/logs carry :func:`~.redact.redact`-ed text.
Write safety: a transport timeout on a send is an UNKNOWN outcome -> :class:`TelegramUnreachableError`, never
retried (the caller reconciles); only a 429 (vendor guarantees "not processed") is retried.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from noctusai_lib.integrations.rate_limit import parse_retry_after

from . import mappers
from .rate import paced
from .redact import install_httpx_redaction, redact
from .types import (
    DEFAULT_ALLOWED_UPDATES, MAX_CAPTION_LEN, MAX_TEXT_LEN, BotInfo, ChatId, ChatInfo, ChatMember,
    SentMessage, TelegramAuthError, TelegramBadRequestError, TelegramError, TelegramForbiddenError,
    TelegramMessageNotDeletableError, TelegramMessageNotModifiedError, TelegramNotFoundError,
    TelegramRateLimitedError, TelegramUnreachableError, WebhookInfo, validate_secret_token, validate_text,
)

API_BASE = "https://api.telegram.org"
_TIMEOUT = 30.0


def translate_error(status: int, body: dict[str, Any], headers: Optional[httpx.Headers] = None) -> TelegramError:
    desc = redact(body.get("description") or f"HTTP {status}")
    code = int(body.get("error_code") or status)
    low = desc.lower()
    if code == 429:
        hinted = (body.get("parameters") or {}).get("retry_after")
        if hinted is None and headers is not None:
            hinted = parse_retry_after(headers.get("Retry-After"))
        return TelegramRateLimitedError(desc, retry_after=float(hinted) if hinted is not None else None)
    if code == 401:
        return TelegramAuthError(desc, status=401)
    if code == 403:
        return TelegramForbiddenError(desc, status=403)
    if code == 404 or "chat not found" in low or "message to edit not found" in low or "message to delete not found" in low:
        return TelegramNotFoundError(desc, status=code)
    if code == 400:
        if "can't be deleted" in low or "cant be deleted" in low:
            return TelegramMessageNotDeletableError(desc, status=400)
        if "not modified" in low:
            return TelegramMessageNotModifiedError(desc, status=400)
        return TelegramBadRequestError(desc, status=400)
    if code >= 500:
        return TelegramUnreachableError(desc, status=code)
    return TelegramError(desc, status=code)


class HttpxTelegramClient:
    def __init__(
        self, bot_token: str, *, line: str = "default", transport: Optional[httpx.AsyncBaseTransport] = None,
        api_base: str = API_BASE,
    ) -> None:
        if not bot_token:
            raise ValueError("HttpxTelegramClient needs a bot token")
        self._token = bot_token
        self._line = line
        self._transport = transport  # test seam: httpx.MockTransport exercises the REAL path, no monkey-patching
        self._base = api_base.rstrip("/")
        install_httpx_redaction()

    def __repr__(self) -> str:  # never leak the token via repr/logging of the client
        return f"HttpxTelegramClient(line={self._line!r}, token=<redacted>)"

    async def _call(self, method: str, payload: Optional[dict[str, Any]] = None, *, chat_id: Any = None) -> Any:
        url = f"{self._base}/bot{self._token}/{method}"

        async def _once() -> Any:
            try:
                async with httpx.AsyncClient(transport=self._transport, timeout=_TIMEOUT) as http:
                    resp = await http.post(url, json=payload or {})
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                raise TelegramUnreachableError(f"{method}: {redact(exc)}") from None
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if resp.status_code == 200 and body.get("ok"):
                return body.get("result")
            raise translate_error(resp.status_code, body if isinstance(body, dict) else {}, resp.headers)

        return await paced(_once, line=self._line, chat_id=chat_id)

    # --- reads ---
    async def get_me(self) -> BotInfo:
        return mappers.to_bot(await self._call("getMe"))

    async def get_chat(self, chat_id: ChatId) -> ChatInfo:
        return mappers.to_chat(await self._call("getChat", {"chat_id": chat_id}))

    async def get_chat_member(self, chat_id: ChatId, user_id: int) -> ChatMember:
        return mappers.to_member(await self._call("getChatMember", {"chat_id": chat_id, "user_id": user_id}))

    async def get_chat_administrators(self, chat_id: ChatId) -> list[ChatMember]:
        return [mappers.to_member(m) for m in await self._call("getChatAdministrators", {"chat_id": chat_id})]

    async def get_chat_member_count(self, chat_id: ChatId) -> int:
        return int(await self._call("getChatMemberCount", {"chat_id": chat_id}))

    # --- writes ---
    async def send_message(
        self, chat_id: ChatId, text: str, *, disable_web_page_preview: bool = False,
        disable_notification: bool = False,
    ) -> SentMessage:
        validate_text(text, limit=MAX_TEXT_LEN)
        raw = await self._call("sendMessage", {
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": disable_web_page_preview},
            "disable_notification": disable_notification,
        }, chat_id=chat_id)
        return mappers.to_sent(raw)

    async def send_photo(
        self, chat_id: ChatId, photo: str, *, caption: Optional[str] = None, disable_notification: bool = False,
    ) -> SentMessage:
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo, "disable_notification": disable_notification}
        if caption:
            payload.update(caption=validate_text(caption, limit=MAX_CAPTION_LEN, what="caption"), parse_mode="HTML")
        return mappers.to_sent(await self._call("sendPhoto", payload, chat_id=chat_id))

    async def edit_message_text(
        self, chat_id: ChatId, message_id: int, text: str, *, disable_web_page_preview: bool = False,
    ) -> SentMessage:
        validate_text(text, limit=MAX_TEXT_LEN)
        raw = await self._call("editMessageText", {
            "chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": disable_web_page_preview},
        }, chat_id=chat_id)
        return mappers.to_sent(raw)

    async def delete_message(self, chat_id: ChatId, message_id: int) -> bool:
        return bool(await self._call("deleteMessage", {"chat_id": chat_id, "message_id": message_id}, chat_id=chat_id))

    # --- webhook ---
    async def set_webhook(
        self, url: str, *, secret_token: str, allowed_updates: Optional[tuple[str, ...]] = None,
    ) -> bool:
        validate_secret_token(secret_token)
        return bool(await self._call("setWebhook", {
            "url": url, "secret_token": secret_token,
            "allowed_updates": list(allowed_updates or DEFAULT_ALLOWED_UPDATES),
        }))

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool:
        return bool(await self._call("deleteWebhook", {"drop_pending_updates": drop_pending_updates}))

    async def get_webhook_info(self) -> WebhookInfo:
        return mappers.to_webhook_info(await self._call("getWebhookInfo"))
