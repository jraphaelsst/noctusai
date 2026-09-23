"""Pure functions that classify a request's caller from its headers.

Split out of ``middleware.py`` so the classification logic is testable
without constructing an ASGI scope — the two functions here take plain
strings and return plain strings.
"""
from __future__ import annotations

import re

from .types import ActorKind

#: `X-Noctus-Client` values the seed FE api client (`seed/lib/frontend
#: /src/api.ts`) sends: `"web"` for a normal browser session, or
#: `"agent:<name>"` when `navigator.webdriver` (or an equivalent
#: automation signal) is true. A server-to-server / internal caller
#: that has no end-user session at all sends the literal `"service"`.
_AGENT_HEADER_PREFIX = "agent:"
_SERVICE_HEADER_VALUE = "service"

#: Case-insensitive UA substrings that mean "this is a browser being
#: driven by automation," independent of whatever `X-Noctus-Client`
#: says (a script hitting the API directly, bypassing the seed FE
#: client entirely, still carries a tell-tale UA).
_AGENT_UA_RE = re.compile(r"headlesschrome|playwright|puppeteer", re.IGNORECASE)

#: Coarse UA "family" extraction — enough to group requests in a
#: report, never the full string (no PII-shaped fingerprint stored).
_UA_FAMILY_RE = re.compile(
    r"(HeadlessChrome|Chrome|Firefox|Safari|Edg|OPR|Playwright|Puppeteer|"
    r"curl|python-requests|okhttp|PostmanRuntime)",
    re.IGNORECASE,
)
_UA_HINT_MAX_LEN = 40


def detect_actor_kind(*, x_noctus_client: str | None, user_agent: str | None) -> ActorKind:
    """Classify the caller as ``"agent"``, ``"service"``, or ``"user"``.

    Order matters: an explicit `X-Noctus-Client: service` call (an
    internal cross-product server call, no end-user session) is
    authoritative over the UA — a server-side HTTP client's UA is
    whatever the library sets, never meaningful here. Absent that, an
    explicit `agent:<name>` header OR a matching automation UA both
    mean `"agent"`. Everything else defaults to `"user"` — the safe
    default when no signal says otherwise, matching every request from
    the seed FE client's normal `X-Noctus-Client: web`.
    """
    header = (x_noctus_client or "").strip().lower()
    if header == _SERVICE_HEADER_VALUE:
        return "service"
    if header.startswith(_AGENT_HEADER_PREFIX):
        return "agent"
    if user_agent and _AGENT_UA_RE.search(user_agent):
        return "agent"
    return "user"


def client_hint_from_ua(user_agent: str | None) -> str:
    """Coarse UA family (`"Chrome"`, `"Playwright"`, ...), never the raw
    string — this is what :class:`AuditEntry.client_hint` stores.
    `"unknown"` for an absent/unrecognised UA."""
    if not user_agent:
        return "unknown"
    match = _UA_FAMILY_RE.search(user_agent)
    if match:
        return match.group(1)
    return user_agent[:_UA_HINT_MAX_LEN]


__all__ = ["client_hint_from_ua", "detect_actor_kind"]
