"""Double opt-in + one-click unsubscribe tokens and the RFC 8058 header pair.

Built on ``noctusai_lib.security.signed_tokens`` (purpose-bound HMAC): a confirm token never
verifies as an unsubscribe token and vice-versa. Payloads carry the subscriber id and the e-mail
HASH, never the address (a token is signed, not encrypted).

* confirm token: expiring (7 days default).
* unsubscribe token: never expires, an old e-mail's link must keep working.
"""
from __future__ import annotations

import time
from typing import Callable, Optional
from urllib.parse import urlparse

from noctusai_lib.security import signed_tokens

from .types import InvalidSubscriptionToken

CONFIRM_PURPOSE = "subscription_confirm"
UNSUBSCRIBE_PURPOSE = "subscription_unsubscribe"
CONFIRM_TTL_SECONDS = 7 * 24 * 3600


def _issue(purpose: str, secret: str, subscriber_id: str, email_hash: str, *, ttl_seconds, now) -> str:
    return signed_tokens.sign(purpose, {"sid": subscriber_id, "h": email_hash}, secret, ttl_seconds=ttl_seconds, now=now)


def _verify(purpose: str, token: str, secret: str, now) -> dict:
    data = signed_tokens.verify(purpose, token, secret, now=now)
    if not data or not data.get("sid") or not data.get("h"):
        raise InvalidSubscriptionToken("invalid, expired or tampered token")
    return {"subscriber_id": str(data["sid"]), "email_hash": str(data["h"])}


def issue_confirm_token(secret: str, subscriber_id: str, email_hash: str, *,
                        ttl_seconds: int = CONFIRM_TTL_SECONDS, now: Callable[[], float] = time.time) -> str:
    return _issue(CONFIRM_PURPOSE, secret, subscriber_id, email_hash, ttl_seconds=ttl_seconds, now=now)


def verify_confirm_token(secret: str, token: str, *, now: Callable[[], float] = time.time) -> dict:
    """``{subscriber_id, email_hash}``; raises ``InvalidSubscriptionToken``."""
    return _verify(CONFIRM_PURPOSE, token, secret, now)


def issue_unsubscribe_token(secret: str, subscriber_id: str, email_hash: str, *,
                            now: Callable[[], float] = time.time) -> str:
    return _issue(UNSUBSCRIBE_PURPOSE, secret, subscriber_id, email_hash, ttl_seconds=None, now=now)


def verify_unsubscribe_token(secret: str, token: str, *, now: Callable[[], float] = time.time) -> dict:
    """``{subscriber_id, email_hash}``; raises ``InvalidSubscriptionToken``."""
    return _verify(UNSUBSCRIBE_PURPOSE, token, secret, now)


def one_click_headers(unsubscribe_url: str, *, mailto: Optional[str] = None, allow_http: bool = False) -> dict[str, str]:
    """The RFC 8058 pair for ``OutgoingEmail.headers`` (``ResendEmailSender`` forwards caller headers).

    ``List-Unsubscribe`` must carry an https URL (RFC 8058 s3.1); ``allow_http`` is for local dev only."""
    scheme = urlparse(unsubscribe_url).scheme
    if scheme != "https" and not (allow_http and scheme == "http"):
        raise ValueError("List-Unsubscribe one-click needs an https URL")
    value = f"<{unsubscribe_url}>" + (f", <mailto:{mailto}>" if mailto else "")
    return {"List-Unsubscribe": value, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


__all__ = [
    "CONFIRM_PURPOSE", "UNSUBSCRIBE_PURPOSE", "CONFIRM_TTL_SECONDS",
    "issue_confirm_token", "verify_confirm_token", "issue_unsubscribe_token", "verify_unsubscribe_token",
    "one_click_headers",
]
