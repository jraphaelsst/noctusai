"""SVG→PNG render seed primitive — Protocol + Fake + Real(resvg) + factory.

Built 2026-05-24 — the final residual of the media-creator absorption. media-creator rendered each
carousel slide as a deterministic SVG (locked palette / typography /
layout, AI only for photography) → rasterized via ``@resvg/resvg-js``.
This is the noc-native, Python, seed-first equivalent: the **outbound**
rasterization primitive any product can consume to turn composed SVG
markup into a PNG.

**What ships** (``KB § PATTERNS/seed-fake-real-adapter.md`` shape):

- ``SvgRenderInput`` / ``RenderedImage`` value objects.
- ``SvgRenderAdapter`` Protocol.
- ``FakeSvgRenderAdapter`` — deterministic placeholder PNG, no
  rasterizer dependency (dev/test default).
- ``ResvgRenderAdapter`` — real rasterization via ``resvg-py`` with
  bundled OFL fonts (Cormorant Garamond + Inter), ``skip_system_fonts``.
- ``get_svg_render_adapter()`` factory.

**Consume recipe:**

    from noctusai_lib.integrations.svg_render import (
        SvgRenderInput,
        get_svg_render_adapter,
    )

    adapter = get_svg_render_adapter(real=True)          # prod
    result = adapter.render(SvgRenderInput(svg_markup=svg, width=1080, height=1350))
    storage.put(slide_png_path, result.png_bytes)        # or supply upload_url_resolver

Tests inject ``FakeSvgRenderAdapter`` (or ``real=False``) — never
monkeypatch the real adapter ([[di-test-seam]]).
"""

from __future__ import annotations

from noctusai_lib.integrations.svg_render.fake_adapter import FakeSvgRenderAdapter
from noctusai_lib.integrations.svg_render.resvg_adapter import (
    ResvgRenderAdapter,
    bundled_font_files,
)
from noctusai_lib.integrations.svg_render.types import (
    RenderedImage,
    SvgRenderAdapter,
    SvgRenderInput,
)


def resvg_available() -> bool:
    """``True`` when the ``resvg-py`` rasterizer can be imported."""
    try:
        import resvg_py  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def get_svg_render_adapter(
    *,
    real: bool = True,
    font_files: list[str] | None = None,
    upload_url_resolver=None,
) -> SvgRenderAdapter:
    """Return an SVG→PNG render adapter.

    - ``real=True`` (default) → :class:`ResvgRenderAdapter`. The
      ``resvg-py`` import is lazy (on ``render``), so construction never
      fails; a missing rasterizer raises a clear ``RuntimeError`` at
      render time rather than degrading silently.
    - ``real=False`` → :class:`FakeSvgRenderAdapter` (dev/test).

    ``font_files`` overrides the bundled OFL faces. ``upload_url_resolver``
    persists ``png_bytes`` to durable storage and returns a URL on
    ``RenderedImage.image_url``.
    """
    if not real:
        return FakeSvgRenderAdapter(upload_url_resolver=upload_url_resolver)
    return ResvgRenderAdapter(
        font_files=font_files,
        upload_url_resolver=upload_url_resolver,
    )


__all__ = [
    "FakeSvgRenderAdapter",
    "RenderedImage",
    "ResvgRenderAdapter",
    "SvgRenderAdapter",
    "SvgRenderInput",
    "bundled_font_files",
    "get_svg_render_adapter",
    "resvg_available",
]
