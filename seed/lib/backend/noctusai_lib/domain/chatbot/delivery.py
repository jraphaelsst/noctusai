"""Human-like reply delivery — split a long reply into bubbles + sequential send.

A long LLM reply sent as one message reads as a wall of text; real people
send several short messages. This module is the channel-neutral delivery
half of the chatbot framework (the inbound half is `buffer.py` debounce):

- `split_reply(text)` — break a reply on paragraph boundaries (blank lines)
  into one entry per bubble. Pure function, no I/O.
- `send_reply_parts(text, send_one, ...)` / `send_reply_parts_sync(...)` —
  drive a consumer-supplied sender once per part with a short inter-message
  delay so the client renders the bubbles in order. The `send_one` seam is
  any callable that delivers one text part, so WhatsApp (WAHA `send_text` /
  `send_text_sync`), Telegram, or in-app messaging all satisfy it — the
  consumer closes over the destination + transport.

Lifted to the seed 2026-05-23 from
`products/social-wiring/app/services/whatsapp_outbound.py` (N=1 product fork
→ seed delivery primitive). The n8n "SDR Agent" template independently
implements the same multi-bubble emit (Passo 04+05), confirming it as a
standard, reusable chatbot pattern rather than a social-wiring quirk. The
inbound Redis debounce it pairs with already lives in `buffer.py` +
`worker.py`. See `KB § PATTERNS/whatsapp-chatbot-seed.md § 3` for wiring.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# 2+ newlines (optionally with whitespace-only lines between) = a paragraph
# break. Single newlines inside a paragraph are soft-wraps the client renders.
_PARAGRAPH_RE = re.compile(r"\n\s*\n+")


def split_reply(text: str, *, enabled: bool = True) -> list[str]:
    """Return `text` split into one entry per paragraph (blank-line boundaries).

    Strips empties and trims each part. When `enabled` is False, returns a
    single-element list (the trimmed whole) so callers can loop
    unconditionally regardless of the toggle. Blank input → `[]`.

    Examples:

        >>> split_reply("hello")
        ['hello']
        >>> split_reply("oi\\n\\ntudo bem?\\n\\nsim")
        ['oi', 'tudo bem?', 'sim']
        >>> split_reply("")
        []
        >>> split_reply("a\\n\\nb", enabled=False)
        ['a\\n\\nb']
    """
    if not text or not text.strip():
        return []
    if not enabled:
        return [text.strip()]
    parts = [part.strip() for part in _PARAGRAPH_RE.split(text)]
    return [part for part in parts if part]


async def send_reply_parts(
    text: str,
    send_one: Callable[[str], Awaitable[Any]],
    *,
    split: bool = True,
    delay_seconds: float = 0.0,
) -> int:
    """Send `text` via `send_one` as one message per part. Returns count sent.

    `send_one(part)` delivers a single text part (await-able); the consumer
    closes over the destination + transport (e.g.
    `lambda p: waha.send_text(chat_id, p)`). Per-part exceptions are logged
    and DO NOT halt the loop — partial delivery beats no delivery for chatbot
    replies. A `delay_seconds` gap separates consecutive parts (skipped after
    the last, and when `<= 0`).
    """
    parts = split_reply(text, enabled=split)
    if not parts:
        return 0
    sent = 0
    for idx, part in enumerate(parts):
        try:
            await send_one(part)
            sent += 1
        except Exception:
            logger.exception(
                "send_reply_parts: send failed (part %d/%d)", idx + 1, len(parts)
            )
            continue
        if idx + 1 < len(parts) and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
    return sent


def send_reply_parts_sync(
    text: str,
    send_one: Callable[[str], Any],
    *,
    split: bool = True,
    delay_seconds: float = 0.0,
) -> int:
    """Sync sibling of `send_reply_parts` for sync worker processors.

    Mirrors the `WahaClient.send_text` / `send_text_sync` dual-path shape —
    the documented wiring recipe's `ConversationProcessor` is synchronous
    (the worker loop uses `time.sleep`), so it binds `send_one` to
    `waha.send_text_sync` and gets the same multi-bubble emit without an
    event loop. Same partial-delivery + delay semantics.
    """
    parts = split_reply(text, enabled=split)
    if not parts:
        return 0
    sent = 0
    for idx, part in enumerate(parts):
        try:
            send_one(part)
            sent += 1
        except Exception:
            logger.exception(
                "send_reply_parts_sync: send failed (part %d/%d)",
                idx + 1,
                len(parts),
            )
            continue
        if idx + 1 < len(parts) and delay_seconds > 0:
            time.sleep(delay_seconds)
    return sent


__all__ = ["send_reply_parts", "send_reply_parts_sync", "split_reply"]
