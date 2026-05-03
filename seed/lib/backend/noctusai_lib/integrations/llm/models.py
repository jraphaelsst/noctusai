"""
Static model catalog per provider.

Consumed by:
  - UI model selector (filters by configured providers + kind)
  - `LLMConfig` defaults
  - Registry validation

Entries tagged `stub=True` are served by a stub Provider (Anthropic, Gemini).
The UI decorates them with a "STUB" badge; production deployments disable
stub providers at runtime via the `NOCTUSAI_ALLOW_STUB_PROVIDERS` env flag.

When Anthropic / Gemini become real:
  - Replace `stub=True` with `stub=False`
  - The model catalog entries themselves stay identical
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

ModelKind = Literal["chat", "embedding", "audio", "vision"]


@dataclass(frozen=True)
class ModelEntry:
    """One row of the catalog. Immutable so it's safely shareable."""

    id: str                  # Provider-native model ID (e.g. "gpt-4o-mini")
    label: str               # Human-readable label for the UI
    provider: str            # "openai" | "anthropic" | "gemini"
    kind: ModelKind
    stub: bool = False       # True when served by a stub provider
    description: str = ""
    # Cost per 1M tokens (USD) — used by `noctusai_lib.llm.usage.estimate_cost_usd`.
    # None = no published price / unknown. Zero cost recorded at lookup.
    cost_per_1m_input_tokens: Optional[float] = None
    cost_per_1m_output_tokens: Optional[float] = None


MODELS: Tuple[ModelEntry, ...] = (
    # ── OpenAI (real) ─────────────────────────────────────────────────
    ModelEntry(
        id="gpt-4o",
        label="GPT-4o",
        provider="openai",
        kind="chat",
        description="Flagship chat model — best accuracy and reasoning.",
        cost_per_1m_input_tokens=2.50,
        cost_per_1m_output_tokens=10.00,
    ),
    ModelEntry(
        id="gpt-4o-mini",
        label="GPT-4o mini",
        provider="openai",
        kind="chat",
        description="Cost-efficient chat model — good for high-volume use cases.",
        cost_per_1m_input_tokens=0.15,
        cost_per_1m_output_tokens=0.60,
    ),
    ModelEntry(
        id="gpt-4o",
        label="GPT-4o (Vision)",
        provider="openai",
        kind="vision",
        description="Multi-modal model — accepts images alongside text prompts.",
        cost_per_1m_input_tokens=2.50,
        cost_per_1m_output_tokens=10.00,
    ),
    ModelEntry(
        id="text-embedding-3-small",
        label="text-embedding-3-small",
        provider="openai",
        kind="embedding",
        description="1536-dim embeddings, cost-efficient.",
        cost_per_1m_input_tokens=0.02,
    ),
    ModelEntry(
        id="text-embedding-3-large",
        label="text-embedding-3-large",
        provider="openai",
        kind="embedding",
        description="3072-dim embeddings, higher retrieval accuracy.",
        cost_per_1m_input_tokens=0.13,
    ),
    ModelEntry(
        id="whisper-1",
        label="Whisper v1",
        provider="openai",
        kind="audio",
        description="Speech-to-text transcription.",
    ),

    # ── Anthropic (real — Phase 13) ──────────────────────────────────
    ModelEntry(
        id="claude-opus-4-7",
        label="Claude Opus 4.7",
        provider="anthropic",
        kind="chat",
        description="Anthropic flagship — highest accuracy.",
        cost_per_1m_input_tokens=15.00,
        cost_per_1m_output_tokens=75.00,
    ),
    ModelEntry(
        id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6",
        provider="anthropic",
        kind="chat",
        description="Anthropic mid-tier — balanced accuracy and cost.",
        cost_per_1m_input_tokens=3.00,
        cost_per_1m_output_tokens=15.00,
    ),
    ModelEntry(
        id="claude-haiku-4-5",
        label="Claude Haiku 4.5",
        provider="anthropic",
        kind="chat",
        description="Anthropic cost-tier — fast and cheap.",
        cost_per_1m_input_tokens=0.80,
        cost_per_1m_output_tokens=4.00,
    ),
    ModelEntry(
        id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6 (Vision)",
        provider="anthropic",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=3.00,
        cost_per_1m_output_tokens=15.00,
    ),

    # ── Gemini (real — Phase 14) ─────────────────────────────────────
    ModelEntry(
        id="gemini-1.5-pro",
        label="Gemini 1.5 Pro",
        provider="gemini",
        kind="chat",
        description="Google flagship — 2M context window.",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=5.00,
    ),
    ModelEntry(
        id="gemini-1.5-flash",
        label="Gemini 1.5 Flash",
        provider="gemini",
        kind="chat",
        description="Google cost-tier — fast, 1M context.",
        cost_per_1m_input_tokens=0.075,
        cost_per_1m_output_tokens=0.30,
    ),
    ModelEntry(
        id="gemini-1.5-pro",
        label="Gemini 1.5 Pro (Vision)",
        provider="gemini",
        kind="vision",
        description="Multimodal — accepts image + audio input parts.",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=5.00,
    ),
    ModelEntry(
        id="gemini-1.5-pro",
        label="Gemini 1.5 Pro (Audio)",
        provider="gemini",
        kind="audio",
        description="Multimodal audio input — alternative to OpenAI Whisper.",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=5.00,
    ),
    ModelEntry(
        id="models/text-embedding-004",
        label="text-embedding-004",
        provider="gemini",
        kind="embedding",
        description="Google embedding model — 768 dims.",
        cost_per_1m_input_tokens=0.0,
    ),
)


def models_for(provider: str, kind: Optional[ModelKind] = None) -> list[ModelEntry]:
    """Return the catalog entries for a provider, optionally filtered by kind."""
    return [m for m in MODELS if m.provider == provider and (kind is None or m.kind == kind)]


def all_providers() -> list[str]:
    """All distinct provider names present in the catalog (sorted)."""
    return sorted({m.provider for m in MODELS})


def is_stub_model(provider: str, model_id: str) -> bool:
    """True if the given (provider, model_id) pair is served by a stub."""
    for m in MODELS:
        if m.provider == provider and m.id == model_id:
            return m.stub
    return False
