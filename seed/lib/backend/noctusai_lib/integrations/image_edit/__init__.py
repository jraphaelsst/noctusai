"""Image-edit seed adapter — Protocol + Fake + Real(OpenAI) + factory.

NEW sibling of `noctusai_lib.integrations.image_gen` (outbound image
GENERATION) for outbound image EDITING — `image_gen` is left completely
untouched by this module. Built 2026-09-16 (contract `edicao-fotos-contract`,
Slice S3b) for the real-estate photo-editing engine (S8, not yet built):
one combined OpenAI `images.edit` call per photo, all edit types the org
enabled folded into ONE prompt (the engine's job, not this adapter's).

**What ships:**

- `ImageEditRequest`, `ImageEditUsage`, `EditedImage`, `ImageEditResult`,
  `ImageEditCapabilities` value objects + `capabilities_for_model()`.
- `ImageEditAdapter` Protocol (async `edit`, sync `capabilities`).
- `FakeImageEditAdapter` — deterministic in-memory adapter for dev +
  tests (default when no API key is configured).
- `OpenAIImageEditAdapter` — real OpenAI Images API (`images.edit`)
  backend. Offline-testable via constructor-injected `client=...`
  (see `openai_adapter.py`'s module docstring) — NO live OpenAI call
  was possible during S3b (no credits on the account; see
  `projects/edicao-fotos/PROJECT.md` § 4c), so this path is verified
  against a scripted double only, never a live response.
- `get_image_edit_adapter()` factory — picks Real when a key is
  resolved from the consumer's `key_provider`, Fake otherwise.
- Typed retryable/fatal error taxonomy (`exceptions.py`):
  `ImageEditRetryableError` (429/5xx/timeout) vs `ImageEditFatalError`
  (content policy / invalid size / not-configured).

**NOT shipped (C8, deliberate):**

    NOC-REMEDIATE[image-edit-batch-c8]: batch submit/poll/fetch
    ("Econômico" speed mode) is not implemented. No catalog
    `image_edit` model is `supports_batch=True` as of 2026-09-16
    (`gpt-image-2` IS Batch-capable per vendor docs but has no
    published per-1M-token rate — see `NOC-REMEDIATE[llm-model-unpriced]`
    in `noctusai_lib/integrations/llm/models.py`), so a batch code path
    here would ship untested and unreachable by construction. Owner
    must either price `gpt-image-2` or cut Econômico from v1 (see
    `projects/edicao-fotos/PROJECT.md` C8) before this module grows
    batch methods.

**Consume recipe** (per `KB § INTEGRATIONS/image-edit.md`):

    from noctusai_lib.integrations.image_edit import (
        ImageEditRequest,
        get_image_edit_adapter,
    )
    from noctusai_lib.integrations.imaging import get_imaging_adapter
    from noctusai_lib.primitives.image_sizing import compute_edit_size

    imaging = get_imaging_adapter()
    normalized = imaging.normalize_for_edit(uploaded_bytes)
    edit_w, edit_h = compute_edit_size(normalized.width, normalized.height)
    edit_input = imaging.resize(normalized.jpeg_bytes, width=edit_w, height=edit_h)

    adapter = get_image_edit_adapter(
        key_provider=lambda org_id=None: resolve_credential("openai_api_key", org_id),
        model=org_settings.image_edit_model,  # no model configured -> ValueError; caller enforces "no model = blocked" (plan §1)
    )
    result = await adapter.edit(
        ImageEditRequest(images=(edit_input,), prompt=combined_prompt, size=f"{edit_w}x{edit_h}"),
        org_id=user.org_id,
    )

When `key_provider` returns `None` (no OpenAI key configured for the
org), the factory returns `FakeImageEditAdapter` — deterministic fake
bytes the caller can detect; never a silent no-op.
"""

from __future__ import annotations

from typing import Callable

from noctusai_lib.integrations.image_edit.exceptions import (
    ImageEditContentPolicyViolation,
    ImageEditError,
    ImageEditFatalError,
    ImageEditInvalidSize,
    ImageEditNotConfigured,
    ImageEditRateLimited,
    ImageEditRetryableError,
    ImageEditServerError,
    ImageEditTimeout,
)
from noctusai_lib.integrations.image_edit.fake_adapter import FakeImageEditAdapter
from noctusai_lib.integrations.image_edit.openai_adapter import OpenAIImageEditAdapter
from noctusai_lib.integrations.image_edit.types import (
    EditedImage,
    ImageEditAdapter,
    ImageEditCapabilities,
    ImageEditRequest,
    ImageEditResult,
    ImageEditUsage,
    capabilities_for_model,
)

KeyProvider = Callable[..., str | None]


def get_image_edit_adapter(
    key_provider: KeyProvider | None = None,
    *,
    backend: str = "openai",
    org_id: str | None = None,
    model: str | None = None,
) -> ImageEditAdapter:
    """Return an image-edit adapter wired for the supplied key provider,
    or `FakeImageEditAdapter` when no key is configured.

    Never-faked-silently, mirroring `image_gen.get_image_gen_adapter`:
    when no key resolves, the Fake adapter returns deterministic fake
    bytes the caller can detect — the absence is loud.

    - `key_provider` — same signature as the LLM `key_provider`:
      `(org_id=None) -> str | None`. `None` -> always Fake.
    - `backend` — concrete real backend kind. `"openai"` is the only v1
      backend.
    - `model` — override the default model for the chosen backend. The
      approved plan (§1 "Models") has NO built-in default for the image
      editor — "no model = batches blocked" — but this factory still
      applies `OpenAIImageEditAdapter`'s own constructor default when
      `model` is omitted; a caller enforcing the "no model configured"
      product rule must check the org's own settings BEFORE calling this
      factory, not rely on it to refuse.
    """
    if key_provider is None:
        return FakeImageEditAdapter()

    api_key = key_provider(org_id) if org_id is not None else key_provider()
    if not api_key:
        return FakeImageEditAdapter()

    if backend == "openai":
        kwargs: dict = {}
        if model is not None:
            kwargs["model"] = model
        return OpenAIImageEditAdapter(api_key, **kwargs)

    raise ValueError(
        f"Unsupported image-edit backend: {backend!r} (v1 ships 'openai' only)"
    )


__all__ = [
    "EditedImage",
    "FakeImageEditAdapter",
    "ImageEditAdapter",
    "ImageEditCapabilities",
    "ImageEditContentPolicyViolation",
    "ImageEditError",
    "ImageEditFatalError",
    "ImageEditInvalidSize",
    "ImageEditNotConfigured",
    "ImageEditRateLimited",
    "ImageEditRequest",
    "ImageEditResult",
    "ImageEditRetryableError",
    "ImageEditServerError",
    "ImageEditTimeout",
    "ImageEditUsage",
    "KeyProvider",
    "OpenAIImageEditAdapter",
    "capabilities_for_model",
    "get_image_edit_adapter",
]
