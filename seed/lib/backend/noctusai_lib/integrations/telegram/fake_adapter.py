"""In-memory Telegram Bot API stand-in with Real-adapter parity (errors, limits, 48h delete window, webhook rules).

Seed state with :meth:`add_channel` / :meth:`add_group`; inspect ``sent`` / ``webhook``. ``fail_next(exc)`` queues an
error for the next call (e.g. a 429). Calls are paced through the SAME ``rate.paced`` seam as the Real adapter, so
bucket behaviour is exercised in Fake-backed tests too.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from .rate import paced
from .types import (
    DEFAULT_ALLOWED_UPDATES, DELETE_WINDOW_SECONDS, MAX_CAPTION_LEN, MAX_TEXT_LEN, BotInfo, ChatId, ChatInfo,
    ChatMember, SentMessage, TelegramAuthError, TelegramBadRequestError, TelegramForbiddenError,
    TelegramMessageNotDeletableError, TelegramMessageNotModifiedError, TelegramNotFoundError, WebhookInfo,
    validate_secret_token, validate_text,
)


@dataclass
class _Msg:
    chat_id: int
    message_id: int
    text: str
    sent_at: float
    kind: str = "text"
    deleted: bool = False


@dataclass
class _Chat:
    info: ChatInfo
    bot_status: str = "administrator"
    can_post: bool = True
    members: int = 0
    next_id: int = 1


class FakeTelegramClient:
    def __init__(
        self, *, bot: Optional[BotInfo] = None, line: str = "fake", now: Callable[[], float] = time.time,
    ) -> None:
        self.bot = bot or BotInfo(id=1000001, username="fake_bot", first_name="Fake", is_bot=True)
        self._line = line
        self._now = now
        self.chats: dict[int, _Chat] = {}
        self.sent: list[_Msg] = []
        self.webhook = WebhookInfo()
        self.webhook_secret: Optional[str] = None
        self.calls: list[str] = []
        self._queued: list[Exception] = []
        self.token_valid = True

    # --- seeding / inspection ---
    def add_channel(self, chat_id: int, title: str = "Canal", *, username: Optional[str] = None,
                    bot_status: str = "administrator", can_post: bool = True, members: int = 0) -> None:
        self.chats[chat_id] = _Chat(ChatInfo(chat_id, "channel", title, username), bot_status, can_post, members)

    def add_group(self, chat_id: int, title: str = "Grupo") -> None:
        self.chats[chat_id] = _Chat(ChatInfo(chat_id, "supergroup", title), "member", False)

    def fail_next(self, exc: Exception) -> None:
        self._queued.append(exc)

    # --- internals ---
    def _resolve(self, chat_id: ChatId) -> _Chat:
        if isinstance(chat_id, str) and chat_id.startswith("@"):
            for c in self.chats.values():
                if (c.info.username or "").lower() == chat_id[1:].lower():
                    return c
        elif isinstance(chat_id, int) and chat_id in self.chats:
            return self.chats[chat_id]
        raise TelegramNotFoundError("Bad Request: chat not found", status=400)

    def _poster(self, chat_id: ChatId) -> _Chat:
        chat = self._resolve(chat_id)
        if chat.bot_status not in ("administrator", "creator") or not chat.can_post:
            raise TelegramForbiddenError("Forbidden: bot is not a member of the channel chat / no rights", status=403)
        return chat

    async def _run(self, name: str, fn: Callable[[], Any], chat_id: Any = None) -> Any:
        self.calls.append(name)

        async def _once() -> Any:
            if self._queued:
                raise self._queued.pop(0)
            if not self.token_valid:
                raise TelegramAuthError("Unauthorized", status=401)
            return fn()

        return await paced(_once, line=self._line, chat_id=chat_id)

    # --- reads ---
    async def get_me(self) -> BotInfo:
        return await self._run("getMe", lambda: self.bot)

    async def get_chat(self, chat_id: ChatId) -> ChatInfo:
        return await self._run("getChat", lambda: self._resolve(chat_id).info)

    def _member(self, chat: _Chat, user_id: int) -> ChatMember:
        if user_id != self.bot.id:
            raise TelegramBadRequestError("Bad Request: user not found", status=400)
        admin = chat.bot_status in ("administrator", "creator")
        return ChatMember(chat.bot_status, user_id, chat.can_post and admin, admin, admin)

    async def get_chat_member(self, chat_id: ChatId, user_id: int) -> ChatMember:
        return await self._run("getChatMember", lambda: self._member(self._resolve(chat_id), user_id))

    async def get_chat_administrators(self, chat_id: ChatId) -> list[ChatMember]:
        def _f() -> list[ChatMember]:
            chat = self._resolve(chat_id)
            return [self._member(chat, self.bot.id)] if chat.bot_status in ("administrator", "creator") else []
        return await self._run("getChatAdministrators", _f)

    async def get_chat_member_count(self, chat_id: ChatId) -> int:
        return await self._run("getChatMemberCount", lambda: self._resolve(chat_id).members)

    # --- writes ---
    def _store(self, chat: _Chat, text: str, kind: str) -> SentMessage:
        mid = chat.next_id
        chat.next_id += 1
        t = self._now()
        self.sent.append(_Msg(chat.info.id, mid, text, t, kind))
        return SentMessage(mid, chat.info.id, int(t))

    async def send_message(self, chat_id: ChatId, text: str, *, disable_web_page_preview: bool = False,
                           disable_notification: bool = False) -> SentMessage:
        validate_text(text, limit=MAX_TEXT_LEN)
        return await self._run("sendMessage", lambda: self._store(self._poster(chat_id), text, "text"), chat_id)

    async def send_photo(self, chat_id: ChatId, photo: str, *, caption: Optional[str] = None,
                         disable_notification: bool = False) -> SentMessage:
        if caption:
            validate_text(caption, limit=MAX_CAPTION_LEN, what="caption")
        return await self._run("sendPhoto", lambda: self._store(self._poster(chat_id), caption or "", "photo"), chat_id)

    def _find(self, chat: _Chat, message_id: int) -> _Msg:
        for m in self.sent:
            if m.chat_id == chat.info.id and m.message_id == message_id and not m.deleted:
                return m
        raise TelegramNotFoundError("Bad Request: message to edit not found", status=400)

    async def edit_message_text(self, chat_id: ChatId, message_id: int, text: str, *,
                                disable_web_page_preview: bool = False) -> SentMessage:
        validate_text(text, limit=MAX_TEXT_LEN)

        def _f() -> SentMessage:
            chat = self._poster(chat_id)
            m = self._find(chat, message_id)
            if m.text == text:
                raise TelegramMessageNotModifiedError("Bad Request: message is not modified", status=400)
            m.text = text
            return SentMessage(m.message_id, m.chat_id, int(m.sent_at))
        return await self._run("editMessageText", _f, chat_id)

    async def delete_message(self, chat_id: ChatId, message_id: int) -> bool:
        def _f() -> bool:
            chat = self._poster(chat_id)
            m = self._find(chat, message_id)
            if self._now() - m.sent_at > DELETE_WINDOW_SECONDS:
                raise TelegramMessageNotDeletableError("Bad Request: message can't be deleted for everyone", status=400)
            m.deleted = True
            return True
        return await self._run("deleteMessage", _f, chat_id)

    # --- webhook ---
    async def set_webhook(self, url: str, *, secret_token: str,
                          allowed_updates: Optional[tuple[str, ...]] = None) -> bool:
        validate_secret_token(secret_token)
        if not url.startswith("https://"):
            raise TelegramBadRequestError("Bad Request: bad webhook: HTTPS url must be provided for webhook", status=400)

        def _f() -> bool:
            self.webhook = WebhookInfo(url=url, allowed_updates=tuple(allowed_updates or DEFAULT_ALLOWED_UPDATES))
            self.webhook_secret = secret_token
            return True
        return await self._run("setWebhook", _f)

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool:
        def _f() -> bool:
            self.webhook = WebhookInfo()
            self.webhook_secret = None
            return True
        return await self._run("deleteWebhook", _f)

    async def get_webhook_info(self) -> WebhookInfo:
        return await self._run("getWebhookInfo", lambda: replace(self.webhook))
