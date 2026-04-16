"""
AI model wrappers for the seed agents.

Provides a unified interface for calling Claude API.
Gracefully degrades if API key is not set — returns None so callers
can skip AI-powered features without crashing.
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

_anthropic_client = None
_initialized = False


def _get_client():
    """Lazy-init the Anthropic client."""
    global _anthropic_client, _initialized
    if _initialized:
        return _anthropic_client

    _initialized = True
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — AI features disabled")
        return None

    try:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
        logger.info("Anthropic client initialized")
        return _anthropic_client
    except ImportError:
        logger.warning("anthropic package not installed — AI features disabled")
        return None


def ask_claude(
    prompt: str,
    system: str = "",
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Optional[str]:
    """Send a prompt to Claude and return the response text.

    Returns None if the API key is not set or the call fails.
    Callers should handle None gracefully.
    """
    client = _get_client()
    if not client:
        return None

    try:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        return response.content[0].text
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return None


def is_ai_available() -> bool:
    """Check if AI features are available (API key set + package installed)."""
    return _get_client() is not None
