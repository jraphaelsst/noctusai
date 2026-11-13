"""Rate-limit wiring for Telegram -- every Bot API call goes through here, never around it.

Buckets (``noctusai_lib.integrations.rate_limit``):
* ``telegram`` -- ~25/s global (Telegram allows ~30/s per bot; headroom kept).
* ``telegram_chat:{line}:{chat}`` -- 20/min per chat (0.33/s, burst 3): Telegram's 1 msg/s per chat and
  ~20/min per group; channels are assumed to follow the group limit.
429 is retried ONLY because Telegram guarantees a 429 request was not processed; the vendor's ``retry_after``
wins over our backoff, and past the bucket's ``max_retry_after`` it becomes ``RetryLater`` for the job layer.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.integrations import rate_limit

from .types import TelegramRateLimitedError

GLOBAL_BUCKET = "telegram"
GLOBAL_RATE, GLOBAL_BURST = 25.0, 25.0
CHAT_RATE, CHAT_BURST = 0.33, 3.0


def chat_bucket(line: str, chat_id: Any) -> str:
    return f"telegram_chat:{line}:{chat_id}"


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, TelegramRateLimitedError)


def _retry_after(exc: BaseException) -> Optional[float]:
    return getattr(exc, "retry_after", None)


async def paced(fn: Callable[[], Awaitable[Any]], *, line: str, chat_id: Any = None) -> Any:
    """Run one logical Bot API call: pace EACH attempt on the global (+ per-chat) bucket, back off on 429."""
    rate_limit.configure_bucket(GLOBAL_BUCKET, rate_per_sec=GLOBAL_RATE, burst=GLOBAL_BURST)
    chat = chat_bucket(line, chat_id) if chat_id is not None else None
    if chat:
        rate_limit.configure_bucket(chat, rate_per_sec=CHAT_RATE, burst=CHAT_BURST, like=GLOBAL_BUCKET)

    async def _attempt() -> Any:
        await rate_limit.acquire_async(GLOBAL_BUCKET)
        if chat:
            await rate_limit.acquire_async(chat)
        return await fn()

    return await rate_limit.retry_with_backoff_async(
        _attempt, bucket=GLOBAL_BUCKET, is_retryable=_is_retryable, retry_after=_retry_after
    )
