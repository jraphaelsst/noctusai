"""ResvgRenderAdapter — real rasterization + bundled-font rendering.

These exercise the actual ``resvg-py`` path (the dep ships in seed). If
``resvg-py`` is somehow absent the suite skips loudly rather than passing
vacuously.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.svg_render import (
    ResvgRenderAdapter,
    SvgRenderInput,
    resvg_available,
)

pytestmark = pytest.mark.skipif(
    not resvg_available(), reason="resvg-py not installed in this environment"
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _svg(text_family: str, text: str = "Valorização") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" '
        'viewBox="0 0 600 300">'
        '<rect width="600" height="300" fill="#2A2620"/>'
        f'<text x="40" y="120" font-family="{text_family}" font-size="72" '
        f'fill="#F5F1EA">{text}</text></svg>'
    )


def test_renders_valid_png_at_requested_size() -> None:
    adapter = ResvgRenderAdapter()
    result = adapter.render(
        SvgRenderInput(svg_markup=_svg("Inter"), width=600, height=300)
    )
    assert result.png_bytes[:8] == _PNG_MAGIC
    assert result.backend == "resvg"
    assert (result.width, result.height) == (600, 300)


def test_bundled_cormorant_font_actually_draws() -> None:
    """With bundled fonts + skip_system_fonts, a Cormorant text node must
    produce strictly more bytes than the same SVG whose font is unknown —
    proving the bundled face is found and rasterized (not silently dropped)."""
    adapter = ResvgRenderAdapter()
    with_font = adapter.render(SvgRenderInput(svg_markup=_svg("Cormorant Garamond")))
    no_such_font = adapter.render(SvgRenderInput(svg_markup=_svg("No Such Font XYZ")))
    assert len(with_font.png_bytes) > len(no_such_font.png_bytes)


def test_upload_resolver_invoked_with_real_bytes() -> None:
    captured: dict = {}

    def _upload(png: bytes, req: SvgRenderInput) -> str:
        captured["len"] = len(png)
        captured["magic_ok"] = png[:8] == _PNG_MAGIC
        return "https://storage.example/slide.png"

    adapter = ResvgRenderAdapter(upload_url_resolver=_upload)
    result = adapter.render(SvgRenderInput(svg_markup=_svg("Inter"), width=200, height=100))
    assert result.image_url == "https://storage.example/slide.png"
    assert captured["magic_ok"] is True
    assert captured["len"] > 0


def test_intrinsic_size_when_dimensions_omitted() -> None:
    adapter = ResvgRenderAdapter()
    result = adapter.render(SvgRenderInput(svg_markup=_svg("Inter")))
    # SVG declares width=600 height=300 → resvg honours intrinsic size
    assert (result.width, result.height) == (600, 300)
