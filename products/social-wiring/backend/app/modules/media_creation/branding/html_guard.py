"""Write-time guard for a component's ``preview_html``.

Component previews are UNTRUSTED markup: they come from an imported folder or
from an editor, and they are rendered by the UI. The primary defence is on the
rendering side (a sandboxed ``<iframe srcdoc>`` with NO script permission, a
CSP meta, never the page DOM). This guard is the second wall: the database must
not hold markup that only a sandbox keeps harmless.

It VALIDATES — it does not rewrite. A preview that carries script, frames,
form posts, event-handler attributes, scripted URLs or off-allowlist fetches is
REJECTED with a precise message. Silently stripping would hand the author a
preview that renders differently from what they reviewed.

Allowed: the styling/drawing vocabulary previews actually use (``div``, ``svg``
and its filter primitives, ``style``, ``button`` …), ``<link rel=stylesheet|
preconnect>`` to the web-font hosts only, ``data:image/*`` image sources, ``#``
and ``https:`` hyperlinks.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

MAX_PREVIEW_BYTES = 200_000

FONT_HOSTS = frozenset({"fonts.googleapis.com", "fonts.gstatic.com"})

_FORBIDDEN_TAGS = frozenset(
    {
        "script", "iframe", "frame", "frameset", "object", "embed", "applet",
        "base", "form", "meta", "portal", "audio", "video", "source", "track",
        "input", "textarea", "select", "dialog", "noscript",
    }
)
_URL_ATTRS = frozenset({"href", "src", "xlink:href", "action", "formaction", "poster", "srcset", "data"})
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
_CSS_IMPORT = re.compile(r"@import\s+(?:url\()?\s*['\"]?([^'\")\s;]+)", re.I)


class PreviewHtmlRejected(ValueError):
    """The preview markup is not safe to store."""


def _check_css(css: str, where: str) -> None:
    low = css.lower()
    if "expression(" in low or "javascript:" in low or "behavior:" in low or "-moz-binding" in low:
        raise PreviewHtmlRejected(f"{where}: scripted CSS construct")
    for target in _CSS_IMPORT.findall(css):
        _check_https_font(target, f"{where} @import")
    for _, target in _CSS_URL.findall(css):
        target = target.strip()
        if target.startswith("#") or _DATA_IMAGE.match(target):
            continue
        _check_https_font(target, f"{where} url()")


def _check_https_font(url: str, where: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in FONT_HOSTS:
        raise PreviewHtmlRejected(
            f"{where}: only https URLs on {sorted(FONT_HOSTS)} are allowed, got {url[:80]!r}"
        )


class _Scanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_style = False
        self._style_buf: list[str] = []

    # tags -------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _FORBIDDEN_TAGS:
            raise PreviewHtmlRejected(f"<{tag}> is not allowed in a component preview")
        if tag == "style":
            self._in_style = True
            self._style_buf = []
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        for name, value in attr_map.items():
            if name.startswith("on"):
                raise PreviewHtmlRejected(f"event-handler attribute {name!r} is not allowed")
            if name == "style":
                _check_css(value, "inline style")
            if name in _URL_ATTRS:
                self._check_url(tag, name, value)
        if tag == "link":
            rel = attr_map.get("rel", "").lower()
            if rel not in {"stylesheet", "preconnect"}:
                raise PreviewHtmlRejected(f"<link rel={rel!r}> is not allowed")
            _check_https_font(attr_map.get("href", ""), "<link href>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._in_style:
            _check_css("".join(self._style_buf), "<style>")
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_buf.append(data)

    # urls -------------------------------------------------------------
    def _check_url(self, tag: str, name: str, value: str) -> None:
        v = value.strip()
        if tag == "link" and name == "href":
            return  # validated by the <link> branch
        if not v or v.startswith("#"):
            return
        if name in {"src", "poster", "srcset", "data"}:
            if _DATA_IMAGE.match(v):
                return
            raise PreviewHtmlRejected(
                f"<{tag} {name}> may only be a data:image/* URL (no remote fetch), got {v[:60]!r}"
            )
        if name in {"href", "xlink:href"}:
            if urlparse(v).scheme.lower() == "https":
                return
            raise PreviewHtmlRejected(f"<{tag} {name}> may only be '#…' or https:, got {v[:60]!r}")
        raise PreviewHtmlRejected(f"attribute {name!r} is not allowed")


def validate_preview_html(html: str) -> str:
    """Return ``html`` unchanged when safe; raise :class:`PreviewHtmlRejected`."""
    if not isinstance(html, str):
        raise PreviewHtmlRejected("preview_html must be a string")
    if len(html.encode("utf-8")) > MAX_PREVIEW_BYTES:
        raise PreviewHtmlRejected(f"preview_html is larger than {MAX_PREVIEW_BYTES} bytes")
    scanner = _Scanner()
    try:
        scanner.feed(html)
        scanner.close()
    except PreviewHtmlRejected:
        raise
    except Exception as exc:  # parser failure is a rejection, never a pass
        raise PreviewHtmlRejected(f"preview_html could not be parsed: {exc}") from exc
    if scanner._in_style:
        raise PreviewHtmlRejected("<style> is not closed")
    return html
