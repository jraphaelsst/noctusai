"""Narrative LLM call with deterministic fallback.

Wraps `chat_completion(...)` with the digest-narrative posture every
product converged on independently (temperature=0, max_tokens=600,
configurable cache, org_id threaded). Returns the caller's fallback
string + logs a warning when the LLM is unavailable, so a Resend send
or a render path never crashes from an upstream LLM outage.

The defaults here are not arbitrary — they match the unanimous shape
across the 4 narrative-using digest services as of 2026-04-30. Override
when the product's domain genuinely needs a different posture.
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.llm import chat_completion

logger = logging.getLogger(__name__)


async def narrative(
    *,
    system: str,
    user_prompt: str,
    model: str,
    cache: bool,
    org_id: Optional[str],
    fallback: str,
    max_tokens: int = 600,
    temperature: float = 0.0,
) -> str:
    """Generate a PT digest narrative; return `fallback` on LLM failure.

    Parameters:
        system: System prompt (per-product analyst voice).
        user_prompt: User message containing the formatted aggregates.
        model: LLM model id (e.g. `"gpt-4o-mini"`). Required — model
            choice is a meaningful product decision and the seed lib
            does not opine.
        cache: Whether to enable response caching. Pass `True` for
            anonymized/operational data + `temperature=0` (identical
            aggregates → identical narrative). Pass `False` for
            personal-narrative-adjacent content (LGPD posture).
        org_id: Threaded into `chat_completion` for org-level credential
            resolution + per-org spend accounting. May be None.
        fallback: Deterministic string to return when the LLM call
            raises any exception. Should embed the same numeric
            highlights the LLM would have used so the recipient still
            gets a usable digest.
        max_tokens: LLM max output tokens. Defaults to 600 — every
            adopter today uses this exact value.
        temperature: LLM sampling temperature. Defaults to 0.0 for
            deterministic output. Override only when the product wants
            stylistic variation in the narrative.

    Returns:
        The stripped LLM response on success, the `fallback` string on
        failure. Never raises.
    """
    try:
        text = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            cache=cache,
            org_id=org_id,
        )
        return text.strip()
    except Exception as exc:
        logger.warning(
            "noctusai_lib.domain.digest.narrative: LLM unavailable "
            "(%s); returning fallback (%d chars)",
            exc, len(fallback),
        )
        return fallback
