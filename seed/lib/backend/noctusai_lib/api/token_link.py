"""Token-link tier -- the one way a link that IS its own authorization is resolved (owner decision 2026-11-10).

A ``token-link`` route (``@access_tier("public", category="token-link")``) is anonymous but opened by an unguessable link
the org sent to ONE person: a content-approval link, a published-report link. KB § PATTERNS/security/access-tiers.md.
The controls every such route needs, and where each lives:

* **server-generated high-entropy token** -- the DB default (``gen_random_uuid()``, 122 bits) or ``secrets.token_urlsafe``;
  never a caller-supplied value. :func:`resolve_token_link` refuses a token that is not a UUID (a malformed link is a 404
  and never a DB round-trip).
* **server-checked expiry that FAILS CLOSED** -- :func:`resolve_token_link` treats a missing or unparsable expiry as expired
  (``require_expiry=True``); a link with no end date is a credential that never dies.
* **one-time use when the action mutates** -- the caller's UPDATE re-states ``status = 'pending'`` and treats 0 rows as
  :class:`TokenLinkGone` (410); :class:`TokenLinkGone` is the shared outcome for "already used".
* **a rate limit** -- the keeper ``check_access_tier_routes`` requires a limiter on the route.
* **no token in logs** -- log :func:`token_fingerprint`, never the token (the value is a bearer credential).
* **no internal ids in the response** -- project to an explicit public view; never ``**row``.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional
from uuid import UUID


class TokenLinkError(Exception):
    """Base: the link cannot be used. Routes map the subclasses to 404 / 410."""


class TokenLinkNotFound(TokenLinkError):
    """Malformed, unknown, or not-yet-published link (404 -- indistinguishable on purpose)."""


class TokenLinkGone(TokenLinkError):
    """The link existed but is expired or already used (410)."""


def token_fingerprint(token: str) -> str:
    """A short, non-reversible id of a token for logs (the token itself is a bearer credential and must never be logged)."""
    return "tok:" + hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:10]


def _parse_expiry(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def resolve_token_link(
    token: str,
    fetch: Callable[[str], Optional[Mapping[str, Any]]],
    *,
    expires_field: str = "expires_at",
    require_expiry: bool = True,
    now: Optional[datetime] = None,
) -> Mapping[str, Any]:
    """The row ``token`` opens, or :class:`TokenLinkNotFound` / :class:`TokenLinkGone`. Fail closed throughout.

    ``fetch(canonical_token)`` is the product's read (one admin-client query by the token column). A token that does not
    parse as a UUID is not looked up at all. A row whose expiry is missing (when ``require_expiry``) or unparsable counts as
    EXPIRED -- never as "no expiry"."""
    try:
        canonical = str(UUID(str(token)))
    except (ValueError, AttributeError, TypeError):
        raise TokenLinkNotFound("link not found") from None
    row = fetch(canonical)
    if row is None:
        raise TokenLinkNotFound("link not found")
    raw = row.get(expires_field)
    if raw in (None, ""):
        if require_expiry:
            raise TokenLinkGone("link expired")
    else:
        try:
            expired = _parse_expiry(raw) <= (now or datetime.now(timezone.utc))
        except (ValueError, TypeError):
            raise TokenLinkGone("link expired") from None
        if expired:
            raise TokenLinkGone("link expired")
    return row


__all__ = ["TokenLinkError", "TokenLinkGone", "TokenLinkNotFound", "resolve_token_link", "token_fingerprint"]
