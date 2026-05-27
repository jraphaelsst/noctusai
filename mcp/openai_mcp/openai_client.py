"""Single seam for OpenAI SDK calls — every tool routes through here.

Tests patch `openai_mcp.openai_client.get_client` to return a fake,
exactly mirroring the github connector's `gh.run_gh` seam pattern.
Per-call settings (api_key, timeout) come from `get_settings()`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .settings import get_settings

logger = logging.getLogger(__name__)

_CLIENT: Optional[Any] = None  # cached lazy client


def get_client() -> Any:
    """Return a cached OpenAI client. Raises ImportError if SDK missing
    or RuntimeError if no API key configured."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "openai SDK not installed; add `openai>=1.0.0` to mcp/openai/requirements.txt"
        ) from exc
    settings = get_settings()
    if not settings.configured:
        raise RuntimeError(
            "OPENAI_API_KEY not configured — set the env var or add it to "
            "mcp/openai/.env / repo-root /.env"
        )
    _CLIENT = OpenAI(
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
    )
    return _CLIENT


def reset_client_for_testing() -> None:
    """Drop the cached client so a test can patch the OpenAI class fresh."""
    global _CLIENT
    _CLIENT = None


__all__ = ["get_client", "reset_client_for_testing"]
