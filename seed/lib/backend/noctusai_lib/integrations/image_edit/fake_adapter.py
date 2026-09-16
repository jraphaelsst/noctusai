"""In-memory deterministic FakeImageEditAdapter for dev + tests.

Mirrors `image_gen.fake_adapter.FakeImageGenAdapter`'s shape closely
enough that consumer code can swap fake/real transparently. Records
every call on `calls` / `batch_calls` (read-side test introspection) per
[[feedback_no_monkeypatching_in_tests]] — no monkeypatching needed to
assert what a caller sent.

Batch (Econômico): a submitted batch stays ``in_progress`` for
``batch_pending_polls`` polls, then turns ``completed``; its results are the
same deterministic output ``edit`` would produce, except for the
``custom_id``s listed in ``batch_item_errors`` (carried as typed errors).
``set_batch_state`` forces a terminal failure state (``expired`` /
``failed`` / ``cancelled``) — every item then comes back as an error, the
way OpenAI reports unfinished requests of an expired batch.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
from collections.abc import Iterable, Sequence
from typing import Any

from noctusai_lib.integrations.image_edit.exceptions import (
    ImageEditBatchNotFound,
    ImageEditBatchNotReady,
    ImageEditBatchUnsupported,
    ImageEditTimeout,
)
from noctusai_lib.integrations.image_edit.types import (
    BatchEditItem,
    BatchItemResult,
    BatchPollResult,
    BatchState,
    BatchSubmission,
    EditedImage,
    ImageEditCapabilities,
    ImageEditRequest,
    ImageEditResult,
    ImageEditUsage,
)
from noctusai_lib.integrations.image_edit import types as _types


class FakeImageEditAdapter:
    """Deterministic in-memory image-edit adapter.

    The returned image bytes are a short, stable, ASCII-prefixed blob
    derived from a hash of the prompt + first input image — same
    "detectable fake, not a real image" contract as
    `FakeImageGenAdapter`. Callers should NOT attempt to decode it as a
    real image. Usage counts are fabricated-but-deterministic (never
    `None`) so downstream cost math has something to sum in tests
    without special-casing the fake.

    `capabilities()` delegates to the SAME catalog-driven lookup the
    Real adapter uses (`capabilities_for_model`) rather than inventing
    its own answer — a Fake that disagreed with production here would
    validate the Econômico UI lock against a truth production never
    sees. ``batch_models`` is the one explicit, constructor-declared
    exception: a test that needs a batch-capable model while the catalog
    has none names it here (the Fake then reports it ``known`` and
    ``supports_batch``) — a visible arrangement, never a silent default.

    ``model`` is the model this adapter instance stands for (the Real
    adapter's model is fixed at construction too); the batch gate checks
    ``capabilities(model)``.
    """

    backend = "fake"

    def __init__(
        self,
        *,
        latency_ms: int = 0,
        model: str = "fake-image-edit",
        batch_models: Iterable[str] = (),
        batch_pending_polls: int = 0,
        batch_item_errors: dict[str, Exception] | None = None,
    ) -> None:
        if batch_pending_polls < 0:
            raise ValueError("batch_pending_polls must be >= 0")
        self._latency_ms = latency_ms
        self.model = model
        self.batch_models = frozenset(batch_models)
        self.batch_pending_polls = batch_pending_polls
        self.batch_item_errors: dict[str, Exception] = dict(batch_item_errors or {})
        self.calls: list[dict[str, Any]] = []
        self.batch_calls: list[dict[str, Any]] = []
        self.batches: dict[str, dict[str, Any]] = {}
        self._batch_seq = itertools.count(1)

    # --- synchronous edit ------------------------------------------------
    def _result_for(self, request: ImageEditRequest) -> ImageEditResult:
        digest = hashlib.sha256(
            request.prompt.encode("utf-8") + request.images[0]
        ).hexdigest()[:16]
        fake_bytes = f"FAKE-IMAGE-EDIT:{digest}".encode("ascii")
        images = tuple(
            EditedImage(image_bytes=fake_bytes, format="png") for _ in range(request.n)
        )
        word_count = len(request.prompt.split())
        image_in_tokens = len(request.images) * 100
        image_out_tokens = request.n * 100
        return ImageEditResult(
            images=images,
            model=self.model,
            usage=ImageEditUsage(
                prompt_tokens=word_count,
                image_input_tokens=image_in_tokens,
                image_output_tokens=image_out_tokens,
                total_tokens=word_count + image_in_tokens + image_out_tokens,
            ),
            latency_ms=self._latency_ms,
            raw={"digest": digest, "request_id": request.request_id},
        )

    async def edit(
        self,
        request: ImageEditRequest,
        *,
        org_id: str | None = None,
    ) -> ImageEditResult:
        self.calls.append({
            "prompt": request.prompt,
            "size": request.size,
            "n_images_in": len(request.images),
            "n_out": request.n,
            "has_mask": request.mask is not None,
            "org_id": org_id,
            "request_id": request.request_id,
        })
        return self._result_for(request)

    def capabilities(self, model: str) -> ImageEditCapabilities:
        if model in self.batch_models:
            return ImageEditCapabilities(model=model, supports_batch=True, known=True)
        return _types.capabilities_for_model(model)

    # --- batch (Econômico) -----------------------------------------------
    async def submit_batch(
        self,
        items: Sequence[BatchEditItem],
        *,
        org_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BatchSubmission:
        if not self.capabilities(self.model).supports_batch:
            raise ImageEditBatchUnsupported(
                f"model {self.model} does not support batch", provider="fake"
            )
        if not items:
            raise ValueError("submit_batch needs at least one item")
        ids = [item.custom_id for item in items]
        if len(set(ids)) != len(ids):
            raise ValueError("submit_batch: duplicate custom_id")
        batch_id = f"fake-batch-{next(self._batch_seq)}"
        self.batches[batch_id] = {
            "items": tuple(items),
            "polls_left": self.batch_pending_polls,
            "state": BatchState.VALIDATING,
            "org_id": org_id,
            "metadata": dict(metadata or {}),
        }
        self.batch_calls.append({
            "op": "submit",
            "batch_id": batch_id,
            "custom_ids": ids,
            "prompts": [item.request.prompt for item in items],
            "sizes": [item.request.size for item in items],
            "org_id": org_id,
            "metadata": dict(metadata or {}),
        })
        return BatchSubmission(
            batch_id=batch_id,
            model=self.model,
            item_count=len(items),
            state=BatchState.VALIDATING,
            input_file_id=f"fake-input-{batch_id}",
        )

    def set_batch_state(self, batch_id: str, state: BatchState) -> None:
        """Test arrangement: force a batch into ``state`` (no more polls)."""
        batch = self._batch(batch_id)
        batch["state"] = BatchState(state)
        batch["polls_left"] = 0

    def _batch(self, batch_id: str) -> dict[str, Any]:
        try:
            return self.batches[batch_id]
        except KeyError:
            raise ImageEditBatchNotFound(f"unknown batch {batch_id}", provider="fake") from None

    async def poll_batch(self, batch_id: str, *, org_id: str | None = None) -> BatchPollResult:
        batch = self._batch(batch_id)
        self.batch_calls.append({"op": "poll", "batch_id": batch_id, "org_id": org_id})
        state: BatchState = batch["state"]
        if not state.is_terminal:
            if batch["polls_left"] > 0:
                batch["polls_left"] -= 1
                state = BatchState.IN_PROGRESS
            else:
                state = BatchState.COMPLETED
            batch["state"] = state
        total = len(batch["items"])
        failed = sum(1 for i in batch["items"] if i.custom_id in self.batch_item_errors)
        done = state is BatchState.COMPLETED
        return BatchPollResult(
            batch_id=batch_id,
            state=state,
            output_file_id=f"fake-output-{batch_id}" if done else None,
            error_file_id=f"fake-errors-{batch_id}" if done and failed else None,
            total=total,
            completed=total - failed if done else 0,
            failed=failed if done else 0,
        )

    async def fetch_batch_results(
        self, batch_id: str, *, org_id: str | None = None
    ) -> tuple[BatchItemResult, ...]:
        batch = self._batch(batch_id)
        self.batch_calls.append({"op": "fetch", "batch_id": batch_id, "org_id": org_id})
        state: BatchState = batch["state"]
        if not state.is_terminal:
            raise ImageEditBatchNotReady(f"batch {batch_id} is {state.value}", provider="fake")
        out: list[BatchItemResult] = []
        for item in batch["items"]:
            if state is not BatchState.COMPLETED:
                error: Exception = ImageEditTimeout(
                    f"batch_{state.value}: request not processed", provider="fake"
                )
                out.append(BatchItemResult(custom_id=item.custom_id, error=error))
            elif item.custom_id in self.batch_item_errors:
                out.append(
                    BatchItemResult(
                        custom_id=item.custom_id, error=self.batch_item_errors[item.custom_id]
                    )
                )
            else:
                result = self._result_for(item.request)
                result = dataclasses.replace(
                    result, raw={**result.raw, "batch_id": batch_id, "custom_id": item.custom_id}
                )
                out.append(BatchItemResult(custom_id=item.custom_id, result=result))
        return tuple(out)


__all__ = ["FakeImageEditAdapter"]
