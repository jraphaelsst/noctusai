"""`analyze_image`'s additive return shape — text plus whether it was cut off.

`analyze_image` returns a bare `str` for every existing caller, unchanged.
A caller that passes `return_metadata=True` gets a `VisionResult` instead:
the same text, plus the one thing a plain string cannot carry — whether the
PROVIDER says the reply was truncated before it finished.

WHY THIS EXISTS: a vision reply capped mid-page (Anthropic
`stop_reason == "max_tokens"`, OpenAI `finish_reason == "length"`, Gemini
`FinishReason.MAX_TOKENS`) reads EXACTLY like a complete answer to a
plain-string caller — measured live 2026-09-27, a dense page transcribed at
the default `max_tokens=4096` cut off mid-page and was still treated as a
finished transcription. `documents.transcription` exists to prevent a
half-read *document* from reporting success (page-count caps, per-page
routing); this type is the missing guard on a half-read *page*.

`truncated` is the ONE normalized field every caller should branch on —
computed per-provider from the vendor's own stop signal, never from
guessing at the text (an empty or garbled reply is not necessarily
truncated, and a long truncated reply is not necessarily empty or garbled).
`stop_reason` is the raw vendor value, kept for logs/debugging only.

This module has no imports beyond the stdlib on purpose: both `vision.py`
(the funnel) and every `providers/*.py` module (the implementations)
import it, and a heavier import here would risk the exact import cycle
this split avoids.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VisionResult:
    """`analyze_image(..., return_metadata=True)`'s return shape.

    See module docstring for why this exists and what `truncated` means.
    """

    text: str
    truncated: bool
    #: Raw vendor value (e.g. `"max_tokens"`, `"length"`, `"MAX_TOKENS"`) —
    #: for logs only. Compare `truncated`, never this, across providers.
    stop_reason: Optional[str] = None


__all__ = ["VisionResult"]
