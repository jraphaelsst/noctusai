"""In-memory deterministic fake ImageGenAdapter for dev + tests.

Mirrors the real-backend response shape closely enough that consumer
code can swap fake/real transparently. Records every call on
``calls`` (read-side test introspection) per
[[feedback_no_monkeypatching_in_tests]].
"""

from __future__ import annotations

import hashlib
from typing import Any

from noctusai_lib.integrations.image_gen.types import (
    GeneratedImage,
    ImagePromptInput,
)


class FakeImageGenAdapter:
    """Deterministic in-memory image-gen adapter.

    The returned ``image_url`` is a stable hash of the prompt so tests
    can assert exact equality without flake. Callers should NOT fetch
    the URL — it points at a fixed sentinel host (``fake-image-gen.noctusai.local``).
    """

    backend = "fake"

    def __init__(self, *, latency_ms: int = 0) -> None:
        self._latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        prompt: ImagePromptInput,
        *,
        org_id: str | None = None,
    ) -> GeneratedImage:
        digest = hashlib.sha256(prompt.prompt.encode("utf-8")).hexdigest()[:16]
        url = (
            f"https://fake-image-gen.noctusai.local/{digest}.png"
            f"?renderer={prompt.renderer}&aspect={prompt.aspect_ratio}"
        )
        self.calls.append({
            "prompt": prompt.prompt,
            "renderer": prompt.renderer,
            "aspect_ratio": prompt.aspect_ratio,
            "org_id": org_id,
            "request_id": prompt.request_id,
        })
        return GeneratedImage(
            image_url=url,
            renderer=prompt.renderer,
            model="fake-image-gen",
            latency_ms=self._latency_ms,
            raw={"digest": digest, "request_id": prompt.request_id},
        )
