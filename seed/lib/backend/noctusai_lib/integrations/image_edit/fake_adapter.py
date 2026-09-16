"""In-memory deterministic FakeImageEditAdapter for dev + tests.

Mirrors `image_gen.fake_adapter.FakeImageGenAdapter`'s shape closely
enough that consumer code can swap fake/real transparently. Records
every call on `calls` (read-side test introspection) per
[[feedback_no_monkeypatching_in_tests]] — no monkeypatching needed to
assert what a caller sent.
"""

from __future__ import annotations

import hashlib
from typing import Any

from noctusai_lib.integrations.image_edit.types import (
    EditedImage,
    ImageEditCapabilities,
    ImageEditRequest,
    ImageEditResult,
    ImageEditUsage,
    capabilities_for_model,
)


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
    sees.
    """

    backend = "fake"

    def __init__(self, *, latency_ms: int = 0) -> None:
        self._latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    async def edit(
        self,
        request: ImageEditRequest,
        *,
        org_id: str | None = None,
    ) -> ImageEditResult:
        digest = hashlib.sha256(
            request.prompt.encode("utf-8") + request.images[0]
        ).hexdigest()[:16]
        self.calls.append({
            "prompt": request.prompt,
            "size": request.size,
            "n_images_in": len(request.images),
            "n_out": request.n,
            "has_mask": request.mask is not None,
            "org_id": org_id,
            "request_id": request.request_id,
        })
        fake_bytes = f"FAKE-IMAGE-EDIT:{digest}".encode("ascii")
        images = tuple(
            EditedImage(image_bytes=fake_bytes, format="png") for _ in range(request.n)
        )
        word_count = len(request.prompt.split())
        image_in_tokens = len(request.images) * 100
        image_out_tokens = request.n * 100
        return ImageEditResult(
            images=images,
            model="fake-image-edit",
            usage=ImageEditUsage(
                prompt_tokens=word_count,
                image_input_tokens=image_in_tokens,
                image_output_tokens=image_out_tokens,
                total_tokens=word_count + image_in_tokens + image_out_tokens,
            ),
            latency_ms=self._latency_ms,
            raw={"digest": digest, "request_id": request.request_id},
        )

    def capabilities(self, model: str) -> ImageEditCapabilities:
        return capabilities_for_model(model)
