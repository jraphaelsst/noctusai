"""FakeSvgRenderAdapter — deterministic placeholder PNG + call recording."""

from __future__ import annotations

from noctusai_lib.integrations.svg_render import (
    FakeSvgRenderAdapter,
    SvgRenderInput,
)

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_fake_returns_valid_png_bytes() -> None:
    adapter = FakeSvgRenderAdapter()
    result = adapter.render(SvgRenderInput(svg_markup=_SVG, width=1080, height=1350))
    assert result.png_bytes[:8] == _PNG_MAGIC
    assert result.backend == "fake"
    assert result.width == 1080 and result.height == 1350


def test_fake_is_deterministic() -> None:
    a = FakeSvgRenderAdapter().render(SvgRenderInput(svg_markup=_SVG))
    b = FakeSvgRenderAdapter().render(SvgRenderInput(svg_markup=_SVG))
    assert a.png_bytes == b.png_bytes
    assert a.raw["svg_sha256"] == b.raw["svg_sha256"]


def test_fake_records_calls() -> None:
    adapter = FakeSvgRenderAdapter()
    adapter.render(SvgRenderInput(svg_markup=_SVG, request_id="r1", width=540))
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["request_id"] == "r1"
    assert call["width"] == 540
    assert len(call["svg_sha256"]) == 64


def test_fake_image_url_only_with_resolver() -> None:
    no_resolver = FakeSvgRenderAdapter().render(SvgRenderInput(svg_markup=_SVG))
    assert no_resolver.image_url is None

    captured: list = []

    def _upload(png: bytes, req) -> str:
        captured.append((png, req))
        return "ignored"

    with_resolver = FakeSvgRenderAdapter(upload_url_resolver=_upload).render(
        SvgRenderInput(svg_markup=_SVG)
    )
    assert with_resolver.image_url is not None
    assert with_resolver.image_url.startswith("https://fake-svg-render.noctusai.local/")
    # NOTE: the Fake builds the URL from the hash; it does not invoke the
    # resolver (no real bytes to upload) — that's the loud "not real" signal.
