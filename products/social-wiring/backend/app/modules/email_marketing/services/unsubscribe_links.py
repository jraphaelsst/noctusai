"""Per-contact unsubscribe links — the precondition for any REAL send.

LGPD (and every ESP's terms) require a working opt-out in marketing email.
`SendService` refuses a live (non-dry-run) batch whose rendered HTML lacks the
contact's own link, so the guard holds by construction: the template must carry
`{{unsubscribe_url}}`, and the URL needs `FRONTEND_BASE_URL` to exist at all.
Automatic link injection is NOT done here — that is an open owner question.
"""
from __future__ import annotations

UNSUBSCRIBE_VARIABLE = "unsubscribe_url"
UNSUBSCRIBE_PATH = "/descadastro/"


def unsubscribe_url(settings, org_id: str, contact_id: str, email: str) -> str | None:
    """The contact's public unsubscribe URL, or None when no frontend base URL
    is configured (then no live send can carry a link, so none is allowed)."""
    base = (getattr(settings, "frontend_base_url", "") or "").rstrip("/")
    if not base:
        return None
    from ..routers.unsubscribe import generate_token

    return f"{base}{UNSUBSCRIBE_PATH}{generate_token(org_id, contact_id, email)}"


def template_carries_unsubscribe(html: str | None) -> bool:
    return "{{" + UNSUBSCRIBE_VARIABLE + "}}" in (html or "")
