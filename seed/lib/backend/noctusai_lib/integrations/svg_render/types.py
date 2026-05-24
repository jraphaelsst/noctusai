"""SVG→PNG render adapter value objects + Protocol.

The seed surface for **outbound** rasterization: take SVG markup (the
caller composes it — e.g. a brand-locked carousel slide) and return a
PNG. Mirrors the Protocol+Fake+Real+factory shape of ``image_gen`` /
``media`` per ``KB § PATTERNS/seed-fake-real-adapter.md``.

Sibling to ``integrations/media`` (which resolves *inbound* media →
text). This module is the *outbound* render direction: markup → pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class SvgRenderInput:
    """SVG→PNG render request payload.

    ``svg_markup`` is a complete, self-contained SVG document string (the
    caller is responsible for composing it — fonts referenced by
    ``font-family`` must be among the adapter's resolvable fonts).

    ``width`` / ``height`` override the output raster size in px. ``None``
    → use the SVG's intrinsic ``width``/``height`` / ``viewBox``.

    ``request_id`` is consumer-provided correlation metadata, surfaced
    back on ``RenderedImage.raw``.
    """

    svg_markup: str
    width: int | None = None
    height: int | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderedImage:
    """Rasterized PNG result.

    ``png_bytes`` is ALWAYS present (the rasterized PNG, valid even for
    the Fake — a deterministic placeholder). ``image_url`` is set only
    when an ``upload_url_resolver`` was supplied to the adapter (it
    uploaded ``png_bytes`` to durable storage and returned the URL);
    otherwise the caller persists ``png_bytes`` itself.
    """

    png_bytes: bytes
    width: int
    height: int
    backend: str
    latency_ms: int
    image_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SvgRenderAdapter(Protocol):
    """SVG→PNG render adapter contract. Concrete implementations:

    - ``FakeSvgRenderAdapter`` — deterministic placeholder PNG, no
      rasterizer dependency; dev/test default.
    - ``ResvgRenderAdapter`` — real rasterization via ``resvg-py``
      (self-contained Rust binding) with bundled OFL fonts.

    The factory ``get_svg_render_adapter(real=...)`` picks the concrete
    adapter. ``real=False`` (or the rasterizer being unavailable) keeps
    the Fake so the absence of the capability is loud, never silent.
    """

    backend: str

    def render(
        self, request: SvgRenderInput, *, org_id: str | None = None
    ) -> RenderedImage: ...
