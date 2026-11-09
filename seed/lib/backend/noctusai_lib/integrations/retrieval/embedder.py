"""Real embedder: the seed's shared `generate_embedding(s_batch)` — retrieval
never talks to a provider itself (one metered, key-resolved path)."""
from __future__ import annotations

from typing import Optional, Sequence

from noctusai_lib.integrations.llm import generate_embedding
from noctusai_lib.integrations.llm.embeddings import generate_embeddings_batch
from noctusai_lib.integrations.llm.client import get_llm_config


class LLMEmbedder:
    def __init__(self, *, model: Optional[str] = None, provider: Optional[str] = None) -> None:
        self._model = model
        self._provider = provider

    @property
    def model_id(self) -> str:
        cfg = get_llm_config()
        return f"{self._provider or cfg.default_provider}:{self._model or cfg.default_embedding_model}"

    async def embed_one(self, text: str, *, org_id: Optional[str] = None) -> list[float]:
        return await generate_embedding(text, model=self._model, provider=self._provider, org_id=org_id)

    async def embed_many(self, texts: Sequence[str], *, org_id: Optional[str] = None) -> list[list[float]]:
        return await generate_embeddings_batch(
            list(texts), model=self._model, provider=self._provider, org_id=org_id
        )
