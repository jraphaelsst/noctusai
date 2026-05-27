"""Pydantic In/Out schemas for the OpenAI connector MCP tools.

One In + one Out model per tool (vista/github/meta `types.py` shape).
The Out models are JSON-friendly mirrors of the OpenAI SDK responses —
each tool normalizes the SDK's typed objects into flat fields so the
host LLM gets a stable contract independent of openai-python versioning.

`openai_mcp` is the top-level package name (avoiding collision with the
`openai` pip package). Same sys.path trick as github/meta/google.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── openai.embed ────────────────────────────────────────────────────────

class EmbedInput(BaseModel):
    text: str = Field(..., description="Text to embed.")
    model: Optional[str] = Field(
        default=None,
        description="Override the embedding model (default: text-embedding-3-small).",
    )


class EmbedOutput(BaseModel):
    ok: bool
    model: str
    dimensions: int
    embedding: List[float]
    error: Optional[dict] = None


# ─── openai.chat ─────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="`system` | `user` | `assistant`.")
    content: str


class ChatInput(BaseModel):
    messages: List[ChatMessage] = Field(
        ..., description="Ordered chat messages — last must be `user`."
    )
    model: Optional[str] = Field(default=None)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)


class ChatOutput(BaseModel):
    ok: bool
    model: str
    content: str
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    error: Optional[dict] = None


# ─── openai.vision ───────────────────────────────────────────────────────

class VisionInput(BaseModel):
    question: str = Field(..., description="What to ask about the image.")
    image_url: Optional[str] = Field(
        default=None,
        description="HTTP/HTTPS image URL OR `data:image/...;base64,<...>` URI.",
    )
    image_path: Optional[str] = Field(
        default=None,
        description="Local file path; auto-loaded + base64-encoded.",
    )
    model: Optional[str] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None, gt=0)


class VisionOutput(BaseModel):
    ok: bool
    model: str
    content: str
    usage: Optional[dict] = None
    error: Optional[dict] = None


# ─── openai.transcribe ───────────────────────────────────────────────────

class TranscribeInput(BaseModel):
    audio_path: str = Field(..., description="Local path to an audio file.")
    model: Optional[str] = Field(default=None)
    language: Optional[str] = Field(
        default=None,
        description="ISO-639-1 code (e.g. 'en', 'pt'). Whisper auto-detects if omitted.",
    )


class TranscribeOutput(BaseModel):
    ok: bool
    model: str
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[dict] = None


# ─── openai.search.kb / openai.search.code ───────────────────────────────

class SearchInput(BaseModel):
    query: str = Field(..., description="Natural-language query.")
    top_k: int = Field(default=5, gt=0, le=50)
    min_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum cosine similarity — hits below are dropped.",
    )


class SearchHit(BaseModel):
    path: str
    symbol: Optional[str] = None
    chunk_text: str
    score: float


class SearchOutput(BaseModel):
    ok: bool
    query: str
    hits: List[SearchHit]
    error: Optional[dict] = None


# ─── openai.diagnostics.connection_status ────────────────────────────────

class DiagnosticsInput(BaseModel):
    """No inputs — pure ping."""
    pass


class DiagnosticsOutput(BaseModel):
    ok: bool
    configured: bool
    reachable: Optional[bool] = None
    default_chat_model: str
    default_embedding_model: str
    default_vision_model: str
    default_audio_model: str
    sdk_version: Optional[str] = None
    error: Optional[dict] = None
