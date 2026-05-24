"""WhatsApp outbound emission — thin product shim over the seed delivery primitive.

The split + sequential-send logic was lifted to the seed 2026-05-23 and now
lives in `noctusai_lib.domain.chatbot.delivery` (`split_reply` +
`send_reply_parts`). This module keeps the product-local names + binds the
channel-neutral seed seam to social-wiring's specifics:

- the toggle/delay come from `settings.whatsapp_paragraph_split` /
  `settings.whatsapp_paragraph_delay_seconds`;
- the `send_one` seam is bound to `intake.send_reply(sender, part)`.

Behavior is unchanged — see `tests/services/test_whatsapp_outbound.py`.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.chatbot import send_reply_parts, split_reply

from app.config import settings

__all__ = ["send_paragraphs", "split_for_whatsapp"]


def split_for_whatsapp(text: str, *, enabled: bool | None = None) -> list[str]:
    """Split `text` into one entry per paragraph, honoring the product toggle.

    Delegates to the seed `split_reply`. `enabled` is the DI seam — defaults
    to `settings.whatsapp_paragraph_split`; tests pass it explicitly instead
    of mutating the singleton. When False → single trimmed entry. Per
    `KB § PATTERNS/di-test-seam.md` (Class-A, service-fn kwarg).
    """
    flag = enabled if enabled is not None else settings.whatsapp_paragraph_split
    return split_reply(text, enabled=flag)


async def send_paragraphs(
    *,
    intake: Any,
    sender: str,
    text: str,
    delay_seconds: float | None = None,
    split: bool | None = None,
) -> int:
    """Send `text` to `sender` as one WAHA message per paragraph.

    Returns the number of paragraphs actually sent. Delegates to the seed
    `send_reply_parts` with the `send_one` seam bound to
    `intake.send_reply(sender, part)`. `delay_seconds` / `split` are DI
    seams — both default to the corresponding `settings` field; tests pass
    them explicitly instead of mutating the singleton. Per
    `KB § PATTERNS/di-test-seam.md`.

    Args:
        intake: Any object exposing `async send_reply(sender, text)` —
            today's `WhatsAppIntakeService` satisfies this.
        sender: WAHA chat id (phone + `@c.us`, or whatever the inbound carried).
        text: The bot's reply; may contain multiple paragraphs.
        delay_seconds: Inter-paragraph delay override.
        split: Paragraph-split toggle override.
    """
    delay = (
        delay_seconds
        if delay_seconds is not None
        else settings.whatsapp_paragraph_delay_seconds
    )
    split_flag = (
        split if split is not None else settings.whatsapp_paragraph_split
    )
    return await send_reply_parts(
        text,
        lambda part: intake.send_reply(sender, part),
        split=split_flag,
        delay_seconds=delay,
    )
