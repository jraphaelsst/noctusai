"""OpenAI client construction + key resolution (lazy import).

Mirrors the spirit of noc's `llm/client.py` (resolve key → build provider). Kept
tiny: one cached AsyncOpenAI client built from settings.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config import get_settings


class LLMNotConfigured(RuntimeError):
    """OPENAI_API_KEY is missing — surfaced loudly, never silently degraded."""


@lru_cache
def get_client() -> Any:
    """Return a cached AsyncOpenAI client, or raise if no key is configured."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMNotConfigured(
            "OPENAI_API_KEY is not set. Add it to .env (or run with --fake)."
        )
    from openai import AsyncOpenAI  # lazy

    # max_retries: the SDK backs off on transient 429s (TPM throttling). Helps
    # batch jobs (resummarize / methodology) ride out per-minute rate limits.
    return AsyncOpenAI(api_key=settings.openai_api_key, max_retries=6)


__all__ = ["get_client", "LLMNotConfigured"]
