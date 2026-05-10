"""Shared tokenizer helper for MCP tools — N=2 absorption target.

Surfaces a single canonical `count_tokens(text: str) -> int` plus the
underlying `get_default_encoder()` so callers can reuse the same encoder
across many strings (batch reuse — important for project ledger writes
where a single record stamps 3+ files).

**Why this module exists.** Phase 1 of `project-history-ledger` would
have made `tiktoken.get_encoding('cl100k_base')` the second call site
(first being `cost_evaluation.count_tokens_in_text`). N=2 triggers the
recurrence rule — triage time. Decision: **formalize** by extracting a
shared helper here so the encoder choice + fallback cascade lives in
one place. `cost_evaluation` delegates to this module; `history.py`
imports the same helper. A future tokenizer swap (e.g. Anthropic's
official tokenizer) lands in this file and propagates automatically.

**Why `mcp/noctusai/tools/_tokens.py` and not `noctusai_lib.tokens`.**
`tiktoken` is an MCP-toolkit-only dependency today (not used by any
product). Pushing it down to `noctusai_lib` would force every
product-backend venv to install it. The MCP-scoped destination
matches the actual consumer surface. Revisit if a product backend
ever needs token counting.

**Tokenizer cascade.** Same shape `cost_evaluation` already shipped:
1. `tiktoken` (default `cl100k_base`) when importable.
2. `chars / 4` approximation as last resort (never wrong by more than
   ~25% on English markdown).

The cascade reports which tokenizer ran via a label string —
callers that record results MUST keep the label alongside the count
(two records with the same `tokens` but different labels are NOT
comparable).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIKTOKEN_ENCODING = "cl100k_base"
APPROX_LABEL = "approximate-chars-per-4"


def get_default_encoder(encoding_name: str = DEFAULT_TIKTOKEN_ENCODING) -> Any | None:
    """Return a tiktoken encoder if available; ``None`` otherwise.

    Returns ``None`` (not raises) when ``tiktoken`` isn't installed
    or the named encoding cannot be loaded — callers must check.

    Args:
        encoding_name: tiktoken encoding name. ``cl100k_base`` is the
            GPT-4-family default; ``o200k_base`` is the GPT-4o family.
            ``cl100k_base`` is documented as "close enough" to Claude's
            BPE for cost-efficiency comparisons (see
            `KB § PATTERNS/accept-with-rationale.md` if migrated later).
    """
    try:
        import tiktoken  # type: ignore
    except ImportError:
        return None
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception as e:  # pragma: no cover — tiktoken edge case
        # tiktoken raises various errors for unknown encodings / corrupted
        # download caches. Don't swallow silently — log and fall back.
        logger.debug("tiktoken.get_encoding(%r) failed: %s", encoding_name, e)
        return None


def count_tokens_in_text(text: str, encoder: Any | None = None) -> tuple[int, str]:
    """Count tokens in ``text``. Returns ``(token_count, tokenizer_label)``.

    Args:
        text: input string. Empty string returns ``(0, label)``.
        encoder: optional pre-loaded tiktoken encoder for batch reuse
            (avoid re-loading the encoding tables per call). If ``None``,
            the helper tries to load the default encoder.

    Returns:
        ``(count, label)`` where ``label`` is one of:
          - ``"tiktoken-<encoding_name>"`` when tiktoken ran
          - ``APPROX_LABEL`` when the chars/4 fallback ran
    """
    if encoder is not None:
        try:
            return len(encoder.encode(text)), f"tiktoken-{encoder.name}"
        except Exception as e:  # pragma: no cover — tiktoken edge case
            # Don't swallow — log + fall through to fresh encoder + then approx.
            logger.debug("tiktoken encode failed on supplied encoder, retrying: %s", e)

    enc = get_default_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text)), f"tiktoken-{enc.name}"
        except Exception as e:  # pragma: no cover — tiktoken edge case
            logger.debug("tiktoken encode failed on default encoder, falling back: %s", e)

    # Fallback — chars/4 (English-markdown rule of thumb).
    chars = len(text)
    return (max(1, chars // 4) if chars else 0), APPROX_LABEL


def count_tokens(text: str) -> int:
    """Convenience: just the count, no label. Uses the default cascade.

    Use this when the caller doesn't care which tokenizer ran (e.g. for
    a one-shot count). For multi-string batch counts, prefer
    ``count_tokens_in_text`` with a shared encoder.
    """
    count, _label = count_tokens_in_text(text)
    return count


__all__ = [
    "DEFAULT_TIKTOKEN_ENCODING",
    "APPROX_LABEL",
    "get_default_encoder",
    "count_tokens_in_text",
    "count_tokens",
]
