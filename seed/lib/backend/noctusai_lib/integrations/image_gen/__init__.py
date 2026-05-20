"""Image-generation seed adapter — Protocol + Fake + Real(Gemini) + factory.

Lifted 2026-05-20 by ``media-creator-w2-4`` close-out per the
no-defer-mid-flight rule (the Phase-4 follow-up project that would
have filed this gap was REPLACED with the inline implementation here).

**What ships:**

- ``ImagePromptInput``, ``GeneratedImage`` value objects.
- ``ImageGenAdapter`` Protocol.
- ``FakeImageGenAdapter`` — deterministic in-memory adapter for
  dev + tests (default when no API key is configured).
- ``GeminiImageGenAdapter`` — Gemini "Nano Banana" backend
  (``imagen-3.0-generate-001`` default; ``gemini-2.0-flash-exp``
  override).
- ``get_image_gen_adapter()`` factory — picks Real when a key is
  resolved from the consumer's ``key_provider``, Fake otherwise.

**Consume recipe** (per ``KB § INTEGRATIONS/image-gen.md``):

    from noctusai_lib.integrations.image_gen import (
        ImagePromptInput,
        get_image_gen_adapter,
    )

    adapter = get_image_gen_adapter(
        key_provider=lambda org_id=None: resolve_credential("gemini_api_key", org_id),
        backend="gemini",
    )

    image = adapter.generate(
        ImagePromptInput(prompt=slide.prompt_nano_banana, renderer="nano_banana"),
        org_id=user.org_id,
    )

When ``key_provider`` returns ``None`` (org has not configured a
Gemini key), the factory returns ``FakeImageGenAdapter`` —
deterministic fake URL the caller can detect; never a silent no-op.
"""

from __future__ import annotations

from typing import Callable

from noctusai_lib.integrations.image_gen.fake_adapter import FakeImageGenAdapter
from noctusai_lib.integrations.image_gen.gemini_adapter import GeminiImageGenAdapter
from noctusai_lib.integrations.image_gen.types import (
    GeneratedImage,
    ImageGenAdapter,
    ImagePromptInput,
)

KeyProvider = Callable[..., str | None]


def get_image_gen_adapter(
    key_provider: KeyProvider | None = None,
    *,
    backend: str = "gemini",
    org_id: str | None = None,
    model: str | None = None,
    upload_url_resolver=None,
) -> ImageGenAdapter:
    """Return an image-gen adapter wired for the supplied key provider,
    or ``FakeImageGenAdapter`` when no key is configured.

    The factory is **never-faked-silently** per
    ``feedback_gated_capability_honesty``: when no key resolves, the
    Fake adapter returns a deterministic ``fake-image-gen.noctusai.local``
    URL the caller can detect — the absence is loud.

    - ``key_provider`` — same signature as the LLM ``key_provider``:
      ``(org_id=None) -> str | None``. ``None`` → always Fake.
    - ``backend`` — concrete real backend kind. ``"gemini"`` is the
      only v1 backend. Future: ``"openai"``, ``"stability"``,
      ``"replicate"``.
    - ``model`` — override the default model for the chosen backend.
    - ``upload_url_resolver`` — optional ``(bytes, ImagePromptInput) ->
      url`` callback that uploads returned image bytes to durable
      storage (e.g. Supabase Storage) and returns the persistent URL.
      When omitted the adapter falls back to inline ``data:`` URLs
      (good for dev / small images; replace in prod).
    """
    if key_provider is None:
        return FakeImageGenAdapter()

    api_key = key_provider(org_id) if org_id is not None else key_provider()
    if not api_key:
        return FakeImageGenAdapter()

    if backend == "gemini":
        kwargs: dict = {}
        if model is not None:
            kwargs["model"] = model
        if upload_url_resolver is not None:
            kwargs["upload_url_resolver"] = upload_url_resolver
        return GeminiImageGenAdapter(api_key, **kwargs)

    raise ValueError(
        f"Unsupported image-gen backend: {backend!r} (v1 ships 'gemini' only; "
        "open a follow-up project to add 'openai' / 'stability' / 'replicate')"
    )


__all__ = [
    "FakeImageGenAdapter",
    "GeminiImageGenAdapter",
    "GeneratedImage",
    "ImageGenAdapter",
    "ImagePromptInput",
    "KeyProvider",
    "get_image_gen_adapter",
]
