"""resvg SVG→PNG adapter — the real rasterization path.

Wraps ``resvg-py`` (a self-contained Rust ``resvg`` binding — NO system
libs, ships manylinux + macOS wheels, so it works unchanged in the slim
prod ``runtime`` image). Fonts are **bundled** (``fonts/*.ttf``, OFL) and
passed explicitly with ``skip_system_fonts=True`` → deterministic,
dev↔prod-parity-safe text rendering (the slim image has no system fonts).

Lazy import — the seed stays importable on machines without ``resvg-py``
(the Fake path is the dev/test default).
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

from noctusai_lib.integrations.svg_render.types import (
    RenderedImage,
    SvgRenderInput,
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"


def bundled_font_files() -> list[str]:
    """Absolute paths of the bundled OFL ``.ttf`` faces (Cormorant + Inter)."""
    return [str(p) for p in sorted(_FONTS_DIR.glob("*.ttf"))]


def _png_dimensions(png: bytes) -> tuple[int, int]:
    """Read width/height from the PNG IHDR chunk (bytes 16–24, big-endian)."""
    if len(png) >= 24 and png[:8] == _PNG_MAGIC:
        width, height = struct.unpack(">II", png[16:24])
        return int(width), int(height)
    return 0, 0


class ResvgRenderAdapter:
    """Real SVG→PNG adapter via ``resvg-py`` with bundled fonts.

    ``font_files`` overrides the bundled face set (defaults to
    :func:`bundled_font_files`). ``upload_url_resolver`` is an optional
    ``(png_bytes, SvgRenderInput) -> url`` callback that persists the PNG
    to durable storage (e.g. Supabase Storage) and returns the URL; when
    omitted, the caller persists ``RenderedImage.png_bytes`` itself.
    """

    backend = "resvg"

    def __init__(self, *, font_files: list[str] | None = None, upload_url_resolver=None) -> None:
        self._font_files = font_files
        self._upload = upload_url_resolver

    def render(
        self,
        request: SvgRenderInput,
        *,
        org_id: str | None = None,
    ) -> RenderedImage:
        try:
            import resvg_py  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised via factory real=False default
            raise RuntimeError(
                "resvg-py is not installed — install it to use "
                "ResvgRenderAdapter, or use FakeSvgRenderAdapter "
                "(get_svg_render_adapter(real=False))."
            ) from exc

        fonts = self._font_files if self._font_files is not None else bundled_font_files()
        kwargs: dict = {
            "svg_string": request.svg_markup,
            "font_files": fonts,
            "skip_system_fonts": True,
        }
        if request.width is not None:
            kwargs["width"] = request.width
        if request.height is not None:
            kwargs["height"] = request.height

        started_at = time.monotonic()
        raw = resvg_py.svg_to_bytes(**kwargs)
        latency_ms = int((time.monotonic() - started_at) * 1000)

        png = bytes(raw)
        if png[:8] != _PNG_MAGIC:
            raise RuntimeError(
                "resvg returned non-PNG bytes — check the SVG markup is a "
                "valid, self-contained <svg> document."
            )

        width, height = _png_dimensions(png)
        image_url = self._upload(png, request) if self._upload is not None else None

        return RenderedImage(
            png_bytes=png,
            width=width,
            height=height,
            backend=self.backend,
            latency_ms=latency_ms,
            image_url=image_url,
            raw={
                "request_id": request.request_id,
                "font_files": [Path(f).name for f in fonts],
                "byte_len": len(png),
            },
        )
