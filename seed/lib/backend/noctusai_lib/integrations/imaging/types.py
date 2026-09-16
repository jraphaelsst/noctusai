"""Real-estate photo imaging value objects + Protocol.

Built for outbound AI photo-editing (virtual staging / photo
enhancement, contract `edicao-fotos-contract` Slice S3): every photo an
org uploads for an OpenAI image-edit call needs the SAME pre/post
pipeline regardless of which product calls it. Mirrors the
Protocol+Fake+Real+factory shape of `svg_render` / `image_gen` per
`KB § PATTERNS/backend/seed-fake-real-adapter.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Text overlay applied by `apply_watermark` when the caller does not
#: supply its own — the ONLY copy this module hardcodes. Callers decide
#: WHEN to call `apply_watermark` (virtual-staging output only, per the
#: task); the adapter itself has no notion of "virtual staging".
DEFAULT_WATERMARK_TEXT = "Imagem gerada com IA"

#: JPEG quality every adapter method encodes its output at.
DEFAULT_JPEG_QUALITY = 92


class UnsupportedImageFormatError(ValueError):
    """Raised when input bytes cannot be decoded as an image, or a
    decoded image cannot be normalized (corrupt/truncated data, a
    format Pillow does not understand even with `pillow-heif`
    registered).

    Never silently swallowed and never a silent pass-through of the
    original bytes — an adapter method either produces a valid
    transformed image or raises this. See CLAUDE.md `no_silent_errors`.
    """


@dataclass(frozen=True)
class NormalizedImage:
    """Result of `ImagingAdapter.normalize_for_edit`.

    `jpeg_bytes` is always JPEG-encoded at `DEFAULT_JPEG_QUALITY`. ANY
    non-JPEG source (HEIC/PNG/WEBP/...) is converted. EXIF orientation
    is applied to the pixels, then the tag is dropped (never carried
    into the output — carrying it forward after the pixels are already
    physically rotated would double-rotate downstream viewers that also
    honour it). An ICC profile is converted to sRGB, then dropped for
    the same reason. EVERY EXIF tag — including GPS — is stripped from
    the output; `gps_stripped` records whether the SOURCE actually
    carried a GPS tag, so callers can audit that the strip had a real
    effect on real input, not just a no-op on GPS-less input. Stripping
    GPS is an LGPD requirement, not an optimization.
    """

    jpeg_bytes: bytes
    width: int
    height: int
    source_format: str
    converted: bool
    gps_stripped: bool


class ImagingAdapter(Protocol):
    """Real-estate photo imaging adapter contract. Concrete
    implementations:

    - `FakeImagingAdapter` — deterministic in-memory; dev/test default,
      no real pixel processing.
    - `RealImagingAdapter` — Pillow + pillow-heif backed.

    The factory `get_imaging_adapter(real=...)` picks the concrete
    adapter. Unlike most seed IO adapters this one needs no API key —
    it is local CPU work — so the factory switches on a plain `real`
    flag (mirrors `svg_render.get_svg_render_adapter`), not a
    `key_provider`.
    """

    backend: str

    def normalize_for_edit(self, image_bytes: bytes) -> NormalizedImage: ...

    def resize(self, image_bytes: bytes, *, width: int, height: int) -> bytes: ...

    def apply_watermark(
        self, image_bytes: bytes, *, text: str = DEFAULT_WATERMARK_TEXT
    ) -> bytes: ...
