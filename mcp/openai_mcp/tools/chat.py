"""openai.chat — text → text completion via OpenAI chat API."""
from __future__ import annotations

import logging
from typing import Any

from mcp.types import Tool

from _kit.errors import typed_error

from .. import openai_client
from ..settings import get_settings
from ..types import ChatInput, ChatOutput

logger = logging.getLogger(__name__)


async def handle_chat(args: dict) -> dict:
    try:
        inp = ChatInput(**args)
    except Exception as exc:
        return {"error": typed_error(exc, status=422)}
    if not inp.messages or inp.messages[-1].role != "user":
        return {"error": typed_error(
            ValueError("messages must be non-empty and end with role=user"),
            status=422,
        )}
    try:
        client = openai_client.get_client()
    except Exception as exc:
        return {"error": typed_error(exc, status=503)}
    model = inp.model or get_settings().default_chat_model
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [m.model_dump() for m in inp.messages],
    }
    if inp.temperature is not None:
        kwargs["temperature"] = inp.temperature
    if inp.max_tokens is not None:
        kwargs["max_tokens"] = inp.max_tokens
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
        return {"error": typed_error(exc, status=502)}
    choice = resp.choices[0]
    usage = getattr(resp, "usage", None)
    return ChatOutput(
        ok=True,
        model=model,
        content=choice.message.content or "",
        finish_reason=choice.finish_reason,
        usage=usage.model_dump() if usage and hasattr(usage, "model_dump") else None,
    ).model_dump()


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="openai.chat",
            description=(
                "Send a chat-completion request to OpenAI (default model: "
                "gpt-4o-mini). Pass an ordered list of {role, content} messages; "
                "the last must be `role=user`. Returns the assistant's reply + "
                "finish_reason + usage (token counts). Use for tasks where the "
                "host LLM needs a second opinion from OpenAI directly."
            ),
            inputSchema=ChatInput.model_json_schema(),
        ),
    ]


HANDLERS: dict[str, Any] = {"openai.chat": handle_chat}


def register(server) -> None:
    pass
