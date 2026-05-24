"""In-memory deterministic fake SvgRenderAdapter for dev + tests.

Returns a valid-but-tiny placeholder PNG (no rasterizer dependency), so
consumer code that persists / uploads ``png_bytes`` works unchanged
under test. Records every call on ``calls`` (read-side test
introspection) per [[di-test-seam]] — never monkeypatch the real adapter.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from noctusai_lib.integrations.svg_render.types import (
    RenderedImage,
    SvgRenderInput,
)

# A known-valid 1×1 transparent PNG. Deterministic placeholder bytes the
# Fake returns regardless of input — valid enough that callers can hash /
# upload / write it without special-casing the Fake.
_PLACEHOLDER_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class FakeSvgRenderAdapter:
    """Deterministic in-memory SVG→PNG adapter.

    ``png_bytes`` is a fixed valid 1×1 PNG (callers must NOT assume the
    pixels mean anything — it is a sentinel). ``raw["svg_sha256"]`` is a
    stable hash of the input markup so tests can assert which SVG was
    rendered without flake. ``image_url`` is ``None`` unless an
    ``upload_url_resolver`` is supplied (then it returns a deterministic
    ``fake-svg-render.noctusai.local`` URL — the loud "not real" signal).
    """

    backend = "fake"

    def __init__(self, *, latency_ms: int = 0, upload_url_resolver=None) -> None:
        self._latency_ms = latency_ms
        self._upload = upload_url_resolver
        self.calls: list[dict[str, Any]] = []

    def render(
        self,
        request: SvgRenderInput,
        *,
        org_id: str | None = None,
    ) -> RenderedImage:
        digest = hashlib.sha256(request.svg_markup.encode("utf-8")).hexdigest()
        self.calls.append(
            {
                "svg_sha256": digest,
                "width": request.width,
                "height": request.height,
                "org_id": org_id,
                "request_id": request.request_id,
            }
        )
        image_url: str | None = None
        if self._upload is not None:
            image_url = (
                f"https://fake-svg-render.noctusai.local/{digest[:16]}.png"
            )
        return RenderedImage(
            png_bytes=_PLACEHOLDER_PNG_1X1,
            width=request.width or 1,
            height=request.height or 1,
            backend=self.backend,
            latency_ms=self._latency_ms,
            image_url=image_url,
            raw={"svg_sha256": digest, "request_id": request.request_id},
        )
