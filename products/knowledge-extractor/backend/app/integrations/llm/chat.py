"""Chat completion via OpenAI.

Signature mirrors `noctusai_lib.integrations.llm.chat_completion(messages, *,
model=None, ...)`.
"""
from __future__ import annotations

from typing import Any, Optional

from app.config import get_settings
from app.integrations.llm.client import get_client


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    **kwargs: Any,
) -> str:
    """Run a chat completion; return the assistant's text content."""
    settings = get_settings()
    client = get_client()
    resp = await client.chat.completions.create(
        model=model or settings.summary_model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    return resp.choices[0].message.content or ""


__all__ = ["chat_completion"]
