"""Real-estate photo imaging seed adapter — Protocol + Fake + Real(Pillow) + factory.

Built 2026-09-16 (contract `edicao-fotos-contract`, Slice S3) for
outbound AI photo-editing: every photo an org uploads for an OpenAI
image-edit call needs the SAME pre/post pipeline regardless of which
product calls it — HEIC->JPEG, EXIF-orientation applied then dropped,
ICC->sRGB, GPS EXIF stripped (LGPD, not an optimization), Lanczos
resize back to the caller's original dimensions, an optional "Imagem
gerada com IA" watermark, and a consistent JPEG-quality-92 encode.

**What ships:**

- `NormalizedImage` value object.
- `ImagingAdapter` Protocol.
- `FakeImagingAdapter` — deterministic in-memory adapter; dev/test
  default, no real pixel processing.
- `RealImagingAdapter` — Pillow + pillow-heif backed. `Pillow` +
  `pillow-heif` are HARD seed dependencies (see `real_adapter.py`'s
  docstring for why this one is a direct top-level import rather than
  the lazy-import shape used for optional heavy deps elsewhere).
- `get_imaging_adapter()` factory.

**Consume recipe** (an OpenAI image-edit round-trip):

    from noctusai_lib.integrations.imaging import get_imaging_adapter
    from noctusai_lib.primitives.image_sizing import compute_edit_size

    adapter = get_imaging_adapter()
    normalized = adapter.normalize_for_edit(uploaded_bytes)
    edit_w, edit_h = compute_edit_size(normalized.width, normalized.height)
    edit_input = adapter.resize(normalized.jpeg_bytes, width=edit_w, height=edit_h)
    # ... send edit_input to the OpenAI image-edit call, get edited_bytes back ...
    restored = adapter.resize(edited_bytes, width=normalized.width, height=normalized.height)
    if is_virtual_staging:
        restored = adapter.apply_watermark(restored)

`apply_watermark` is a SEPARATE, opt-in step — the adapter has no
notion of "virtual staging"; the CALLER decides when to invoke it (the
watermark must apply ONLY to virtual-staging output, never plain
enhancement/retouch output).

Tests inject `FakeImagingAdapter` (or `real=False`) for orchestration
coverage, and exercise `RealImagingAdapter` directly for pixel-level
behaviour (HEIC conversion, GPS strip, ...) — never monkeypatch the
real adapter ([[di-test-seam]]).
"""

from __future__ import annotations

from noctusai_lib.integrations.imaging.fake_adapter import FakeImagingAdapter
from noctusai_lib.integrations.imaging.real_adapter import RealImagingAdapter
from noctusai_lib.integrations.imaging.types import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_WATERMARK_TEXT,
    ImagingAdapter,
    NormalizedImage,
    UnsupportedImageFormatError,
)


def get_imaging_adapter(*, real: bool = True) -> ImagingAdapter:
    """Return an imaging adapter.

    - `real=True` (default) -> `RealImagingAdapter`. No API key /
      network — Pillow + pillow-heif are hard seed dependencies, so
      construction never fails for a missing-dependency reason.
    - `real=False` -> `FakeImagingAdapter` (dev/test).
    """
    if not real:
        return FakeImagingAdapter()
    return RealImagingAdapter()


__all__ = [
    "DEFAULT_JPEG_QUALITY",
    "DEFAULT_WATERMARK_TEXT",
    "FakeImagingAdapter",
    "ImagingAdapter",
    "NormalizedImage",
    "RealImagingAdapter",
    "UnsupportedImageFormatError",
    "get_imaging_adapter",
]
