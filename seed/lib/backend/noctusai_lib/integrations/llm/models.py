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

ModelKind = Literal["chat", "embedding", "audio", "vision", "image_edit"]


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
    # `image_edit` models bill THREE independent rates, not two:
    # `cost_per_1m_input_tokens` above prices the TEXT instruction tokens;
    # these two price the reference-image tokens and the generated/edited
    # image tokens respectively — each at a different published rate. None
    # = no published price for that leg; `estimate_cost_usd` treats a
    # missing rate as a zero contribution for that component only (same
    # silent-zero-for-unknown contract the text rates already have).
    cost_per_1m_image_input_tokens: Optional[float] = None
    cost_per_1m_image_output_tokens: Optional[float] = None
    # True when the vendor's async Batch API (submit-a-job, ~24h turnaround,
    # ~50% discount) is available for this model. This is NOT the same
    # concept as `generate_embeddings_batch` (a single synchronous
    # multi-input round-trip) — that batches many REQUESTS into one HTTP
    # call; this flag is about the separate async discounted job queue.
    # Load-bearing beyond pricing: it drives a UI capability gate (e.g. an
    # "Econômico" speed mode is disabled when the org's selected image model
    # has no Batch support). Conservative default — unknown/unverified
    # support is False, never silently advertised as available.
    supports_batch: bool = False
    # Provider-native dated snapshot suffix (e.g. "-2026-09-08") when the
    # vendor pins this catalog id to a specific dated release distinct from
    # a rolling alias. None when the catalog `id` already IS the pinned
    # snapshot (no separate rolling alias exists).
    snapshot: Optional[str] = None
    # UI recommendation tag: "performance" (quality-first) | "economico"
    # (cost-first) | None. Pure presentation — never a capability gate.
    tag_performance: Optional[str] = None


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
    #: The OCR pin for the `openai` rung (`documents/transcription.py::
    #: OCR_MODELS`). It was reachable in production while unpriced, which is
    #: the same silent-zero the Anthropic block below documents — found by
    #: `mcp/noctusai/tests/test_model_catalog_pricing.py`, not by anyone
    #: noticing a suspiciously cheap month. (That guard lives in the toolkit
    #: tests rather than beside the lib because CI runs no pytest over
    #: `seed/lib/backend/tests/` at all — its own header explains why.)
    ModelEntry(
        id="gpt-4.1-mini",
        label="GPT-4.1 mini",
        provider="openai",
        kind="chat",
        description="OpenAI cost-tier — the document-transcription pin.",
        cost_per_1m_input_tokens=0.40,
        cost_per_1m_output_tokens=1.60,
    ),
    ModelEntry(
        id="gpt-4.1-mini",
        label="GPT-4.1 mini (Vision)",
        provider="openai",
        kind="vision",
        description="Multi-modal — reads rasterized document pages.",
        cost_per_1m_input_tokens=0.40,
        cost_per_1m_output_tokens=1.60,
    ),
    ModelEntry(
        id="whisper-1",
        label="Whisper v1",
        provider="openai",
        kind="audio",
        description="Speech-to-text transcription.",
    ),

    # ── OpenAI (image-edit — Phase S2, verified 2026-09-15) ───────────
    #: Both 2.5-generation edit models share the same published rates.
    #: `supports_batch=False` — neither has async Batch API availability
    #: yet, so the "Econômico" speed-mode UI lock stays engaged for them.
    #: The older `gpt-image-2` (and prior) generation IS Batch-capable (per
    #: vendor docs, 50% discount) but no published per-1M-token rate was
    #: available to verify at the 2026-09-15 pass — a guessed number in a
    #: billing catalog is worse than a declared gap, so it is NOT a static
    #: row. Resolved 2026-09-16 (edicao-fotos W8, C8) through the runtime
    #: overlay instead: a platform admin enters the rate + the batch flag in
    #: the product UI (`catalog_overrides.ModelCatalogStore`), and an
    #: unpriced model is refused at selection and at submission
    #: (`is_priced`) rather than billed at a silent $0.
    ModelEntry(
        id="gpt-image-2.5-sunburst",
        label="GPT Image 2.5 Sunburst",
        provider="openai",
        kind="image_edit",
        description="Image editing — multi-turn, reference-image aware.",
        snapshot="-2026-09-08",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_image_input_tokens=8.00,
        cost_per_1m_image_output_tokens=30.00,
        supports_batch=False,
    ),
    ModelEntry(
        id="gpt-image-2.5-flare",
        label="GPT Image 2.5 Flare",
        provider="openai",
        kind="image_edit",
        description="Image editing — 2.5-generation sibling of Sunburst.",
        snapshot="-2026-09-08",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_image_input_tokens=8.00,
        cost_per_1m_image_output_tokens=30.00,
        supports_batch=False,
    ),

    # ── OpenAI (text + vision — Phase S2, verified 2026-09-15) ────────
    ModelEntry(
        id="gpt-6-astra",
        label="GPT-6 Astra",
        provider="openai",
        kind="chat",
        description="OpenAI flagship — next-generation reasoning tier.",
        cost_per_1m_input_tokens=10.00,
        cost_per_1m_output_tokens=50.00,
    ),
    ModelEntry(
        id="gpt-6-astra",
        label="GPT-6 Astra (Vision)",
        provider="openai",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=10.00,
        cost_per_1m_output_tokens=50.00,
    ),
    ModelEntry(
        id="gpt-5.6-sol",
        label="GPT-5.6 Sol",
        provider="openai",
        kind="chat",
        description="OpenAI mid-tier — balanced accuracy and cost.",
        cost_per_1m_input_tokens=4.00,
        cost_per_1m_output_tokens=20.00,
    ),
    ModelEntry(
        id="gpt-5.6-sol",
        label="GPT-5.6 Sol (Vision)",
        provider="openai",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=4.00,
        cost_per_1m_output_tokens=20.00,
    ),
    ModelEntry(
        id="gpt-5.6-terra",
        label="GPT-5.6 Terra",
        provider="openai",
        kind="chat",
        description="OpenAI cost-tier — high-volume use cases.",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=12.00,
    ),
    ModelEntry(
        id="gpt-5.6-terra",
        label="GPT-5.6 Terra (Vision)",
        provider="openai",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=12.00,
    ),
    ModelEntry(
        id="gpt-5.6-luna",
        label="GPT-5.6 Luna",
        provider="openai",
        kind="chat",
        description="OpenAI economy tier — fastest and cheapest.",
        cost_per_1m_input_tokens=0.20,
        cost_per_1m_output_tokens=1.20,
    ),
    ModelEntry(
        id="gpt-5.6-luna",
        label="GPT-5.6 Luna (Vision)",
        provider="openai",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=0.20,
        cost_per_1m_output_tokens=1.20,
    ),

    # ── Anthropic (real — Phase 13) ──────────────────────────────────
    #: 🔴 REGISTERED BECAUSE AN UNREGISTERED MODEL COSTS ZERO, SILENTLY.
    #:
    #: `usage.estimate_cost_usd` looks the model up here and returns 0.0 when
    #: it finds nothing — so a model the fleet actually calls but never
    #: registered writes `cost_estimate_usd=0` on every row, and
    #: `budget.compute_spend_usd` (which sums exactly that column) reports an
    #: org as having spent nothing. The budget guardrail then never fires.
    #: That is not a missing feature, it is a disabled safety net that still
    #: looks armed.
    #:
    #: `claude-opus-5` was the model `documents.providers.OCR_MODELS` pinned
    #: for the `anthropic` rung until 2026-09-22 (now Haiku 4.5, measured), so
    #: it was reachable in production before it was priced here.
    ModelEntry(
        id="claude-opus-5",
        label="Claude Opus 5",
        provider="anthropic",
        kind="chat",
        description="Anthropic flagship — highest accuracy, 1M context.",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_output_tokens=25.00,
    ),
    ModelEntry(
        id="claude-opus-5",
        label="Claude Opus 5 (Vision)",
        provider="anthropic",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_output_tokens=25.00,
    ),
    #: Registered for the same reason, one step down: the mid-tier swap
    #: between the old Opus pin and the current Haiku pin, so a consumer
    #: moving a document pin up must not land on the zero-cost path either.
    ModelEntry(
        id="claude-sonnet-5",
        label="Claude Sonnet 5",
        provider="anthropic",
        kind="chat",
        description="Anthropic mid-tier — balanced accuracy and cost, 1M context.",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=10.00,
    ),
    ModelEntry(
        id="claude-sonnet-5",
        label="Claude Sonnet 5 (Vision)",
        provider="anthropic",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=10.00,
    ),
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
    #: $1 / $5 per 1M — Anthropic's list price for Haiku 4.5. It was
    #: registered at $0.80 / $4.00 (Haiku 3.5's price), under-counting every
    #: call by 20%; that mattered little while nothing hot called it, and a lot
    #: once `documents.providers` pinned it on both document-read rungs.
    ModelEntry(
        id="claude-haiku-4-5",
        label="Claude Haiku 4.5",
        provider="anthropic",
        kind="chat",
        description="Anthropic cost-tier — fast and cheap.",
        cost_per_1m_input_tokens=1.00,
        cost_per_1m_output_tokens=5.00,
    ),
    #: The document-transcription pin (`documents.providers.OCR_MODELS`) —
    #: a vision call, so it needs its own vision-kind row like its siblings.
    ModelEntry(
        id="claude-haiku-4-5",
        label="Claude Haiku 4.5 (Vision)",
        provider="anthropic",
        kind="vision",
        description="Same model used for vision — accepts image content blocks.",
        cost_per_1m_input_tokens=1.00,
        cost_per_1m_output_tokens=5.00,
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
    ModelEntry(
        id="gemini-embedding-001",
        label="gemini-embedding-001",
        provider="gemini",
        kind="embedding",
        # Matryoshka: natively 3072, truncatable to 1536 / 768 via
        # `outputDimensionality`. The permutas layer asks for 1536 because
        # that is the column width.
        description="Google embedding model — 3072 dims, truncatable (1536/768).",
        cost_per_1m_input_tokens=0.15,
    ),
)


def base_models_for(provider: str, kind: Optional[ModelKind] = None) -> list[ModelEntry]:
    """The STATIC catalog rows only — no runtime overlay. Admin surfaces use
    it to show what a row looked like before an operator changed it."""
    return [m for m in MODELS if m.provider == provider and (kind is None or m.kind == kind)]


def models_for(provider: str, kind: Optional[ModelKind] = None) -> list[ModelEntry]:
    """Return the EFFECTIVE catalog entries for a provider, optionally
    filtered by kind: the static rows with the process-wide operator overlay
    applied (`catalog_overrides`) — an overridden row takes the operator's
    prices/flags, a disabled row disappears, an operator-added row appears.
    Every catalog consumer (pricing, `capabilities_for_model`, cost records)
    goes through here, so one overlay reaches all of them."""
    from .catalog_overrides import apply_overlay

    return apply_overlay(base_models_for(provider, kind), provider, kind)


def is_priced(entry: ModelEntry) -> bool:
    """True when every leg this model's calls bill has a rate.

    `image_edit`: text-in + image-in + image-out (an edit always sends a
    prompt and an image and returns an image). `chat`/`vision`: in + out.
    `embedding`: in. Anything else (audio) is never considered priced —
    there is no token rate that describes it."""
    rates: tuple[Optional[float], ...]
    if entry.kind == "image_edit":
        rates = (
            entry.cost_per_1m_input_tokens,
            entry.cost_per_1m_image_input_tokens,
            entry.cost_per_1m_image_output_tokens,
        )
    elif entry.kind in ("chat", "vision"):
        rates = (entry.cost_per_1m_input_tokens, entry.cost_per_1m_output_tokens)
    elif entry.kind == "embedding":
        rates = (entry.cost_per_1m_input_tokens,)
    else:
        return False
    return all(r is not None for r in rates)


def all_providers() -> list[str]:
    """All distinct provider names present in the catalog (sorted)."""
    return sorted({m.provider for m in MODELS})


def is_stub_model(provider: str, model_id: str) -> bool:
    """True if the given (provider, model_id) pair is served by a stub."""
    for m in MODELS:
        if m.provider == provider and m.id == model_id:
            return m.stub
    return False
