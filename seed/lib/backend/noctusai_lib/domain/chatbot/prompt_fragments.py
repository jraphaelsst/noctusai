"""Reusable system-prompt fragments — opt-in, appendable.

WHY this module
---------------
Takeaway 5.9 (prompt over-obedience): LLMs reformat provider-issued
URLs even when it breaks them — the model inserted a `/u/0/` segment
into a Google `htmlLink` (→ HTTP 400). The same hazard generalizes to
Stripe checkout URLs, Vista links, WAHA media URLs, YouTube URLs: any
opaque provider-issued URL the model is tempted to "tidy up".

The fix is a single, generic system-prompt clause. The **seed owns the
string**; products **compose** it onto their own `system_prompt` —
deliberately NOT hard-baked into every prompt (consumers keep prompt
ownership; `openai_orchestrator` takes `system_prompt` from the
consumer). This is a constant + a tiny compose helper, NOT a prompt
framework.

Filed in `projects/oauth-integrations-seed-lift/` (residual gap 3 of 3).
"""

from __future__ import annotations

#: Generic, provider-agnostic URL-immutability instruction. Append to a
#: product's own system prompt when the bot relays provider-issued URLs
#: (auth_url, html_link / htmlLink, Stripe checkout, WAHA media, YouTube).
URL_IMMUTABILITY_FRAGMENT: str = (
    "External URLs are immutable. When a tool response contains a URL "
    "(for example auth_url, html_link, htmlLink, a checkout or payment "
    "link, a media link), copy it character-for-character into your "
    "reply. Never add a `/u/0/` (or any account-index) prefix, never "
    "rewrite or shorten the domain, never re-encode query parameters, "
    "and never reformat the link. The URL works only exactly as the "
    "tool returned it."
)


def with_url_immutability(system_prompt: str) -> str:
    """Return `system_prompt` with the URL-immutability fragment appended.

    Idempotent: if the fragment is already present (verbatim), the
    prompt is returned unchanged (no double-append on re-composition).
    A blank prompt yields the fragment alone.
    """
    base = (system_prompt or "").rstrip()
    if URL_IMMUTABILITY_FRAGMENT in base:
        return base
    if not base:
        return URL_IMMUTABILITY_FRAGMENT
    return f"{base}\n\n{URL_IMMUTABILITY_FRAGMENT}"


__all__ = [
    "URL_IMMUTABILITY_FRAGMENT",
    "with_url_immutability",
]
