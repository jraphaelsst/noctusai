"""get_svg_render_adapter — picks Fake vs Real(resvg) per the factory shape."""

from __future__ import annotations

from noctusai_lib.integrations.svg_render import (
    FakeSvgRenderAdapter,
    ResvgRenderAdapter,
    bundled_font_files,
    get_svg_render_adapter,
)


def test_real_false_returns_fake() -> None:
    adapter = get_svg_render_adapter(real=False)
    assert isinstance(adapter, FakeSvgRenderAdapter)
    assert adapter.backend == "fake"


def test_real_true_returns_resvg() -> None:
    adapter = get_svg_render_adapter(real=True)
    assert isinstance(adapter, ResvgRenderAdapter)
    assert adapter.backend == "resvg"


def test_default_is_real() -> None:
    assert isinstance(get_svg_render_adapter(), ResvgRenderAdapter)


def test_upload_resolver_threaded_to_fake() -> None:
    sentinel = lambda png, req: "url://x"  # noqa: E731
    adapter = get_svg_render_adapter(real=False, upload_url_resolver=sentinel)
    assert adapter._upload is sentinel


def test_bundled_fonts_present() -> None:
    fonts = bundled_font_files()
    names = {f.rsplit("/", 1)[-1] for f in fonts}
    # both OFL faces the design system relies on must ship in-package
    assert any("Cormorant" in n for n in names), names
    assert any("Inter" in n for n in names), names
