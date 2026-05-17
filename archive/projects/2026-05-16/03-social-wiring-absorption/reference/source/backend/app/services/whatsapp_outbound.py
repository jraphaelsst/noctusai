"""WhatsApp outbound emission helpers.

Two responsibilities:

- ``split_for_whatsapp(text)`` — split a multi-paragraph reply on ``\\n\\n``
  into individual WhatsApp messages. Reflects how humans chat: each
  paragraph lands as its own bubble, not a single wall of text.
- ``send_paragraphs(intake, sender, text)`` — drive ``intake.send_reply``
  once per paragraph with a short inter-message delay so WAHA + the
  mobile clients render the messages in order.

Both honor ``settings.whatsapp_paragraph_split`` — when ``False``, the
helpers degrade to the legacy single-message behavior so the toggle is
truly reversible.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# Matches one-or-more blank lines (``\n\n`` or more, possibly with
# whitespace-only lines between). Module-private so the public
# ``split_for_whatsapp`` keeps the regex detail hidden.
_PARAGRAPH_RE = re.compile(r"\n\s*\n+")


def split_for_whatsapp(text: str) -> list[str]:
    """Return ``text`` split into one entry per paragraph.

    Splits on ``\\n\\n`` (one or more blank lines between paragraphs),
    strips empties, and trims each entry. When
    ``settings.whatsapp_paragraph_split`` is ``False`` returns a
    single-element list so callers can loop unconditionally.

    Examples:

        >>> split_for_whatsapp("hello")
        ['hello']
        >>> split_for_whatsapp("oi\\n\\ntudo bem?\\n\\nsim")
        ['oi', 'tudo bem?', 'sim']
        >>> split_for_whatsapp("")
        []
    """
    if not text or not text.strip():
        return []
    if not settings.whatsapp_paragraph_split:
        return [text.strip()]
    # Treat sequences of 2+ newlines as paragraph breaks; single newlines
    # inside a paragraph are kept as soft-wraps (WhatsApp renders them).
    raw_parts = [part.strip() for part in _PARAGRAPH_RE.split(text)]
    return [part for part in raw_parts if part]


async def send_paragraphs(
    *,
    intake: Any,
    sender: str,
    text: str,
    delay_seconds: float | None = None,
) -> int:
    """Send ``text`` to ``sender`` as one WAHA message per paragraph.

    Returns the number of paragraphs actually sent. Exceptions from
    individual sends are logged and DO NOT halt the loop — partial
    delivery beats no delivery for chatbot replies.

    Args:
        intake: Any object exposing ``async send_reply(sender, text)`` —
            today's ``WhatsAppIntakeService`` satisfies this.
        sender: WAHA chat id (phone + ``@c.us``, or whatever form the
            inbound carried).
        text: The bot's reply; may contain multiple paragraphs.
        delay_seconds: Inter-paragraph delay override. Defaults to
            ``settings.whatsapp_paragraph_delay_seconds``.
    """
    paragraphs = split_for_whatsapp(text)
    if not paragraphs:
        return 0

    delay = (
        delay_seconds
        if delay_seconds is not None
        else settings.whatsapp_paragraph_delay_seconds
    )

    sent = 0
    for idx, paragraph in enumerate(paragraphs):
        try:
            await intake.send_reply(sender, paragraph)
            sent += 1
        except Exception:
            logger.exception(
                "send_paragraphs: WAHA send failed (paragraph %d/%d, sender=%s)",
                idx + 1,
                len(paragraphs),
                sender,
            )
            continue
        if idx + 1 < len(paragraphs) and delay > 0:
            await asyncio.sleep(delay)
    return sent


__all__ = ["send_paragraphs", "split_for_whatsapp"]
