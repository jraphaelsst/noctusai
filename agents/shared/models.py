"""
AI model wrappers for the seed agents.

Uses OpenAI API as the primary provider.
Provides a unified interface — callers don't need to know which provider is used.
Gracefully degrades if API key is not set.
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env from repo root
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

_openai_client = None
_initialized = False


def _get_client():
    """Lazy-init the OpenAI client."""
    global _openai_client, _initialized
    if _initialized:
        return _openai_client

    _initialized = True
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set — AI features disabled")
        return None

    try:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized")
        return _openai_client
    except ImportError:
        logger.warning("openai package not installed — AI features disabled")
        return None


# Model mapping — callers use logical names, we resolve to OpenAI models
MODEL_MAP = {
    "fast": "gpt-4o-mini",
    "standard": "gpt-4o",
    "deep": "gpt-4o",
}


def ask_ai(
    prompt: str,
    system: str = "",
    model: str = "standard",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Optional[str]:
    """Send a prompt to the AI and return the response text.

    Args:
        prompt: The user prompt.
        system: System instruction.
        model: Logical model name — "fast" (mini), "standard" (4o), "deep" (4o).
        max_tokens: Max response tokens.
        temperature: Creativity (0.0 = deterministic, 1.0 = creative).

    Returns None if the API key is not set or the call fails.
    """
    client = _get_client()
    if not client:
        return None

    resolved_model = MODEL_MAP.get(model, model)

    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("OpenAI API error: %s", e)
        return None


# Backwards-compatible alias
ask_claude = ask_ai


def is_ai_available() -> bool:
    """Check if AI features are available (API key set + package installed)."""
    return _get_client() is not None
