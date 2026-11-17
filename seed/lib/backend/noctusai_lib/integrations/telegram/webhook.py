"""Inbound webhook safety for a Telegram line.

* :func:`verify_telegram_secret_token` -- ``X-Telegram-Bot-Api-Secret-Token`` vs the line's stored secret with
  ``hmac.compare_digest``; missing header, missing stored secret, or mismatch is ``False`` (a handler maps it to a
  STRICT 401 via :func:`require_telegram_secret_token` -- never 404/422, never open when the secret is unset).
* :func:`ensure_webhook_ours` / :func:`connect_webhook` -- clobber guard: a bot is global to Telegram, so if
  ``getWebhookInfo`` shows a URL that is not ours another app owns it; we refuse (409 ``webhook_estrangeiro``)
  rather than silently stealing its updates. After ``setWebhook`` the config is READ BACK and checked.

Route shape (mounted by the consumer, tier ``service``/signed): ``POST /api/telegram/webhook/{webhook_token}``;
unknown token -> generic 404, never an enumeration signal; the token value is never logged.
"""
from __future__ import annotations

import hmac
from typing import Optional

from .types import (
    DEFAULT_ALLOWED_UPDATES, TelegramBadRequestError, TelegramClient, WebhookEstrangeiroError, WebhookInfo,
)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def verify_telegram_secret_token(provided: Optional[str], expected: Optional[str]) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_telegram_secret_token(provided: Optional[str], expected: Optional[str]) -> None:
    """Raise ``HTTPException(401)`` unless the header matches. Strict 401 (the auth-boundary contract)."""
    if not verify_telegram_secret_token(provided, expected):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="invalid_secret_token")


def webhook_estrangeiro_http_exception(exc: Optional[WebhookEstrangeiroError] = None):
    from fastapi import HTTPException

    return HTTPException(status_code=409, detail={"code": WebhookEstrangeiroError.code})


async def ensure_webhook_ours(client: TelegramClient, our_url: str) -> WebhookInfo:
    """Refuse (409) when the bot's current webhook is a foreign URL. Empty or identical is fine."""
    info = await client.get_webhook_info()
    if info.url and info.url != our_url:
        raise WebhookEstrangeiroError()
    return info


async def connect_webhook(
    client: TelegramClient, url: str, secret_token: str, *, allowed_updates: Optional[tuple[str, ...]] = None,
) -> WebhookInfo:
    """Guard -> setWebhook -> read-back. A config PUT and never read back is unverified (integration canon 7)."""
    await ensure_webhook_ours(client, url)
    wanted = tuple(allowed_updates or DEFAULT_ALLOWED_UPDATES)
    await client.set_webhook(url, secret_token=secret_token, allowed_updates=wanted)
    echoed = await client.get_webhook_info()
    if echoed.url != url:
        raise TelegramBadRequestError("setWebhook not reflected by getWebhookInfo", status=0)
    return echoed
