"""Per-contact unsubscribe links — the precondition for any REAL send.

LGPD (and every ESP's terms) require a working opt-out in marketing email, so it
holds by construction: a template without `{{unsubscribe_url}}` gets the
`UNSUBSCRIBE_FOOTER` appended (P1b(a), 2026-10-10), every rendered body must
then contain that contact's own link (else `SendService` refuses the batch), and
the link needs `FRONTEND_BASE_URL`. Emails also carry RFC 8058 one-click headers.
"""
from __future__ import annotations

from noctusai_lib.security import signed_tokens

UNSUBSCRIBE_VARIABLE = "unsubscribe_url"
TOKEN_PURPOSE = "unsubscribe"
UNSUBSCRIBE_PATH = "/descadastro/"


def make_token(secret: str, org_id: str, contact_id: str, email: str) -> str:
    """Purpose-bound signed unsubscribe token (never expires: an old email's
    link must keep working). Raises ValueError on an empty secret."""
    return signed_tokens.sign(
        TOKEN_PURPOSE, {"org_id": org_id, "contact_id": contact_id, "email": email}, secret,
    )


def unsubscribe_url(settings, org_id: str, contact_id: str, email: str) -> str | None:
    """The contact's public unsubscribe URL, or None when it cannot be built —
    no frontend base URL, or no signing secret (then no live send can carry a
    link, so none is allowed)."""
    base = (getattr(settings, "frontend_base_url", "") or "").rstrip("/")
    if not base:
        return None
    try:
        token = make_token(getattr(settings, "jwt_secret", ""), org_id, contact_id, email)
    except ValueError:  # empty JWT_SECRET: a token signed with "" is forgeable
        return None
    return f"{base}{UNSUBSCRIBE_PATH}{token}"


UNSUBSCRIBE_FOOTER = (
    '<p style="font-size:12px;color:#6b7280;margin-top:24px;text-align:center">'
    "Não quer mais receber estes e-mails? "
    '<a href="{{unsubscribe_url}}" style="color:#6b7280">Descadastrar</a></p>'
)


def template_carries_unsubscribe(html: str | None) -> bool:
    return "{{" + UNSUBSCRIBE_VARIABLE + "}}" in (html or "")


def with_unsubscribe(html: str | None) -> str:
    """The template itself when it places `{{unsubscribe_url}}`; otherwise the
    template plus `UNSUBSCRIBE_FOOTER` (inside `</body>` when there is one)."""
    html = html or ""
    if template_carries_unsubscribe(html):
        return html
    marker = html.lower().rfind("</body>")
    if marker == -1:
        return html + UNSUBSCRIBE_FOOTER
    return html[:marker] + UNSUBSCRIBE_FOOTER + html[marker:]


def one_click_headers(link: str) -> dict[str, str]:
    return {"List-Unsubscribe": f"<{link}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
