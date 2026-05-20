"""Image-generation adapter value objects + Protocol.

The seed surface for outbound image generation. Mirrors the
Protocol+Fake+Real+factory shape of `google_calendar` / `youtube` /
`google_drive` per `KB § PATTERNS/seed-fake-real-adapter.md`.

The Protocol is renderer-agnostic — concrete backends differ in
prompt-shape but the consumer contract is uniform: take a textual
``prompt`` and return a ``GeneratedImage`` with a URL the caller can
persist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ImagePromptInput:
    """Image-generation request payload.

    ``renderer`` is the renderer flavor the prompt was authored for
    (``"nano_banana"``, ``"galilai"``, ``"midjourney"``). Backends free
    to ignore it (a Gemini backend always renders w/ Gemini regardless
    of the renderer label) — but logging it back on the
    ``GeneratedImage`` makes the audit trail explicit.

    ``request_id`` is consumer-provided idempotency metadata. Backends
    do NOT translate it into wire-level idempotency today; it is
    surfaced back on ``GeneratedImage.raw`` for the caller to correlate.
    """

    prompt: str
    renderer: str = "nano_banana"
    aspect_ratio: str = "1:1"
    negative_prompt: str | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedImage:
    image_url: str
    renderer: str
    model: str
    latency_ms: int
    raw: dict[str, Any]


class ImageGenAdapter(Protocol):
    """Image-generation adapter contract. Concrete implementations:

    - ``FakeImageGenAdapter`` — deterministic in-memory; dev/test default.
    - ``GeminiImageGenAdapter`` — Google Gemini "Nano Banana"
      (``imagen-3.0`` / ``gemini-2.0-flash-exp:generate_images``).

    The factory ``get_image_gen_adapter(key_provider, ...)`` picks the
    concrete adapter from the key resolved for the org; ``None`` →
    ``FakeImageGenAdapter`` so the absence of configuration is loud (the
    Fake returns a fake-but-deterministic URL the caller can detect).
    """

    backend: str

    def generate(self, prompt: ImagePromptInput, *, org_id: str | None = None) -> GeneratedImage: ...
