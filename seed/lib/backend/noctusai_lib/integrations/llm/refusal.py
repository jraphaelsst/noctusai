"""Vision/text refusal detection + opt-in retry.

Lifted 2026-05-16 by `projects/social-wiring-absorption/` Wave 1.E5 from the
originating seed-workspace's `media_service._looks_like_refusal()` +
refusal-retry path (see SESSION-NOTES_chatbot-multichannel-2026-05-12 §4.5,
commit `72f70bf`).

**Why this exists.** LLMs refuse politely when a prompt is too narrow OR when
content falls outside the prompt's framing — a real-estate-narrow document
prompt made `gpt-4o` recite "Não foi possível extrair texto" instead of
reading a driver's license. The refusal is short and recites canned
"unable to" / "não consegui" markers rather than producing useful output.

Two surfaces:

- `looks_like_refusal(text)` — generic, language-agnostic (pt-BR + en)
  heuristic: short reply AND a refusal marker, OR a strong stand-alone
  refusal phrase. Pure function, no IO.
- `analyze_image_with_refusal_retry(...)` — opt-in wrapper around the seed
  `analyze_image` entry point. On a detected refusal it retries ONCE with a
  broadened retry prompt (default appends a generic "describe whatever IS
  visible" instruction). Returns the better of the two responses (the retry
  if it is no longer a refusal, else the original).

Refusal-retry is **opt-in** — callers that want the safety net pass
`retry=True` (or use the wrapper directly). The base `analyze_image` is
unchanged so existing consumers keep their exact behaviour.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from .vision import analyze_image

# Markers that, in a SHORT reply, indicate the model declined rather than
# answered. Lower-cased substring match. pt-BR first (primary product
# language), then English.
_REFUSAL_MARKERS: tuple[str, ...] = (
    "não foi possível",
    "nao foi possivel",
    "não consegui",
    "nao consegui",
    "não posso",
    "nao posso",
    "não é possível",
    "nao e possivel",
    "unable to",
    "i cannot",
    "i can't",
    "i'm unable",
    "i am unable",
    "sorry, i can",
    "cannot assist",
    "can't help with",
    "no text could be extracted",
    "no text was found",
)

# Phrases strong enough to be a refusal even in a longer reply.
_STRONG_REFUSAL_PHRASES: tuple[str, ...] = (
    "não foi possível extrair texto",
    "nao foi possivel extrair texto",
    "i'm sorry, i can't assist with that",
    "i cannot assist with that request",
    "i'm unable to process this image",
)

# A reply shorter than this (chars, stripped) that also contains a refusal
# marker is treated as a refusal. Real vision/text refusals are terse
# (a single canned sentence); a longer reply that mentions "unable to"
# for ONE field while listing many others is a legitimate answer, not a
# refusal — the strong-phrase list above catches the long-form declines.
_SHORT_REPLY_CHARS = 160


def looks_like_refusal(text: Optional[str]) -> bool:
    """Heuristic: does `text` read like an LLM declining rather than answering?

    Generic across pt-BR + English. Two triggers:
    1. A short reply (< ~240 chars) that contains any refusal marker.
    2. Any reply (length-independent) containing a strong stand-alone
       refusal phrase.

    Empty / whitespace-only text counts as a refusal (the model produced
    nothing usable).
    """
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()

    for phrase in _STRONG_REFUSAL_PHRASES:
        if phrase in lowered:
            return True

    if len(stripped) <= _SHORT_REPLY_CHARS:
        for marker in _REFUSAL_MARKERS:
            if marker in lowered:
                return True

    return False


_DEFAULT_RETRY_SUFFIX = (
    "\n\nDescribe and extract whatever IS visible in the image — classify the "
    "document/scene type first, then list every legible field or detail. Do "
    "not decline; if a value is unreadable, say so for that value only and "
    "continue with the rest."
)


async def analyze_image_with_refusal_retry(
    image: Union[bytes, str],
    prompt: str,
    *,
    retry_prompt: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """`analyze_image` with a single broadened retry on detected refusal.

    Calls `analyze_image` once. If `looks_like_refusal()` flags the result,
    retries ONCE with a broadened prompt (`retry_prompt` if given, else the
    original prompt + a generic "describe whatever is visible" suffix).

    Returns the retry result when it is no longer a refusal; otherwise
    returns the original result (best-effort — never raises just because the
    model declined). Provider/transport errors propagate unchanged.

    Opt-in: callers that don't want the retry keep using `analyze_image`.
    """
    first = await analyze_image(
        image,
        prompt,
        model=model,
        provider=provider,
        org_id=org_id,
        **kwargs,
    )
    if not looks_like_refusal(first):
        return first

    broadened = retry_prompt if retry_prompt is not None else prompt + _DEFAULT_RETRY_SUFFIX
    second = await analyze_image(
        image,
        broadened,
        model=model,
        provider=provider,
        org_id=org_id,
        **kwargs,
    )
    return second if not looks_like_refusal(second) else first


__all__ = ["looks_like_refusal", "analyze_image_with_refusal_retry"]
