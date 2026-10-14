"""Assistant text → WhatsApp bubbles (``reply.partes``, contract §3.1).

Paragraphs (blank-line separated) become separate bubbles, in order — the
natural way a person types on WhatsApp. A paragraph longer than the WhatsApp
text limit is split on whitespace. Empty / whitespace-only output is NO bubble
(``partes: []`` = stay silent). Pure, no IO.
"""
from __future__ import annotations

import re

__all__ = ["BUBBLE_MAX_CHARS", "split_into_bubbles"]

#: WhatsApp's text-message ceiling is 4096; stay under it.
BUBBLE_MAX_CHARS = 4000

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _chunk(paragraph: str, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]
    out: list[str] = []
    rest = paragraph
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


def split_into_bubbles(text: str | None, *, limit: int = BUBBLE_MAX_CHARS) -> list[str]:
    if not text or not text.strip():
        return []
    parts: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text.replace("\r\n", "\n").strip()):
        cleaned = paragraph.strip()
        if cleaned:
            parts.extend(_chunk(cleaned, limit))
    return parts
