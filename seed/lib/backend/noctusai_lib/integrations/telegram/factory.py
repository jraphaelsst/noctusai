"""The single seam consumers reach for: Real when a bot token resolved, else a DECLARED refusal -- never a
silent Fake (``resolve_fake_or_refuse``). The Fake is an explicit opt-in (tests / local dev)."""
from __future__ import annotations

from typing import Optional

import httpx

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse

from .fake_adapter import FakeTelegramClient
from .real_adapter import HttpxTelegramClient
from .types import TelegramClient, TelegramNotConfiguredError


def _refuse() -> TelegramClient:
    raise TelegramNotConfiguredError("Telegram bot token not configured for this line")


def make_telegram_client(
    bot_token: Optional[str] = None, *, line: str = "default", allow_fake: bool = False,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> TelegramClient:
    """``bot_token`` set -> Real. Unset -> ``TelegramNotConfiguredError`` unless ``allow_fake=True``."""
    return resolve_fake_or_refuse(
        configured=bool(bot_token),
        build_real=lambda: HttpxTelegramClient(bot_token or "", line=line, transport=transport),
        build_fake=lambda: FakeTelegramClient(line=line),
        allow_fake=allow_fake,
        unconfigured=_refuse,
    )
