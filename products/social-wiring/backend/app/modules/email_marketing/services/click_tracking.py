"""Click tracking — rewrite a rendered email's links through a signed redirect.

P1b(c), 2026-10-10. Every http/https ``href`` on an ``<a>``/``<area>`` of a LIVE
email becomes ``{FRONTEND_BASE_URL}/api/email-marketing/t/c/{token}``; the token
is a ``signed_tokens`` purpose ``click`` carrying ``{"s": send_log_id, "u": url}``.
The public redirect (``routers/tracking.py``) only ever sends the browser to the
URL inside a valid token — never to anything from the query string — so the
endpoint cannot be used as an open redirect.

Public base: social-wiring is one container serving the SPA and the API on the
same host (house container model, ``serve_spa``; the frontend calls ``/api/...``
same-origin), so ``FRONTEND_BASE_URL`` — already required for the unsubscribe
link — is also the API's public origin.

Left untouched: the contact's unsubscribe link (the send guard checks it is
present verbatim, and RFC 8058 needs the real URL), ``mailto:``/``tel:``, ``#``
anchors, relative URLs and template placeholders. The rewrite is HTML-aware:
``html.parser`` locates each anchor start tag and only that tag's ``href``
attribute value is replaced — body text that merely looks like a URL, and every
other attribute, stay byte-identical.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional

from noctusai_lib.security import signed_tokens

TOKEN_PURPOSE = "click"
CLICK_PATH = "/api/email-marketing/t/c/"
_LINK_TAGS = {"a", "area"}
# One attribute of a start tag (name, then an optional double-quoted,
# single-quoted or bare value). Walking every attribute in order means an
# ``href=`` that only appears INSIDE another attribute's value is never touched.
_ATTR = re.compile(
    r"""(?P<lead>\s+(?P<name>[^\s"'>/=]+))(?P<value>\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?"""
)


def _replace_href(raw_tag: str, new_href: str) -> Optional[str]:
    """``raw_tag`` with its (first) href value replaced, or None if not found."""
    for m in _ATTR.finditer(raw_tag):
        if m.group("name").lower() == "href" and m.group("value"):
            return f'{raw_tag[:m.start()]}{m.group("lead")}="{new_href}"{raw_tag[m.end():]}'
    return None


def is_trackable(url: Optional[str]) -> bool:
    """Only absolute http(s) URLs are tracked (and are the only redirect targets)."""
    if not url:
        return False
    lowered = url.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def make_token(secret: str, send_log_id: str, url: str) -> str:
    """Click token bound to one send_log (one recipient) and one URL. Never
    expires — an old email's links keep working. Raises ValueError on an
    empty secret (a token signed with "" is forgeable)."""
    return signed_tokens.sign(TOKEN_PURPOSE, {"s": send_log_id, "u": url}, secret)


def verify_token(secret: str, token: str) -> Optional[dict]:
    """``{"send_log_id", "url"}`` for a valid click token whose target is
    http(s); None otherwise (forged, other purpose, malformed, non-http)."""
    data = signed_tokens.verify(TOKEN_PURPOSE, token, secret)
    if not data:
        return None
    send_log_id, url = data.get("s"), data.get("u")
    if not send_log_id or not isinstance(url, str) or not is_trackable(url):
        return None
    return {"send_log_id": str(send_log_id), "url": url}


def tracking_url(base: str, secret: str, send_log_id: str, url: str) -> str:
    return f"{base.rstrip('/')}{CLICK_PATH}{make_token(secret, send_log_id, url)}"


class _AnchorLocator(HTMLParser):
    """Collects ``(offset, raw_start_tag, href)`` for every link start tag."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.hits: list[tuple[int, str, str]] = []
        self._line_starts = [0]
        for i, ch in enumerate(source):
            if ch == "\n":
                self._line_starts.append(i + 1)

    def handle_starttag(self, tag, attrs):
        if tag not in _LINK_TAGS:
            return
        href = next((v for k, v in attrs if k == "href"), None)
        raw = self.get_starttag_text()
        if href is None or raw is None:
            return
        line, col = self.getpos()
        self.hits.append((self._line_starts[line - 1] + col, raw, href))


def rewrite_links(html: str, *, base: str, secret: str, send_log_id: str,
                  keep: frozenset[str] | set[str] = frozenset()) -> str:
    """``html`` with every trackable link routed through the click redirect for
    this recipient's ``send_log_id``. URLs in ``keep`` (the unsubscribe link)
    are left verbatim."""
    if not html:
        return html
    locator = _AnchorLocator(html)
    locator.feed(html)
    locator.close()

    out: list[str] = []
    cursor = 0
    for offset, raw, href in locator.hits:
        if offset < cursor or html[offset:offset + len(raw)] != raw:
            continue  # defensive: never splice at a position we did not parse
        url = href.strip()
        if not is_trackable(url) or url in keep or "{{" in url:
            continue
        new_href = tracking_url(base, secret, send_log_id, url)
        new_raw = _replace_href(raw, new_href)
        if new_raw is None:
            continue
        out.append(html[cursor:offset])
        out.append(new_raw)
        cursor = offset + len(raw)
    out.append(html[cursor:])
    return "".join(out)


__all__ = [
    "CLICK_PATH", "TOKEN_PURPOSE", "is_trackable", "make_token", "rewrite_links",
    "tracking_url", "verify_token",
]
