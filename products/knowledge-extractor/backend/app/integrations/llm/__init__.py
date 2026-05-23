"""LLM seam — consumes `noctusai_lib.integrations.llm` (swapped on absorption 2026-05-23).

`transcribe_audio` / `chat_completion` / `generate_embedding` are the seed's
(credential + provider resolution auto-wired by `create_product_app`). This
module stays as the product-local import surface so consumers' call sites
(`from app.integrations.llm import …`) are unchanged — the local OpenAI
adapters (audio/chat/embeddings/client) were deleted; the seed is the source.
"""
from noctusai_lib.integrations.llm import (
    chat_completion,
    generate_embedding,
    transcribe_audio,
)

# KE's canonical embedding model (1536-dim) — kept as a product constant.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

__all__ = [
    "transcribe_audio",
    "chat_completion",
    "generate_embedding",
    "DEFAULT_EMBEDDING_MODEL",
]
