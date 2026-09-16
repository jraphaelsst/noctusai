"""Image-edit adapter value objects + Protocol.

NEW sibling of `noctusai_lib.integrations.image_gen` (outbound image
GENERATION) for outbound image EDITING — one photo (plus optional extra
reference images) in, an edited photo out, via a single combined OpenAI
edit call. Built for real-estate photo editing (contract
`edicao-fotos-contract`, Slice S3b): a photo already normalized by
`noctusai_lib.integrations.imaging` and sized by
`noctusai_lib.primitives.image_sizing.compute_edit_size` is the expected
input shape, but this module has no import-time dependency on either —
it accepts raw bytes and trusts the caller already ran that pipeline.

Mirrors the Protocol+Fake+Real+factory shape of `image_gen` per
`KB § PATTERNS/backend/seed-fake-real-adapter.md`. `image_gen` itself is
left completely untouched — this is a NEW sibling, not a refactor of it.

Async, unlike `image_gen`'s sync Protocol — this module is consumed from
`noctusai_lib.domain.jobs.worker`'s async job handlers (the same reason
`integrations.outbound_webhook.OutboundWebhookSender.send` is async), and
its Real backend uses OpenAI's `AsyncOpenAI` client.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ImageEditRequest:
    """Image-edit request payload.

    ``images`` is one or more input images (already normalized/sized by
    the caller — this module does no pixel processing of its own). The
    FIRST entry is the primary photo being edited; any additional
    entries are reference images the model may use (multi-image edit).
    ``mask`` is an optional PNG with alpha=0 marking editable regions
    (OpenAI mask-edit semantics); omitted means "edit the whole image".

    ``size`` is the OpenAI Images API size string, e.g. ``"1536x1024"``
    — callers compute the numeric size via
    ``noctusai_lib.primitives.image_sizing.compute_edit_size`` and pass
    the STRING form here (this module has no dependency on that
    primitive; it does not import or call it itself).

    ``request_id`` is consumer-provided idempotency metadata, mirroring
    ``ImagePromptInput.request_id`` in `image_gen` — surfaced back on
    ``ImageEditResult.raw`` for the caller to correlate, never
    translated into wire-level idempotency by this module.
    """

    images: tuple[bytes, ...]
    prompt: str
    size: str
    mask: bytes | None = None
    n: int = 1
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.images:
            raise ValueError("ImageEditRequest.images must contain at least one image")
        if self.n < 1:
            raise ValueError(f"ImageEditRequest.n must be >= 1, got {self.n}")


@dataclass(frozen=True)
class ImageEditUsage:
    """Token accounting for one edit call — the SAME 4-field shape
    `noctusai_lib.integrations.llm.usage.UsageEvent` carries
    (`prompt_tokens` / `image_input_tokens` / `image_output_tokens` /
    `total_tokens`), so a caller can feed this straight into
    `record_usage(...)` / build a `UsageEvent` without reshaping.
    ``None`` on any field means the provider did not report that count
    (never fabricated as 0 — see CLAUDE.md `no_silent_errors`).
    """

    prompt_tokens: int | None = None
    image_input_tokens: int | None = None
    image_output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class EditedImage:
    """One output image. ``format`` is whatever the provider actually
    returned (``"png"`` for the OpenAI Images API) — never assumed to be
    JPEG; callers that need JPEG re-encode via
    `noctusai_lib.integrations.imaging`."""

    image_bytes: bytes
    format: str


@dataclass(frozen=True)
class ImageEditResult:
    """Result of ``ImageEditAdapter.edit``.

    ``model`` echoes the model actually invoked (the adapter's
    configured model, not a value read off the request — this Protocol
    has no per-request model override; see `openai_adapter.py`'s
    constructor). A separate provider-reported dated snapshot is NOT
    captured here: the OpenAI Images API response does not expose one
    the way chat completions exposes `response.model` (verified against
    the SDK's `ImagesResponse` shape at S3b write time — no live account
    to re-check against, see the module docstring in `openai_adapter.py`).
    """

    images: tuple[EditedImage, ...]
    model: str
    usage: ImageEditUsage
    latency_ms: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class ImageEditCapabilities:
    """Static per-model capability flags, driven ENTIRELY by the
    `noctusai_lib.integrations.llm.models` catalog — this module never
    hardcodes a second copy of what a model supports. Obtained via
    :func:`capabilities_for_model` (used identically by both
    `FakeImageEditAdapter.capabilities` and
    `OpenAIImageEditAdapter.capabilities`, so a consumer gets the SAME
    answer regardless of which adapter it tests against).

    ``supports_batch`` mirrors `ModelEntry.supports_batch` exactly: the
    "Econômico" (Batch API) capability gate. Per `projects/edicao-fotos/
    PROJECT.md` C8: as of 2026-09-16 NO catalog `image_edit` row sets
    this True, so every known model reports `supports_batch=False` —
    correct behaviour, not a bug in this module. See the
    `NOC-REMEDIATE[llm-model-unpriced]` marker in
    `noctusai_lib/integrations/llm/models.py`.
    """

    model: str
    supports_batch: bool
    known: bool  # False when `model` is not a catalog `image_edit` entry


# ---------------------------------------------------------------------------
# Batch (Econômico) value objects — W4, resolves image-edit-batch-c8
# ---------------------------------------------------------------------------


class BatchState(str, Enum):
    """Provider batch lifecycle, mirroring the OpenAI Batch API ``status``
    vocabulary one-to-one (``validating`` → ``in_progress`` →
    ``finalizing`` → ``completed``; or ``failed`` / ``expired`` /
    ``cancelling`` → ``cancelled``)."""

    VALIDATING = "validating"
    IN_PROGRESS = "in_progress"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_BATCH_STATES


_TERMINAL_BATCH_STATES = frozenset(
    {BatchState.COMPLETED, BatchState.FAILED, BatchState.EXPIRED, BatchState.CANCELLED}
)


@dataclass(frozen=True)
class BatchEditItem:
    """One edit inside a provider batch. ``custom_id`` is the caller's
    correlation key — echoed back on the matching ``BatchItemResult`` and
    unique within one batch (the provider rejects duplicates)."""

    custom_id: str
    request: ImageEditRequest

    def __post_init__(self) -> None:
        if not self.custom_id:
            raise ValueError("BatchEditItem.custom_id must be non-empty")


@dataclass(frozen=True)
class BatchSubmission:
    """Receipt of ``submit_batch``. ``batch_id`` is the provider's id —
    the only handle ``poll_batch`` / ``fetch_batch_results`` need."""

    batch_id: str
    model: str
    item_count: int
    state: BatchState
    input_file_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchPollResult:
    """One ``poll_batch`` observation. ``output_file_id`` /
    ``error_file_id`` are set once the provider has produced them (an
    ``expired`` batch may still carry partial output)."""

    batch_id: str
    state: BatchState
    output_file_id: str | None = None
    error_file_id: str | None = None
    total: int | None = None
    completed: int | None = None
    failed: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchItemResult:
    """Outcome of one ``BatchEditItem``: exactly one of ``result`` /
    ``error`` is set. ``error`` is a typed ``ImageEditError`` instance
    (carried, not raised) so the caller branches on ``error.retryable``
    exactly as it does for a synchronous ``edit``. ``usage`` inside
    ``result`` is the provider's raw (undiscounted) token count — the
    batch discount is a pricing concern of the caller."""

    custom_id: str
    result: ImageEditResult | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise ValueError("BatchItemResult needs exactly one of result / error")

    @property
    def ok(self) -> bool:
        return self.result is not None


def capabilities_for_model(model: str) -> ImageEditCapabilities:
    """Catalog-driven capability lookup — the ONLY implementation of
    "does `model` support Batch/Econômico" this module has.

    Imports `noctusai_lib.integrations.llm.models` lazily to avoid a
    module-load-order dependency between the two integration packages
    (mirrors the lazy `from .models import models_for` already used
    inside `llm.usage.estimate_cost_usd`).
    """
    from noctusai_lib.integrations.llm.models import models_for

    for entry in models_for("openai", "image_edit"):
        if entry.id == model:
            return ImageEditCapabilities(model=model, supports_batch=entry.supports_batch, known=True)
    return ImageEditCapabilities(model=model, supports_batch=False, known=False)


@runtime_checkable
class ImageEditAdapter(Protocol):
    """Image-edit adapter contract. Concrete implementations:

    - ``FakeImageEditAdapter`` — deterministic in-memory; dev/test default.
    - ``OpenAIImageEditAdapter`` — OpenAI Images API (`images.edit`).

    The factory ``get_image_edit_adapter(key_provider, ...)`` picks the
    concrete adapter from the key resolved for the org; ``None`` ->
    ``FakeImageEditAdapter`` so absence of configuration is loud (the
    Fake returns deterministic-but-fake bytes the caller can detect).

    Batch (Econômico speed-mode, W4): ``submit_batch`` → ``poll_batch`` →
    ``fetch_batch_results``. Gated by ``capabilities(model).supports_batch``
    — an adapter REFUSES (``ImageEditBatchUnsupported``, fatal) to submit
    for a model the catalog does not mark batch-capable.
    """

    backend: str

    async def edit(
        self, request: ImageEditRequest, *, org_id: str | None = None
    ) -> ImageEditResult: ...

    def capabilities(self, model: str) -> ImageEditCapabilities: ...

    async def submit_batch(
        self,
        items: Sequence[BatchEditItem],
        *,
        org_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BatchSubmission: ...

    async def poll_batch(
        self, batch_id: str, *, org_id: str | None = None
    ) -> BatchPollResult: ...

    async def fetch_batch_results(
        self, batch_id: str, *, org_id: str | None = None
    ) -> tuple[BatchItemResult, ...]: ...
