"""openai.embed — text → vector via OpenAI embeddings API."""
from __future__ import annotations

import logging
from typing import Any

from mcp.types import Tool

from _kit.errors import typed_error

from .. import openai_client
from ..settings import get_settings
from ..types import EmbedInput, EmbedOutput

logger = logging.getLogger(__name__)


async def handle_embed(args: dict) -> dict:
    try:
        inp = EmbedInput(**args)
    except Exception as exc:  # validation
        return {"error": typed_error(exc, status=422)}
    try:
        client = openai_client.get_client()
    except Exception as exc:
        return {"error": typed_error(exc, status=503)}
    model = inp.model or get_settings().default_embedding_model
    try:
        resp = client.embeddings.create(input=inp.text, model=model)
    except Exception as exc:
        return {"error": typed_error(exc, status=502)}
    vec = list(resp.data[0].embedding)
    return EmbedOutput(
        ok=True, model=model, dimensions=len(vec), embedding=vec,
    ).model_dump()


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="openai.embed",
            description=(
                "Generate an embedding vector for the given text via the OpenAI "
                "embeddings API (default model: text-embedding-3-small → 1536-D). "
                "Use for semantic-similarity comparisons or as a building block "
                "for custom RAG over content not in the noc KB/code index."
            ),
            inputSchema=EmbedInput.model_json_schema(),
        ),
    ]


HANDLERS: dict[str, Any] = {"openai.embed": handle_embed}


def register(server) -> None:
    """Compatibility hook — server uses HANDLERS + tool_descriptors()."""
    pass
