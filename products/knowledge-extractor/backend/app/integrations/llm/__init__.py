"""LLM seam — transcription + chat + embeddings, backed by OpenAI (lazy-imported).

Signatures mirror `noctusai_lib.integrations.llm` (`transcribe_audio`,
`chat_completion`, `generate_embedding`) so absorption swaps the import, not
the callers.
"""
from app.integrations.llm.audio import transcribe_audio
from app.integrations.llm.chat import chat_completion
from app.integrations.llm.client import LLMNotConfigured
from app.integrations.llm.embeddings import DEFAULT_EMBEDDING_MODEL, generate_embedding

__all__ = [
    "transcribe_audio",
    "chat_completion",
    "LLMNotConfigured",
    "generate_embedding",
    "DEFAULT_EMBEDDING_MODEL",
]
