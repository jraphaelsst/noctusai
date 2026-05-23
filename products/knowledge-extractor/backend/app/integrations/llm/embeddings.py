"""Embedding generation via OpenAI.

Signature mirrors `noctusai_lib.integrations.llm.generate_embedding`:
    async generate_embedding(text, *, model=None) -> list[float]

On absorption: delete this file, import from noctusai_lib instead.
The caller (`kb_ingest.py`) stays unchanged — it only calls
`generate_embedding(text, model=model)`.

Default model: text-embedding-3-small → 1536 dimensions.
"""
from __future__ import annotations

from typing import Optional

from app.config import get_settings
from app.integrations.llm.client import get_client

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


async def generate_embedding(
    text: str,
    *,
    model: Optional[str] = None,
) -> list[float]:
    """Generate an embedding vector for *text* via OpenAI.

    Parameters
    ----------
    text:
        The text to embed.
    model:
        Override the embedding model.  Defaults to ``text-embedding-3-small``
        (1536 dimensions).

    Returns
    -------
    list[float]
        Embedding vector.  Length is model-dependent (1536 for the default).

    Raises
    ------
    LLMNotConfigured
        OPENAI_API_KEY is missing.
    openai.OpenAIError
        Downstream API error — not caught here; let it propagate loudly.
    """
    effective_model = model or DEFAULT_EMBEDDING_MODEL
    client = get_client()
    response = await client.embeddings.create(
        model=effective_model,
        input=text,
    )
    return response.data[0].embedding


__all__ = ["generate_embedding", "DEFAULT_EMBEDDING_MODEL"]
