"""Ports — every IO the engine performs, injected as one dataclass.

``PhotoEditingPorts`` is the single DI seam the handlers take. Tests build
it from fakes; a consumer (social-wiring W2) builds it from real
adapters. Nothing here imports a product.

Ports the seed already ships are consumed as-is:

- ``repo``        → ``repository.PhotoEditingRepository``
- ``jobs``        → ``noctusai_lib.domain.jobs.JobRepository``
- ``imaging``     → ``noctusai_lib.integrations.imaging.ImagingAdapter``
- ``image_edit``  → a factory returning ``integrations.image_edit.ImageEditAdapter``
  (the adapter's model is fixed at construction, and the model is per-org)
- ``fx``          → ``noctusai_lib.integrations.fx.FxRateAdapter``
- ``edit_quota``  → optional ``noctusai_lib.integrations.quota.QuotaTracker``

Ports defined here (no seed organ covers them yet): object storage for
photo bytes, a structured-LLM call that returns usage, and the
batch-ready notifier.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, Union, runtime_checkable

from noctusai_lib.domain.jobs import JobRepository, RetryPolicy
from noctusai_lib.domain.photo_editing.repository import PhotoEditingRepository
from noctusai_lib.integrations.fx import FxRateAdapter
from noctusai_lib.integrations.image_edit import (
    ImageEditAdapter,
    ImageEditNotConfigured,
    OpenAIImageEditAdapter,
)
from noctusai_lib.integrations.imaging import ImagingAdapter
from noctusai_lib.integrations.quota import QuotaTracker

# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------


@runtime_checkable
class PhotoStorage(Protocol):
    """Bytes in / bytes out by path (``naming.storage_path`` layout)."""

    async def get(self, path: str) -> bytes: ...
    async def put(self, path: str, data: bytes, *, content_type: str) -> None: ...
    async def delete(self, path: str) -> None: ...


class InMemoryPhotoStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def get(self, path: str) -> bytes:
        try:
            return self.objects[path][0]
        except KeyError:
            raise FileNotFoundError(path) from None

    async def put(self, path: str, data: bytes, *, content_type: str) -> None:
        self.objects[path] = (bytes(data), content_type)

    async def delete(self, path: str) -> None:
        self.objects.pop(path, None)


# ---------------------------------------------------------------------------
# Structured LLM call (vision + text), usage-returning
# ---------------------------------------------------------------------------

ImageInput = Union[bytes, str]


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    image_input_tokens: int | None = None
    image_output_tokens: int | None = None


@dataclass(frozen=True)
class StructuredResult:
    data: dict[str, Any]
    model: str
    #: ``None`` = the provider path did not surface usage to the caller.
    #: The engine records NO cost row in that case and says so in the
    #: photo event — it never fabricates a zero.
    usage: TokenUsage | None
    model_version: str | None = None


@runtime_checkable
class StructuredLlm(Protocol):
    async def analyze(
        self,
        *,
        images: Sequence[ImageInput],
        prompt: str,
        response_schema: dict[str, Any],
        model: str,
        org_id: str | None,
        schema_name: str,
    ) -> StructuredResult: ...


class LlmStructuredAdapter:
    """Real ``StructuredLlm`` over ``noctusai_lib.integrations.llm.analyze_images``.

    ``analyze_images`` accepts an empty image list (text-only structured
    call), so the rule proposer and note writer use the same path.

    NOC-REMEDIATE[llm-analyze-images-usage]: ``analyze_images`` returns only
    the parsed dict — the provider records usage to the process-wide
    ``LLMConfig.usage_sink`` but never hands it back — so this adapter
    returns ``usage=None`` and the engine cannot price vision calls into
    ``cost_ledger``. Fix at the organ: have ``analyze_images`` return (or
    expose) its usage, then populate ``TokenUsage`` here. — 2026-09-16
    """

    def __init__(self, *, provider: str = "openai") -> None:
        self._provider = provider

    async def analyze(
        self,
        *,
        images: Sequence[ImageInput],
        prompt: str,
        response_schema: dict[str, Any],
        model: str,
        org_id: str | None,
        schema_name: str,
    ) -> StructuredResult:
        from noctusai_lib.integrations.llm import analyze_images

        data = await analyze_images(
            list(images),
            prompt,
            response_schema=response_schema,
            model=model,
            provider=self._provider,
            org_id=org_id,
            schema_name=schema_name,
        )
        return StructuredResult(data=data, model=model, usage=None, model_version=None)


class FakeStructuredLlm:
    """Scripted ``StructuredLlm``.

    ``responses`` maps ``schema_name`` to either a dict (returned every
    time), a list of dicts/exceptions (consumed in order), or a callable
    ``(call) -> dict``. An exception instance in a list is RAISED — the
    DI way to exercise retry paths. Every call is recorded on ``calls``.
    """

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        *,
        usage: TokenUsage | None = TokenUsage(prompt_tokens=1000, completion_tokens=100, total_tokens=1100),
    ) -> None:
        self.responses: dict[str, Any] = dict(responses or {})
        self.usage = usage
        self.calls: list[dict[str, Any]] = []

    async def analyze(
        self,
        *,
        images: Sequence[ImageInput],
        prompt: str,
        response_schema: dict[str, Any],
        model: str,
        org_id: str | None,
        schema_name: str,
    ) -> StructuredResult:
        call = {
            "images": list(images),
            "prompt": prompt,
            "response_schema": response_schema,
            "model": model,
            "org_id": org_id,
            "schema_name": schema_name,
        }
        self.calls.append(call)
        if schema_name not in self.responses:
            raise LookupError(f"FakeStructuredLlm: no scripted response for {schema_name!r}")
        scripted = self.responses[schema_name]
        if isinstance(scripted, list):
            if not scripted:
                raise LookupError(f"FakeStructuredLlm: script for {schema_name!r} exhausted")
            scripted = scripted.pop(0)
        if isinstance(scripted, BaseException):
            raise scripted
        data = scripted(call) if callable(scripted) else dict(scripted)
        return StructuredResult(
            data=data, model=model, usage=self.usage, model_version=f"{model}-fake"
        )


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchReadyNotice:
    lote_id: str
    org_id: str
    criado_por: str
    nome: str
    total_fotos: int
    aguardando_decisao: int
    falhou: int


@runtime_checkable
class BatchReadyNotifier(Protocol):
    """Fan-out is the consumer's job (in-app + email + WhatsApp, opt-ins,
    the platform switch); the engine only says "this batch is ready"."""

    async def batch_ready(self, notice: BatchReadyNotice) -> None: ...


class RecordingNotifier:
    def __init__(self) -> None:
        self.notices: list[BatchReadyNotice] = []

    async def batch_ready(self, notice: BatchReadyNotice) -> None:
        self.notices.append(notice)


# ---------------------------------------------------------------------------
# Image-edit adapter factory
# ---------------------------------------------------------------------------

#: ``(org_id, model_id) -> ImageEditAdapter``
ImageEditFactory = Callable[[str, str], ImageEditAdapter]


def openai_image_edit_factory(key_provider: Callable[..., str | None]) -> ImageEditFactory:
    """Real factory: resolves the org's OpenAI key per call and REFUSES
    (``ImageEditNotConfigured``, fatal) when none resolves.

    Deliberately NOT ``get_image_edit_adapter``: that factory falls back to
    the Fake on a missing key, which is right for dev wiring but would let
    a production batch "succeed" with placeholder bytes.
    """

    def _factory(org_id: str, model_id: str) -> ImageEditAdapter:
        api_key = key_provider(org_id)
        if not api_key:
            raise ImageEditNotConfigured("openai")
        return OpenAIImageEditAdapter(api_key, model=model_id)

    return _factory


# ---------------------------------------------------------------------------
# Config + the ports bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhotoEditingConfig:
    """Engine tunables. Model defaults are the owner's plan §1 choices; the
    image-editor model has NO default — it is per org."""

    evaluator_model: str = "gpt-5.6-terra"
    style_guide_model: str = "gpt-5.6-sol"
    rule_proposer_model: str = "gpt-5.6-sol"
    note_writer_model: str = "gpt-5.6-luna"
    llm_provider: str = "openai"
    image_edit_provider: str = "openai"
    #: Plan §1: auto-retry ONCE, then ``falhou``.
    max_auto_retries: int = 1
    retry_backoff_seconds: float = 30.0
    guide_regen_debounce_seconds: int = 600
    rule_proposal_debounce_seconds: int = 1800
    #: Newest-first cap on pairs sent to the style-guide builder per run.
    max_reference_pairs_per_guide: int = 30
    #: PTAX is a Brazilian bulletin; "today" is the São Paulo date.
    fx_timezone: str = "America/Sao_Paulo"
    #: ``edit_quota`` key is ``f"{prefix}:{org_id}"``; the consumer registers it.
    edit_quota_key_prefix: str = "fotos.edit"
    #: Max rejection comments per rule-proposer call.
    max_rejections_per_proposal: int = 50

    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_retries=self.max_auto_retries,
            backoff_seconds=self.retry_backoff_seconds,
            backoff_multiplier=1.0,
            max_backoff_seconds=self.retry_backoff_seconds,
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PhotoEditingPorts:
    repo: PhotoEditingRepository
    jobs: JobRepository
    storage: PhotoStorage
    imaging: ImagingAdapter
    image_edit: ImageEditFactory
    llm: StructuredLlm
    fx: FxRateAdapter
    notifier: BatchReadyNotifier
    config: PhotoEditingConfig = field(default_factory=PhotoEditingConfig)
    clock: Callable[[], datetime] = _utcnow
    edit_quota: QuotaTracker | None = None

    def with_config(self, **changes: Any) -> "PhotoEditingPorts":
        return dataclasses.replace(self, config=dataclasses.replace(self.config, **changes))


__all__ = [
    "BatchReadyNotice",
    "BatchReadyNotifier",
    "FakeStructuredLlm",
    "ImageEditFactory",
    "ImageInput",
    "InMemoryPhotoStorage",
    "LlmStructuredAdapter",
    "PhotoEditingConfig",
    "PhotoEditingPorts",
    "PhotoStorage",
    "RecordingNotifier",
    "StructuredLlm",
    "StructuredResult",
    "TokenUsage",
    "openai_image_edit_factory",
]
