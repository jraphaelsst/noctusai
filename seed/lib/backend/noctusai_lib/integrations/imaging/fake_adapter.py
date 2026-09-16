"""In-memory deterministic fake ImagingAdapter for dev + tests.

Returns a valid-but-tiny placeholder JPEG (no Pillow pixel work), so
consumer/orchestration code that persists / uploads / re-opens the
returned bytes works unchanged under test. Records every call on
`calls` (read-side test introspection) per [[di-test-seam]] — never
monkeypatch the real adapter.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from noctusai_lib.integrations.imaging.types import (
    DEFAULT_WATERMARK_TEXT,
    NormalizedImage,
)

# A known-valid tiny (2x2, mid-grey) baseline JPEG — deterministic
# placeholder bytes every Fake method returns regardless of input,
# valid enough that callers can hash / upload / re-open it without
# special-casing the Fake. Generated once via
# `Image.new("RGB", (2, 2), (128, 128, 128)).save(buf, format="JPEG", quality=50)`
# — not a checked-in arbitrary binary, the exact recipe is reproducible.
_PLACEHOLDER_JPEG_2X2 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0o"
    "OjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8a"
    "Gi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2Nj"
    "Y2NjY2P/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQF"
    "BgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEI"
    "I0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNk"
    "ZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLD"
    "xMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEB"
    "AQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJB"
    "UQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH"
    "SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaan"
    "qKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oA"
    "DAMBAAIRAxEAPwAooooA/9k="
)


class FakeImagingAdapter:
    """Deterministic in-memory imaging adapter — no Pillow work.

    Every method returns `_PLACEHOLDER_JPEG_2X2` regardless of input.
    Useful for exercising ORCHESTRATION code (a service that calls
    `normalize_for_edit` -> `resize` -> optionally `apply_watermark`)
    without needing real image bytes or paying real CPU cost. Real
    pixel behaviour (HEIC conversion, EXIF/ICC/GPS stripping, Lanczos
    resize, watermark rendering) is exercised against
    `RealImagingAdapter` directly.
    """

    backend = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def normalize_for_edit(self, image_bytes: bytes) -> NormalizedImage:
        digest = hashlib.sha256(image_bytes).hexdigest()
        self.calls.append({"op": "normalize_for_edit", "input_sha256": digest})
        return NormalizedImage(
            jpeg_bytes=_PLACEHOLDER_JPEG_2X2,
            width=2,
            height=2,
            source_format="FAKE",
            converted=True,
            gps_stripped=False,
        )

    def resize(self, image_bytes: bytes, *, width: int, height: int) -> bytes:
        digest = hashlib.sha256(image_bytes).hexdigest()
        self.calls.append(
            {"op": "resize", "input_sha256": digest, "width": width, "height": height}
        )
        return _PLACEHOLDER_JPEG_2X2

    def apply_watermark(
        self, image_bytes: bytes, *, text: str = DEFAULT_WATERMARK_TEXT
    ) -> bytes:
        digest = hashlib.sha256(image_bytes).hexdigest()
        self.calls.append(
            {"op": "apply_watermark", "input_sha256": digest, "text": text}
        )
        return _PLACEHOLDER_JPEG_2X2
