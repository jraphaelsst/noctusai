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


def split_for_whatsapp(text: str) -> list[str]:
    """Split `text` into one entry per paragraph, honoring the product toggle.

    Delegates to the seed `split_reply`; `settings.whatsapp_paragraph_split`
    drives the `enabled` flag (when False → single trimmed entry).
    """
    return split_reply(text, enabled=settings.whatsapp_paragraph_split)


async def send_paragraphs(
    *,
    intake: Any,
    sender: str,
    text: str,
    delay_seconds: float | None = None,
) -> int:
    """Send `text` to `sender` as one WAHA message per paragraph.

    Returns the number of paragraphs actually sent. Delegates to the seed
    `send_reply_parts` with the `send_one` seam bound to
    `intake.send_reply(sender, part)`. `delay_seconds` defaults to
    `settings.whatsapp_paragraph_delay_seconds`.

    Args:
        intake: Any object exposing `async send_reply(sender, text)` —
            today's `WhatsAppIntakeService` satisfies this.
        sender: WAHA chat id (phone + `@c.us`, or whatever the inbound carried).
        text: The bot's reply; may contain multiple paragraphs.
        delay_seconds: Inter-paragraph delay override.
    """
    delay = (
        delay_seconds
        if delay_seconds is not None
        else settings.whatsapp_paragraph_delay_seconds
    )
    return await send_reply_parts(
        text,
        lambda part: intake.send_reply(sender, part),
        split=settings.whatsapp_paragraph_split,
        delay_seconds=delay,
    )
