"""Telegram Bot API value objects, errors and the ``TelegramClient`` Protocol.

Publish-only (official Bot API; no MTProto -- API ToS section 1.5, owner decision 2026-11-13). The bot is an
ADMIN of the channel it posts to; it cannot read channels it is not in, so this is never a news source.

Anti-corruption layer: vendor JSON stops at ``mappers``/the Real adapter; callers see only these types.
Secrets: the bot token is NEVER part of any value object or error message (errors carry the redacted text).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol, Union, runtime_checkable

#: Bot API limits (core.telegram.org/bots/api). Enforced in Fake and Real alike.
MAX_TEXT_LEN = 4096
MAX_CAPTION_LEN = 1024
#: A message can only be deleted for everyone within 48h of sending.
DELETE_WINDOW_SECONDS = 48 * 3600
#: Allowed characters/length of the setWebhook ``secret_token``.
SECRET_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")

#: Updates a publish-only line needs: bot added/removed as admin, and its own channel posts.
DEFAULT_ALLOWED_UPDATES: tuple[str, ...] = ("my_chat_member", "channel_post", "edited_channel_post")

ChatId = Union[int, str]


# --- errors ------------------------------------------------------------------


class TelegramError(Exception):
    """Base. ``description`` is the (token-redacted) vendor text; ``status`` the HTTP/error_code (0 = transport)."""

    def __init__(self, description: str, *, status: int = 0) -> None:
        super().__init__(description)
        self.description = description
        self.status = status


class TelegramNotConfiguredError(TelegramError):
    """No bot token resolved for the line -- a declared refusal, never a silent Fake."""


class TelegramAuthError(TelegramError):
    """401 -- the token is invalid or was revoked (the line goes to ``needs_reconnection``)."""


class TelegramForbiddenError(TelegramError):
    """403 -- the bot was kicked from the chat / lacks the right to post."""


class TelegramNotFoundError(TelegramError):
    """Chat / message not found (404, or 400 'chat not found')."""


class TelegramBadRequestError(TelegramError):
    """400 -- malformed request (text too long, bad entities, bad webhook url ...)."""


class TelegramMessageNotDeletableError(TelegramBadRequestError):
    """delete_message refused: older than 48h (or otherwise not deletable). Edit to a tombstone instead."""


class TelegramMessageNotModifiedError(TelegramBadRequestError):
    """edit_message_text with identical content ('message is not modified') -- an idempotent no-op for callers."""


class TelegramRateLimitedError(TelegramError):
    """429 -- ``retry_after`` seconds from ``parameters.retry_after`` (the vendor's own pacing hint)."""

    def __init__(self, description: str, *, retry_after: Optional[float] = None) -> None:
        super().__init__(description, status=429)
        self.retry_after = retry_after


class TelegramUnreachableError(TelegramError):
    """Transport failure / timeout / 5xx. For a WRITE the outcome is UNKNOWN: never blind-retried (reconcile first)."""


class WebhookEstrangeiroError(TelegramError):
    """Clobber guard: the bot already has a webhook that is not ours (another app owns this bot) -- 409."""

    status_code = 409
    code = "webhook_estrangeiro"

    def __init__(self, description: str = "webhook_estrangeiro") -> None:
        super().__init__(description, status=409)


# --- value objects -----------------------------------------------------------


@dataclass(frozen=True)
class BotInfo:
    id: int
    username: str
    first_name: str = ""
    is_bot: bool = True


@dataclass(frozen=True)
class ChatInfo:
    id: int
    type: str  # "channel" | "supergroup" | "group" | "private"
    title: str = ""
    username: Optional[str] = None


@dataclass(frozen=True)
class ChatMember:
    status: str  # "creator" | "administrator" | "member" | "left" | "kicked" | ...
    user_id: int = 0
    can_post_messages: bool = False
    can_edit_messages: bool = False
    can_delete_messages: bool = False

    @property
    def is_admin(self) -> bool:
        return self.status in ("creator", "administrator")


@dataclass(frozen=True)
class SentMessage:
    message_id: int
    chat_id: int
    date: int = 0  # unix seconds, as Telegram reports it


@dataclass(frozen=True)
class WebhookInfo:
    url: str = ""
    pending_update_count: int = 0
    last_error_message: Optional[str] = None
    allowed_updates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChannelAdminCheck:
    """Whether the bot may publish to a channel (see :func:`~.channels.verify_bot_channel_admin`)."""

    chat: ChatInfo
    is_admin: bool
    can_post: bool
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.chat.type == "channel" and self.is_admin and self.can_post


# --- Protocol ----------------------------------------------------------------


@runtime_checkable
class TelegramClient(Protocol):
    """Async Bot API surface. One client = one bot (one Telegram "line")."""

    async def get_me(self) -> BotInfo: ...
    async def get_chat(self, chat_id: ChatId) -> ChatInfo: ...
    async def get_chat_member(self, chat_id: ChatId, user_id: int) -> ChatMember: ...
    async def get_chat_administrators(self, chat_id: ChatId) -> list[ChatMember]: ...
    async def get_chat_member_count(self, chat_id: ChatId) -> int: ...
    async def send_message(
        self, chat_id: ChatId, text: str, *, disable_web_page_preview: bool = False,
        disable_notification: bool = False,
    ) -> SentMessage: ...
    async def send_photo(
        self, chat_id: ChatId, photo: str, *, caption: Optional[str] = None, disable_notification: bool = False,
    ) -> SentMessage: ...
    async def edit_message_text(
        self, chat_id: ChatId, message_id: int, text: str, *, disable_web_page_preview: bool = False,
    ) -> SentMessage: ...
    async def delete_message(self, chat_id: ChatId, message_id: int) -> bool: ...
    async def set_webhook(
        self, url: str, *, secret_token: str, allowed_updates: Optional[tuple[str, ...]] = None,
    ) -> bool: ...
    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool: ...
    async def get_webhook_info(self) -> WebhookInfo: ...


def validate_secret_token(secret_token: str) -> str:
    """The setWebhook ``secret_token`` rule (1-256 chars of ``A-Za-z0-9_-``); shared by Fake and Real."""
    if not SECRET_TOKEN_RE.match(secret_token or ""):
        raise TelegramBadRequestError("secret_token must be 1-256 chars of A-Z a-z 0-9 _ -", status=400)
    return secret_token


def validate_text(text: str, *, limit: int = MAX_TEXT_LEN, what: str = "text") -> str:
    if not text or not text.strip():
        raise TelegramBadRequestError(f"{what} is empty", status=400)
    if len(text) > limit:
        raise TelegramBadRequestError(f"{what} too long ({len(text)} > {limit})", status=400)
    return text
