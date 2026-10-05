"""Component preview HTML guard (write-time wall behind the sandboxed iframe)."""
from __future__ import annotations

import pytest

from app.modules.media_creation.branding.html_guard import (
    PreviewHtmlRejected,
    validate_preview_html,
)

from ._branding_fixtures import DESIGN_SYSTEMS, PREVIEW


def test_every_real_preview_passes():
    previews = sorted(DESIGN_SYSTEMS.glob("*/components/*/preview.html"))
    assert len(previews) >= 20, "expected the four design systems' previews"
    for path in previews:
        validate_preview_html(path.read_text(encoding="utf-8"))


def test_plain_markup_passes_unchanged():
    assert validate_preview_html(PREVIEW) == PREVIEW


@pytest.mark.parametrize(
    "html",
    [
        "<script>alert(1)</script>",
        "<div onclick=\"x()\">a</div>",
        "<iframe src='https://evil'></iframe>",
        "<object data='x'></object>",
        "<form action='https://evil'><button>go</button></form>",
        "<meta http-equiv='refresh' content='0;url=https://evil'>",
        "<base href='https://evil/'>",
        "<a href='javascript:alert(1)'>x</a>",
        "<img src='https://evil/x.png'>",
        "<link rel='stylesheet' href='https://evil.example/x.css'>",
        "<link rel='icon' href='https://fonts.googleapis.com/x'>",
        "<style>@import url('https://evil.example/x.css');</style>",
        "<style>.a{background:url(https://evil.example/x.png)}</style>",
        "<div style=\"background:url(https://evil.example/x)\">a</div>",
        "<div style=\"width:expression(alert(1))\">a</div>",
        "<svg><a xlink:href='javascript:alert(1)'>x</a></svg>",
        "<svg><image href='data:image/svg+xml;base64,AAAA'/></svg>",
    ],
)
def test_rejects_unsafe_markup(html):
    with pytest.raises(PreviewHtmlRejected):
        validate_preview_html(html)


def test_allows_font_stylesheet_and_data_image():
    ok = (
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter'>"
        "<img alt='' src='data:image/png;base64,iVBORw0KGgo='>"
    )
    assert validate_preview_html(ok) == ok


def test_rejects_oversized():
    with pytest.raises(PreviewHtmlRejected):
        validate_preview_html("<div>" + "a" * 250_000 + "</div>")
